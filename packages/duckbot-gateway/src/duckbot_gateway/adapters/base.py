"""Adapters, and the reason there are two kinds.

``OutboundPermit`` exists so that nothing reaches a hosted provider without a policy
decision behind it. That guarantee is only worth something if the adapter layer cannot
be handed raw text, so the two cases are different types:

* :class:`LocalModelAdapter` takes a ``str``. The content never leaves the machine, so
  there is nothing for a permit to authorise.
* :class:`RemoteModelAdapter` takes an :class:`~duckbot_core.OutboundPermit`. There is no
  overload that accepts a string, which means a caller cannot send content to a provider
  by forgetting a step — they would have to construct a permit, and that is impossible
  outside ``duckbot_core.policy``.

The wire formats live in :mod:`duckbot_gateway.adapters.clients`, behind
:class:`ChatClient`. A client never sees a permit and never makes a policy decision; it
turns a string into a completion. The two wrapper classes below are the whole of the
permit logic, deliberately small enough to review at a glance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from duckbot_core import OutboundPermit
from duckbot_schemas import ModelTier

from ..descriptors import ModelDescriptor
from ..errors import SensitivityCeilingExceeded


@dataclass(frozen=True)
class Completion:
    """What came back from a model.

    Token counts come from the provider's own usage figures where they are reported.
    Where they are not, the adapter says so by leaving them at zero rather than
    estimating, because an estimate in a cost record is indistinguishable from a
    measurement once it has been written down.

    ``usage_reported`` is how the difference stays visible. A call with no usage figures
    prices at zero, and a zero that means "free" and a zero that means "we were not told"
    look identical in a total. Anything that sums costs should carry this flag alongside
    them and describe the result as a floor when it is false.
    """

    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    usage_reported: bool = True

    def __post_init__(self) -> None:
        if self.tokens_in < 0 or self.tokens_out < 0 or self.latency_ms < 0:
            raise ValueError("token counts and latency cannot be negative")


class ChatClient(Protocol):
    """Turns a prompt into a completion. Knows a wire format and nothing else."""

    def chat(self, prompt: str) -> Completion: ...


class LocalModelAdapter(Protocol):
    """A model running on this machine."""

    @property
    def descriptor(self) -> ModelDescriptor: ...

    def complete(self, prompt: str, *, purpose: str) -> Completion: ...


class RemoteModelAdapter(Protocol):
    """A model on somebody else's machine. Takes a permit, never a string."""

    @property
    def descriptor(self) -> ModelDescriptor: ...

    def complete(self, permit: OutboundPermit, *, purpose: str) -> Completion: ...


class LocalAdapter:
    """Wraps a client as a local adapter."""

    def __init__(self, descriptor: ModelDescriptor, client: ChatClient) -> None:
        if descriptor.tier is not ModelTier.LOCAL:
            raise ValueError(
                f"{descriptor.key} is tier {descriptor.tier.value}, so it is not local and "
                "must be registered as a remote adapter, where a permit is required"
            )
        self._descriptor = descriptor
        self._client = client

    @property
    def descriptor(self) -> ModelDescriptor:
        return self._descriptor

    def complete(self, prompt: str, *, purpose: str) -> Completion:
        return self._client.chat(prompt)


class RemoteAdapter:
    """Wraps a client as a remote adapter. Sends the permit's payload, nothing else."""

    def __init__(self, descriptor: ModelDescriptor, client: ChatClient) -> None:
        if descriptor.tier is ModelTier.LOCAL:
            raise ValueError(
                f"{descriptor.key} is a local model and must be registered as a local "
                "adapter; wrapping it here would ask for a permit to send content that "
                "is not going anywhere"
            )
        self._descriptor = descriptor
        self._client = client

    @property
    def descriptor(self) -> ModelDescriptor:
        return self._descriptor

    def complete(self, permit: OutboundPermit, *, purpose: str) -> Completion:
        """Send what the permit authorised.

        The payload is used rather than any other text the caller has to hand. If the
        policy decision was to redact, the payload is the redacted version, and sending
        anything else would defeat the decision that was just made.
        """
        if permit.destination != self._descriptor.key:
            raise SensitivityCeilingExceeded(
                f"this permit authorises {permit.destination}, not {self._descriptor.key}. "
                "A permit is issued for one destination because the destination is part "
                "of what was decided; it cannot be reused against a different provider."
            )
        if not self._descriptor.accepts(permit.decision.input_sensitivity):
            raise SensitivityCeilingExceeded(
                f"{self._descriptor.key} may receive content up to "
                f"{self._descriptor.max_sensitivity.name}, but this permit carries "
                f"{permit.decision.input_sensitivity.name}"
            )
        return self._client.chat(permit.payload)
