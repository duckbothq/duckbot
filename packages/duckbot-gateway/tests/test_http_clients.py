"""The three wire formats, against a fake transport.

**What these tests prove and what they do not.** They prove the clients build the
request each provider's documentation describes and read the response shape it
documents. They do not prove the providers actually behave that way — nothing that mocks
a server can. Until each client has been run once against the real endpoint, treat this
file as a specification of our belief rather than a verification of it. The README says
the same thing where somebody will read it.

No test here opens a socket.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from duckbot_gateway import AdapterFailure
from duckbot_gateway.adapters.http import (
    AnthropicClient,
    HttpResponse,
    OllamaClient,
    OpenAICompatibleClient,
)

KEY = "test-key-not-a-real-credential"


class FakeTransport:
    """Records the request and returns a prepared response."""

    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.url: str | None = None
        self.headers: dict[str, str] = {}
        self.payload: dict[str, Any] = {}

    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_s: float,
    ) -> HttpResponse:
        self.url = url
        self.headers = dict(headers)
        self.payload = dict(payload)
        return self.response


def ok(body: dict[str, Any]) -> HttpResponse:
    return HttpResponse(status=200, body=json.dumps(body))


class TestAnthropic:
    def response(self) -> HttpResponse:
        return ok(
            {
                "content": [{"type": "text", "text": "hello"}],
                "usage": {"input_tokens": 12, "output_tokens": 3},
            }
        )

    def test_the_request_matches_the_documented_shape(self) -> None:
        transport = FakeTransport(self.response())
        client = AnthropicClient(api_key=KEY, model="a-model", transport=transport, max_tokens=256)
        client.chat("say hello")
        assert transport.url == "https://api.anthropic.com/v1/messages"
        assert transport.headers["x-api-key"] == KEY
        assert transport.headers["anthropic-version"]
        assert transport.payload["messages"] == [{"role": "user", "content": "say hello"}]
        assert transport.payload["max_tokens"] == 256

    def test_text_and_usage_are_read(self) -> None:
        client = AnthropicClient(
            api_key=KEY, model="a-model", transport=FakeTransport(self.response())
        )
        completion = client.chat("say hello")
        assert completion.text == "hello"
        assert (completion.tokens_in, completion.tokens_out) == (12, 3)
        assert completion.usage_reported

    def test_missing_usage_is_flagged_rather_than_assumed(self) -> None:
        client = AnthropicClient(
            api_key=KEY,
            model="a-model",
            transport=FakeTransport(ok({"content": [{"type": "text", "text": "hi"}]})),
        )
        completion = client.chat("hi")
        assert not completion.usage_reported
        assert completion.tokens_in == 0

    def test_an_empty_key_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError, match="API key"):
            AnthropicClient(api_key="   ", model="a-model")


class TestOpenAICompatible:
    def test_the_request_matches_the_documented_shape(self) -> None:
        transport = FakeTransport(
            ok(
                {
                    "choices": [{"message": {"content": "hello"}}],
                    "usage": {"prompt_tokens": 9, "completion_tokens": 2},
                }
            )
        )
        client = OpenAICompatibleClient(
            base_url="https://example-provider.invalid/v1",
            model="fast-1",
            api_key=KEY,
            transport=transport,
        )
        completion = client.chat("say hello")
        assert transport.url == "https://example-provider.invalid/v1/chat/completions"
        assert transport.headers["authorization"] == f"Bearer {KEY}"
        assert completion.text == "hello"
        assert (completion.tokens_in, completion.tokens_out) == (9, 2)

    def test_a_keyless_endpoint_sends_no_authorization_header(self) -> None:
        """A self-hosted server on the same machine usually wants no credential."""
        transport = FakeTransport(ok({"choices": [{"message": {"content": "hi"}}]}))
        client = OpenAICompatibleClient(
            base_url="http://localhost:8080/v1", model="local-1", transport=transport
        )
        client.chat("hi")
        assert "authorization" not in transport.headers

    def test_a_response_without_choices_fails_clearly(self) -> None:
        client = OpenAICompatibleClient(
            base_url="http://x.invalid/v1", model="m", transport=FakeTransport(ok({}))
        )
        with pytest.raises(AdapterFailure, match="no choices"):
            client.chat("hi")


class TestOllama:
    def test_the_request_matches_the_documented_shape(self) -> None:
        transport = FakeTransport(
            ok(
                {
                    "message": {"content": "你好"},
                    "prompt_eval_count": 7,
                    "eval_count": 4,
                }
            )
        )
        client = OllamaClient(model="small-local", transport=transport)
        completion = client.chat("你好")
        assert transport.url == "http://localhost:11434/api/chat"
        assert transport.payload["stream"] is False
        assert completion.text == "你好"
        assert (completion.tokens_in, completion.tokens_out) == (7, 4)
        assert completion.usage_reported


class TestErrors:
    def test_the_provider_error_body_is_never_included(self) -> None:
        """Providers quote the request back in error bodies. The request is the secret."""
        secret = "身份證 A123456(3)"
        transport = FakeTransport(
            HttpResponse(
                status=400,
                body=json.dumps({"error": {"type": "invalid_request_error", "message": secret}}),
            )
        )
        client = AnthropicClient(api_key=KEY, model="m", transport=transport)
        with pytest.raises(AdapterFailure) as excinfo:
            client.chat(secret)
        message = str(excinfo.value)
        assert "A123456(3)" not in message
        assert "invalid_request_error" in message
        assert "400" in message

    def test_the_api_key_never_appears_in_an_error(self) -> None:
        transport = FakeTransport(HttpResponse(status=401, body='{"error":{"type":"auth"}}'))
        client = AnthropicClient(api_key=KEY, model="m", transport=transport)
        with pytest.raises(AdapterFailure) as excinfo:
            client.chat("hi")
        assert KEY not in str(excinfo.value)

    def test_a_non_json_body_fails_without_quoting_it(self) -> None:
        transport = FakeTransport(HttpResponse(status=500, body="<html>身份證 A123456(3)</html>"))
        client = OpenAICompatibleClient(
            base_url="http://x.invalid/v1", model="m", transport=transport
        )
        with pytest.raises(AdapterFailure) as excinfo:
            client.chat("hi")
        assert "A123456(3)" not in str(excinfo.value)
        assert "unparseable" in str(excinfo.value)
