"""Descriptors, and the one thing configuration must not be allowed to say."""

from __future__ import annotations

import pytest
from duckbot_schemas import ModelTier, SensitivityLevel

from duckbot_gateway import Capability, ModelDescriptor


def test_a_hosted_model_cannot_declare_itself_fit_for_local_only() -> None:
    """LOCAL_ONLY is a statement about where the bytes go, not about how good the model is."""
    with pytest.raises(ValueError, match="does not leave this machine"):
        ModelDescriptor(
            provider="example-frontier",
            model="big-1",
            tier=ModelTier.FRONTIER,
            context_window=200_000,
            max_sensitivity=SensitivityLevel.LOCAL_ONLY,
        )


def test_a_local_model_may(local_descriptor: ModelDescriptor) -> None:
    assert local_descriptor.max_sensitivity is SensitivityLevel.LOCAL_ONLY


def test_accepts_is_a_ceiling(cheap_descriptor: ModelDescriptor) -> None:
    assert cheap_descriptor.accepts(SensitivityLevel.PUBLIC)
    assert cheap_descriptor.accepts(SensitivityLevel.ANONYMIZE)
    assert not cheap_descriptor.accepts(SensitivityLevel.DERIVE)
    assert not cheap_descriptor.accepts(SensitivityLevel.LOCAL_ONLY)


def test_capabilities_must_all_be_present(frontier_descriptor: ModelDescriptor) -> None:
    assert frontier_descriptor.supports(frozenset({Capability.TEXT, Capability.VISION}))
    assert not frontier_descriptor.supports(frozenset({Capability.STRUCTURED_OUTPUT}))


def test_the_key_is_what_appears_in_logs(cheap_descriptor: ModelDescriptor) -> None:
    assert cheap_descriptor.key == "example-cheap/fast-1"


@pytest.mark.parametrize(
    ("provider", "model", "window"),
    [("", "m", 100), ("p", "", 100), ("p", "m", 0), ("p", "m", -1)],
)
def test_incoherent_descriptors_are_refused(provider: str, model: str, window: int) -> None:
    with pytest.raises(ValueError):
        ModelDescriptor(
            provider=provider,
            model=model,
            tier=ModelTier.LOW_COST,
            context_window=window,
            max_sensitivity=SensitivityLevel.PUBLIC,
        )
