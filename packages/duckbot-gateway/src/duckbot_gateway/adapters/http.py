"""Wire formats for one frontier, one low-cost and one local provider.

**Status: written from the published request and response shapes, and not yet run
against a live endpoint.** Nobody on this project has an account key at the time of
writing, and a test that mocks the provider proves only that the code matches what the
author believed the provider does. Running each of these against the real service once,
with a throwaway key and a one-word prompt, is the first task for whoever gets a key. It
takes ten minutes and it is the only thing that turns this file from plausible into
known.

Two decisions here are not stylistic.

**No HTTP dependency.** Transport is a protocol with a standard-library implementation.
Adding ``requests`` or ``httpx`` to the core dependency tree buys convenience and costs a
licence review, a supply-chain surface and a pinned version in every deployment. The
seam also means tests never touch the network, which is why the whole suite runs offline.

**Error bodies are not logged.** When a provider returns an error it frequently echoes
part of the request, and the request is the thing this product exists to keep private. A
failure records the status code and the provider's error *type*, never the body. If you
need the body while debugging, read it at the point of failure; do not put it into a log
line that will be shipped to a customer's audit export.

Retries are deliberately absent. The gateway's fallback chain is the retry mechanism, and
a client that silently retried would make a provider look healthier than it is in the
cost report.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

from ..errors import AdapterFailure
from .base import Completion

DEFAULT_TIMEOUT_S = 60.0


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str

    def json(self) -> dict[str, Any]:
        try:
            parsed: Any = json.loads(self.body)
        except json.JSONDecodeError as exc:
            raise AdapterFailure(
                f"provider returned status {self.status} with a body that is not JSON"
            ) from exc
        if not isinstance(parsed, dict):
            raise AdapterFailure("provider returned JSON that is not an object")
        return parsed


class HttpTransport(Protocol):
    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_s: float,
    ) -> HttpResponse: ...


class UrllibTransport:
    """The standard library, so that this package adds no HTTP dependency."""

    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> HttpResponse:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="POST")
        for key, value in headers.items():
            request.add_header(key, value)
        request.add_header("content-type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                return HttpResponse(
                    status=response.status, body=response.read().decode("utf-8", "replace")
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(status=exc.code, body=exc.read().decode("utf-8", "replace"))
        except urllib.error.URLError as exc:
            raise AdapterFailure(f"could not reach {url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise AdapterFailure(f"{url} did not respond within {timeout_s:g}s") from exc


def _error_type(response: HttpResponse) -> str:
    """The provider's error type, never its body.

    An error body often quotes the request back. Putting that into an exception message
    puts it into a log, and the log is the one place this product cannot afford to leak.
    """
    try:
        error = response.json().get("error")
    except AdapterFailure:
        return "unparseable"
    if isinstance(error, dict):
        kind = error.get("type") or error.get("code")
        return str(kind) if kind else "unspecified"
    return "unspecified"


def _usage(body: dict[str, Any], in_key: str, out_key: str) -> tuple[int, int, bool]:
    """Token counts from a provider's usage object, and whether there was one.

    A provider that reports nothing gets zeros and a false flag, never an estimate. See
    :class:`~duckbot_gateway.adapters.base.Completion`.
    """
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return 0, 0, False
    return int(usage.get(in_key, 0)), int(usage.get(out_key, 0)), True


def _check(response: HttpResponse, provider: str) -> dict[str, Any]:
    if response.status >= 400:
        raise AdapterFailure(
            f"{provider} returned status {response.status} ({_error_type(response)}); "
            "the response body is not included because providers echo the request in it"
        )
    return response.json()


class AnthropicClient:
    """The Messages API. One user turn, no streaming, no tools.

    The API key is held in memory for the life of the process and is never written to a
    cost record, an audit event or an exception message. It is passed in rather than read
    from the environment here, so that whoever constructs this decides where secrets come
    from.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int = 1024,
        base_url: str = "https://api.anthropic.com",
        api_version: str = "2023-06-01",
        transport: HttpTransport | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        if not api_key.strip():
            raise ValueError("an API key is required")
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._url = f"{base_url.rstrip('/')}/v1/messages"
        self._version = api_version
        self._transport = transport or UrllibTransport()
        self._timeout_s = timeout_s

    def chat(self, prompt: str) -> Completion:
        started = perf_counter()
        response = self._transport.post(
            self._url,
            headers={"x-api-key": self._api_key, "anthropic-version": self._version},
            payload={
                "model": self._model,
                "max_tokens": self._max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout_s=self._timeout_s,
        )
        body = _check(response, "anthropic")
        blocks = body.get("content")
        if not isinstance(blocks, list):
            raise AdapterFailure("anthropic response had no content blocks")
        text = "".join(
            str(block.get("text", ""))
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
        tokens_in, tokens_out, reported = _usage(body, "input_tokens", "output_tokens")
        return Completion(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=int((perf_counter() - started) * 1000),
            usage_reported=reported,
        )


class OpenAICompatibleClient:
    """Chat Completions, as spoken by most low-cost providers and several local servers.

    One implementation covers the cheap hosted providers and a self-hosted llama.cpp or
    vLLM endpoint. Which of those a given configuration is decides whether it is
    registered as a local or a remote adapter — the wire format does not.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        transport: HttpTransport | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._api_key = api_key
        self._transport = transport or UrllibTransport()
        self._timeout_s = timeout_s

    def chat(self, prompt: str) -> Completion:
        started = perf_counter()
        headers = {"authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        response = self._transport.post(
            self._url,
            headers=headers,
            payload={"model": self._model, "messages": [{"role": "user", "content": prompt}]},
            timeout_s=self._timeout_s,
        )
        body = _check(response, "openai-compatible")
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AdapterFailure("openai-compatible response had no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise AdapterFailure("openai-compatible response had no message")
        tokens_in, tokens_out, reported = _usage(body, "prompt_tokens", "completion_tokens")
        return Completion(
            text=str(message.get("content") or ""),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=int((perf_counter() - started) * 1000),
            usage_reported=reported,
        )


class OllamaClient:
    """A model running on this machine, through Ollama's chat endpoint.

    Registered as a *local* adapter, which is what makes it the only thing LOCAL_ONLY
    content can reach. Ollama reports token counts, so a local call still produces real
    usage figures — at zero cost, which is the point.
    """

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://localhost:11434",
        transport: HttpTransport | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/api/chat"
        self._model = model
        self._transport = transport or UrllibTransport()
        self._timeout_s = timeout_s

    def chat(self, prompt: str) -> Completion:
        started = perf_counter()
        response = self._transport.post(
            self._url,
            headers={},
            payload={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout_s=self._timeout_s,
        )
        body = _check(response, "ollama")
        message = body.get("message")
        if not isinstance(message, dict):
            raise AdapterFailure("ollama response had no message")
        has_usage = "prompt_eval_count" in body or "eval_count" in body
        return Completion(
            text=str(message.get("content") or ""),
            tokens_in=int(body.get("prompt_eval_count", 0)),
            tokens_out=int(body.get("eval_count", 0)),
            latency_ms=int((perf_counter() - started) * 1000),
            usage_reported=has_usage,
        )
