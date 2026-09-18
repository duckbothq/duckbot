"""Clients that do not touch the network.

These are shipped rather than kept in the test directory because downstream packages
need them too: a task engine's tests should be able to run a whole task without a key, a
network or a bill. They are also what a demo should use, so that nobody's first
experience of the product depends on a provider being up.
"""

from __future__ import annotations

from collections.abc import Callable

from ..errors import AdapterFailure
from .base import Completion


def _count(text: str) -> int:
    """A token count stand-in, for fixtures only.

    Four characters to a token is roughly true for English and roughly wrong for
    Chinese. It is fine in a stub, where the number only has to be stable and non-zero,
    and it is exactly the kind of estimate that must never reach a cost record from a
    real provider.
    """
    return max(1, len(text) // 4)


class EchoClient:
    """Deterministic. Returns the prompt with a prefix, and plausible token counts."""

    def __init__(self, label: str = "echo", latency_ms: int = 1) -> None:
        self.label = label
        self.latency_ms = latency_ms
        self.calls: list[str] = []

    def chat(self, prompt: str) -> Completion:
        self.calls.append(prompt)
        text = f"[{self.label}] {prompt}"
        return Completion(
            text=text,
            tokens_in=_count(prompt),
            tokens_out=_count(text),
            latency_ms=self.latency_ms,
        )


class ScriptedClient:
    """Returns prepared replies in order. For testing multi-step behaviour."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[str] = []

    def chat(self, prompt: str) -> Completion:
        self.calls.append(prompt)
        if not self._replies:
            raise AdapterFailure("the scripted client has no replies left")
        reply = self._replies.pop(0)
        return Completion(text=reply, tokens_in=_count(prompt), tokens_out=_count(reply))


class FailingClient:
    """Always fails. For exercising fallback chains."""

    def __init__(self, message: str = "provider unavailable") -> None:
        self.message = message
        self.calls: list[str] = []

    def chat(self, prompt: str) -> Completion:
        self.calls.append(prompt)
        raise AdapterFailure(self.message)


class RecordingClient:
    """Wraps another client and records exactly what was sent.

    Used by the tests that assert real values never reach a provider. Asserting on what
    a fake *received* is the only way to prove the redaction happened on the outbound
    path rather than somewhere convenient.
    """

    def __init__(self, inner: Callable[[str], Completion]) -> None:
        self._inner = inner
        self.sent: list[str] = []

    def chat(self, prompt: str) -> Completion:
        self.sent.append(prompt)
        return self._inner(prompt)
