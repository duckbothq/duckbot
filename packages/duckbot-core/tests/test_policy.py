"""The outbound path."""

from __future__ import annotations

import pytest
from duckbot_schemas import (
    ContentClassification,
    DetectedEntity,
    DetectionMethod,
    PolicyAction,
    SensitivityLevel,
)

from duckbot_core import OutboundPermit, PolicyEngine, PolicyViolation, Rule


def _classified(level: SensitivityLevel, *entity_types: str) -> ContentClassification:
    return ContentClassification(
        content_id="c1",
        sensitivity=level,
        entities=[
            DetectedEntity(
                entity_type=t, start=0, end=5, confidence=0.99, method=DetectionMethod.RULE
            )
            for t in entity_types
        ],
    )


def test_a_permit_cannot_be_constructed_directly() -> None:
    """The gateway is on the outbound path, not beside it. This is that, in a test."""
    with pytest.raises(PolicyViolation):
        OutboundPermit(
            object(),
            decision=None,  # type: ignore[arg-type]
            payload="anything",
            destination="anthropic",
        )


def test_public_content_is_allowed_and_gets_a_permit() -> None:
    engine = PolicyEngine()
    decision, permit = engine.evaluate(
        _classified(SensitivityLevel.PUBLIC),
        destination="anthropic",
        redacted_payload="hello",
    )
    assert decision.action is PolicyAction.ALLOW
    assert permit is not None
    assert permit.payload == "hello"
    assert permit.destination == "anthropic"


def test_local_only_content_gets_no_permit() -> None:
    engine = PolicyEngine()
    decision, permit = engine.evaluate(
        _classified(SensitivityLevel.LOCAL_ONLY),
        destination="anthropic",
        redacted_payload="salary schedule",
    )
    assert decision.action is PolicyAction.LOCAL_ONLY
    assert permit is None
    assert decision.destination is None


def test_defaults_are_restrictive() -> None:
    """No matching rule must never mean 'allow'. A policy engine that fails open is how
    a product like this ends up in the news."""
    engine = PolicyEngine()
    for level, expected in [
        (SensitivityLevel.MINIMIZE, PolicyAction.REDACT),
        (SensitivityLevel.ANONYMIZE, PolicyAction.REDACT),
        (SensitivityLevel.DERIVE, PolicyAction.DERIVE),
        (SensitivityLevel.LOCAL_ONLY, PolicyAction.LOCAL_ONLY),
    ]:
        decision = engine.decide(_classified(level), "anthropic")
        assert decision.action is expected


def test_redaction_without_tokens_is_refused() -> None:
    """A redact decision with nothing redacted means sending the original."""
    engine = PolicyEngine()
    with pytest.raises(PolicyViolation):
        engine.evaluate(
            _classified(SensitivityLevel.MINIMIZE),
            destination="anthropic",
            redacted_payload="unchanged text",
            placeholder_tokens=[],
        )


def test_redaction_with_tokens_produces_a_permit() -> None:
    engine = PolicyEngine()
    decision, permit = engine.evaluate(
        _classified(SensitivityLevel.MINIMIZE),
        destination="anthropic",
        redacted_payload="Contact [PHONE_a1b2c3]",
        placeholder_tokens=["[PHONE_a1b2c3]"],
    )
    assert decision.action is PolicyAction.REDACT
    assert permit is not None
    assert permit.placeholder_tokens == ("[PHONE_a1b2c3]",)


def test_a_rule_can_block_by_entity_type() -> None:
    engine = PolicyEngine(
        [
            Rule(
                id="no-hkid-outbound",
                description="HKID never leaves, whatever the overall sensitivity",
                action=PolicyAction.BLOCK,
                entity_types=frozenset({"HKID"}),
            )
        ]
    )
    decision, permit = engine.evaluate(
        _classified(SensitivityLevel.PUBLIC, "HKID"),
        destination="anthropic",
        redacted_payload="x",
    )
    assert decision.action is PolicyAction.BLOCK
    assert decision.matched_rule_id == "no-hkid-outbound"
    assert permit is None


def test_a_rule_can_scope_to_a_destination() -> None:
    engine = PolicyEngine(
        [
            Rule(
                id="trusted-local",
                description="anything may go to the local model",
                action=PolicyAction.ALLOW,
                destinations=frozenset({"llama.cpp"}),
            )
        ]
    )
    allowed = engine.decide(_classified(SensitivityLevel.ANONYMIZE), "llama.cpp")
    assert allowed.action is PolicyAction.ALLOW
    elsewhere = engine.decide(_classified(SensitivityLevel.ANONYMIZE), "anthropic")
    assert elsewhere.action is PolicyAction.REDACT


def test_justification_is_present_and_human_readable() -> None:
    """It is shown on the pre-send screen, not written to a debug log."""
    engine = PolicyEngine()
    decision = engine.decide(_classified(SensitivityLevel.LOCAL_ONLY), None)
    assert decision.justification
    assert "local" in decision.justification.lower()
