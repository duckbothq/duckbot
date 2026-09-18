"""The permit boundary at the adapter layer.

These tests are about what is *impossible*, not about what works. The value of the two
adapter types is that a caller cannot send content to a hosted provider by forgetting a
step, and that is only true if the wrappers refuse the cases below.
"""

from __future__ import annotations

import pytest
from duckbot_core import PolicyEngine
from duckbot_schemas import ModelTier, SensitivityLevel

from duckbot_gateway import (
    AdapterFailure,
    EchoClient,
    FailingClient,
    LocalAdapter,
    ModelDescriptor,
    RemoteAdapter,
    SensitivityCeilingExceeded,
)
from duckbot_gateway.adapters.base import Completion
from helpers import classification


def permit_for(destination: str, level: SensitivityLevel, payload: str = "redacted"):
    engine = PolicyEngine()
    tokens = () if level is SensitivityLevel.PUBLIC else ("[PERSON_NAME_aaaaaa]",)
    _, permit = engine.evaluate(
        classification(level),
        destination=destination,
        redacted_payload=payload,
        placeholder_tokens=tokens,
    )
    assert permit is not None
    return permit


class TestWrappingRules:
    def test_a_hosted_model_cannot_be_wrapped_as_local(
        self, cheap_descriptor: ModelDescriptor
    ) -> None:
        with pytest.raises(ValueError, match="not local"):
            LocalAdapter(cheap_descriptor, EchoClient())

    def test_a_local_model_cannot_be_wrapped_as_remote(
        self, local_descriptor: ModelDescriptor
    ) -> None:
        with pytest.raises(ValueError, match="local model"):
            RemoteAdapter(local_descriptor, EchoClient())


class TestLocalAdapter:
    def test_it_takes_text_because_nothing_leaves(self, local_descriptor: ModelDescriptor) -> None:
        client = EchoClient(label="local")
        adapter = LocalAdapter(local_descriptor, client)
        result = adapter.complete("身份證 A123456(3)", purpose="classification")
        assert "A123456(3)" in result.text
        assert client.calls == ["身份證 A123456(3)"]


class TestRemoteAdapter:
    def test_it_sends_the_permit_payload_and_nothing_else(
        self, cheap_descriptor: ModelDescriptor
    ) -> None:
        """If policy decided to redact, the redacted payload is what goes."""
        client = EchoClient()
        adapter = RemoteAdapter(cheap_descriptor, client)
        permit = permit_for(cheap_descriptor.key, SensitivityLevel.ANONYMIZE, "客戶 [NAME_1]")
        adapter.complete(permit, purpose="drafting")
        assert client.calls == ["客戶 [NAME_1]"]

    def test_a_permit_cannot_be_reused_against_another_provider(
        self, cheap_descriptor: ModelDescriptor, frontier_descriptor: ModelDescriptor
    ) -> None:
        """The destination is part of what was decided, not a label on the decision."""
        adapter = RemoteAdapter(frontier_descriptor, EchoClient())
        permit = permit_for(cheap_descriptor.key, SensitivityLevel.ANONYMIZE)
        with pytest.raises(SensitivityCeilingExceeded, match="cannot be reused"):
            adapter.complete(permit, purpose="drafting")

    def test_content_above_the_ceiling_is_refused(self) -> None:
        """A second lock, on the other side of the one the router already holds."""
        descriptor = ModelDescriptor(
            provider="example-strict",
            model="public-only",
            tier=ModelTier.LOW_COST,
            context_window=8000,
            max_sensitivity=SensitivityLevel.PUBLIC,
        )
        adapter = RemoteAdapter(descriptor, EchoClient())
        permit = permit_for(descriptor.key, SensitivityLevel.ANONYMIZE)
        with pytest.raises(SensitivityCeilingExceeded, match="may receive content up to"):
            adapter.complete(permit, purpose="drafting")

    def test_an_adapter_failure_propagates(self, cheap_descriptor: ModelDescriptor) -> None:
        adapter = RemoteAdapter(cheap_descriptor, FailingClient("503 from provider"))
        permit = permit_for(cheap_descriptor.key, SensitivityLevel.ANONYMIZE)
        with pytest.raises(AdapterFailure, match="503"):
            adapter.complete(permit, purpose="drafting")


class TestCompletion:
    def test_negative_figures_are_refused(self) -> None:
        with pytest.raises(ValueError):
            Completion(text="x", tokens_in=-1)

    def test_token_counts_default_to_zero_rather_than_an_estimate(self) -> None:
        """Zero says "the provider did not tell us". An estimate would read as a measurement."""
        assert Completion(text="x").tokens_in == 0
