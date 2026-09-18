"""Tests for the Duckbot schema contracts.

These are contract tests, not coverage theatre. Each one guards a decision that would be
expensive to discover was wrong later.
"""

from datetime import timedelta

import pytest
from pydantic import BaseModel, ValidationError

from duckbot_schemas import (
    Approval,
    ApprovalOutcome,
    AuditAction,
    AuditEvent,
    ContentClassification,
    DetectedEntity,
    DetectionMethod,
    ModelCall,
    ModelTier,
    Money,
    PlaceholderMap,
    PolicyAction,
    PolicyDecision,
    RiskClass,
    SCHEMA_VERSION,
    SensitivityLevel,
    Task,
    TaskState,
    TaskStep,
    MemoryItem,
    utc_now,
    verify_chain,
)
import duckbot_schemas


# --- the structural privacy guarantee -------------------------------------------------

def test_placeholder_map_is_not_serialisable():
    """The mapping of token to real value must not be a serialisable model.

    If someone makes PlaceholderMap a pydantic model, it becomes possible to dump it
    into an audit record or an outbound payload. This test is the alarm.
    """
    assert not issubclass(PlaceholderMap, BaseModel)
    assert not hasattr(PlaceholderMap, "model_dump")


def test_placeholder_map_repr_withholds_values():
    pm = PlaceholderMap()
    pm.token_for("CHAN Ka Man", "person_name")
    assert "CHAN Ka Man" not in repr(pm)
    assert "CHAN Ka Man" not in str(pm)


def test_placeholder_tokens_are_stable_within_a_document():
    """The same person mentioned three times must become the same token."""
    pm = PlaceholderMap()
    first = pm.token_for("CHAN Ka Man", "person_name")
    second = pm.token_for("CHAN Ka Man", "person_name")
    assert first == second
    assert len(pm) == 1


def test_restore_puts_real_values_back():
    pm = PlaceholderMap()
    token = pm.token_for("9876 5432", "phone")
    assert pm.restore(f"Call {token} tomorrow") == "Call 9876 5432 tomorrow"


def test_no_schema_field_can_hold_a_placeholder_map():
    """No exported model may declare a field typed to carry the map."""
    for name in duckbot_schemas.__all__:
        obj = getattr(duckbot_schemas, name)
        if isinstance(obj, type) and issubclass(obj, BaseModel):
            for field in obj.model_fields.values():
                assert field.annotation is not PlaceholderMap, (
                    f"{name} declares a PlaceholderMap field"
                )


# --- versioning -----------------------------------------------------------------------

def test_every_model_carries_a_schema_version():
    """Checked on the field definition, not by instantiating — most models have
    required fields, and a test that constructs them would be testing the wrong thing."""
    checked = 0
    for name in duckbot_schemas.__all__:
        obj = getattr(duckbot_schemas, name)
        if isinstance(obj, type) and issubclass(obj, BaseModel):
            assert "schema_version" in obj.model_fields, f"{name} has no schema_version"
            assert obj.model_fields["schema_version"].default == SCHEMA_VERSION, (
                f"{name} defaults to a different schema version"
            )
            checked += 1
    assert checked >= 8, "expected every exported model to be checked"


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        Money(amount="1", currency="USD", surprise=True)


def test_naive_datetime_is_rejected():
    from datetime import datetime

    with pytest.raises(ValidationError):
        ContentClassification(
            content_id="c1",
            sensitivity=SensitivityLevel.PUBLIC,
            detected_at=datetime(2026, 9, 18, 12, 0, 0),
        )


# --- classification -------------------------------------------------------------------

def test_detected_entity_carries_no_raw_value():
    assert "value" not in DetectedEntity.model_fields
    assert "text" not in DetectedEntity.model_fields


def test_entity_offsets_must_be_ordered():
    with pytest.raises(ValidationError):
        DetectedEntity(
            entity_type="HKID", start=10, end=5, confidence=0.9, method=DetectionMethod.RULE
        )


def test_override_must_be_attributable():
    with pytest.raises(ValidationError):
        ContentClassification(
            content_id="c1",
            sensitivity=SensitivityLevel.LOCAL_ONLY,
            reviewer_override=SensitivityLevel.PUBLIC,
        )


def test_human_override_wins():
    c = ContentClassification(
        content_id="c1",
        sensitivity=SensitivityLevel.LOCAL_ONLY,
        reviewer_override=SensitivityLevel.MINIMIZE,
        override_reason="internal template, no client data",
        overridden_by="richard",
    )
    assert c.effective_sensitivity is SensitivityLevel.MINIMIZE


# --- policy ---------------------------------------------------------------------------

def test_blocked_content_cannot_have_a_destination():
    with pytest.raises(ValidationError):
        PolicyDecision(
            classification_id="cls_1",
            input_sensitivity=SensitivityLevel.LOCAL_ONLY,
            action=PolicyAction.BLOCK,
            destination="openai",
            justification="contains an HKID",
        )


def test_allowed_content_requires_a_destination():
    with pytest.raises(ValidationError):
        PolicyDecision(
            classification_id="cls_1",
            input_sensitivity=SensitivityLevel.PUBLIC,
            action=PolicyAction.ALLOW,
            justification="nothing sensitive detected",
        )


def test_user_override_requires_a_reason():
    with pytest.raises(ValidationError):
        PolicyDecision(
            classification_id="cls_1",
            input_sensitivity=SensitivityLevel.ANONYMIZE,
            action=PolicyAction.REDACT,
            destination="anthropic",
            justification="names removed",
            user_override=True,
        )


# --- model calls ----------------------------------------------------------------------

def test_local_model_calls_are_free():
    with pytest.raises(ValidationError):
        ModelCall(
            provider="llama.cpp",
            model="qwen",
            tier=ModelTier.LOCAL,
            purpose="classification",
            cost=Money(amount="0.02"),
            max_sensitivity_permitted=SensitivityLevel.LOCAL_ONLY,
        )


def test_failed_call_must_say_why():
    with pytest.raises(ValidationError):
        ModelCall(
            provider="x",
            model="y",
            tier=ModelTier.FRONTIER,
            purpose="drafting",
            max_sensitivity_permitted=SensitivityLevel.MINIMIZE,
            succeeded=False,
        )


# --- memory ---------------------------------------------------------------------------

def test_local_only_memory_cannot_be_embedded_remotely():
    with pytest.raises(ValidationError):
        MemoryItem(
            source="file",
            text="staff salary schedule",
            sensitivity=SensitivityLevel.LOCAL_ONLY,
            embedded_remotely=True,
        )


# --- approval -------------------------------------------------------------------------

def test_financial_and_destructive_always_require_approval():
    assert Approval.is_mandatory(RiskClass.FINANCIAL)
    assert Approval.is_mandatory(RiskClass.DESTRUCTIVE)
    assert not Approval.is_mandatory(RiskClass.READ)


def test_decided_approval_must_be_attributable():
    with pytest.raises(ValidationError):
        Approval(
            task_id="task_1",
            risk_class=RiskClass.EXTERNAL,
            action_description="send the quotation to the customer",
            outcome=ApprovalOutcome.APPROVED,
        )


def test_pending_approval_cannot_have_a_decider():
    with pytest.raises(ValidationError):
        Approval(
            task_id="task_1",
            risk_class=RiskClass.WRITE,
            action_description="update the spreadsheet",
            decided_by="richard",
        )


# --- audit ----------------------------------------------------------------------------

def _chain(n: int) -> list[AuditEvent]:
    events: list[AuditEvent] = []
    prev = "0" * 64
    for i in range(n):
        e = AuditEvent(
            sequence=i,
            actor="richard",
            action=AuditAction.SENT_TO_MODEL,
            destination="anthropic",
            prev_hash=prev,
        ).sealed()
        events.append(e)
        prev = e.entry_hash
    return events


def test_audit_chain_verifies_when_intact():
    assert verify_chain(_chain(5)) == (True, None)


def test_audit_chain_detects_tampering():
    events = _chain(5)
    events[2] = events[2].model_copy(update={"actor": "someone_else"})
    ok, seq = verify_chain(events)
    assert ok is False and seq == 2


def test_audit_chain_detects_a_removed_entry():
    events = _chain(5)
    del events[2]
    ok, seq = verify_chain(events)
    assert ok is False and seq == 3


def test_unsealed_entry_does_not_verify():
    e = AuditEvent(sequence=0, actor="system", action=AuditAction.TASK_STATE_CHANGED)
    assert verify_chain([e]) == (False, 0)


def test_outbound_event_must_record_destination():
    with pytest.raises(ValidationError):
        AuditEvent(sequence=0, actor="system", action=AuditAction.SENT_TO_MODEL)


def test_audit_event_has_no_raw_value_field():
    for forbidden in ("value", "content", "payload", "text"):
        assert forbidden not in AuditEvent.model_fields


# --- task -----------------------------------------------------------------------------

def test_failed_task_must_record_a_reason():
    with pytest.raises(ValidationError):
        Task(goal="g", requester="r", state=TaskState.FAILED, finished_at=utc_now())


def test_terminal_task_must_record_finished_at():
    with pytest.raises(ValidationError):
        Task(goal="g", requester="r", state=TaskState.COMPLETED)


def test_step_ordinals_must_be_unique():
    with pytest.raises(ValidationError):
        Task(
            goal="g",
            requester="r",
            steps=[
                TaskStep(ordinal=0, description="a"),
                TaskStep(ordinal=0, description="b"),
            ],
        )


def test_step_cannot_finish_before_it_starts():
    now = utc_now()
    with pytest.raises(ValidationError):
        TaskStep(
            ordinal=0,
            description="x",
            started_at=now,
            finished_at=now - timedelta(seconds=1),
        )
