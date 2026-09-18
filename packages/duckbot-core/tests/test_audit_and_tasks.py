"""Audit log, task lifecycle, and approval gates."""

from __future__ import annotations

import pytest
from duckbot_schemas import (
    ApprovalOutcome,
    AuditAction,
    RiskClass,
    TaskState,
)

from duckbot_core import (
    ApprovalGate,
    ApprovalRequired,
    AuditChainBroken,
    AuditLog,
    DuckbotError,
    InMemoryApprovalStore,
    InMemoryAuditStore,
    InMemoryTaskStore,
    Instruction,
    TaskService,
)


def _audit() -> tuple[AuditLog, InMemoryAuditStore]:
    store = InMemoryAuditStore()
    return AuditLog(store), store


# --- audit log ------------------------------------------------------------------------


def test_sequences_and_chains_without_the_caller_thinking_about_it() -> None:
    log, _ = _audit()
    for i in range(5):
        log.record(actor="richard", action=AuditAction.TASK_STATE_CHANGED, detail=f"{i}")
    log.verify()
    assert log.count == 5


def test_verify_detects_tampering() -> None:
    log, store = _audit()
    for _ in range(3):
        log.record(actor="richard", action=AuditAction.TASK_STATE_CHANGED)
    store._events[1] = store._events[1].model_copy(update={"actor": "someone_else"})
    with pytest.raises(AuditChainBroken):
        log.verify()


def test_export_contains_no_sensitive_values() -> None:
    """An audit export that could leak what the product protects would be the product
    arguing against itself."""
    log, _ = _audit()
    log.record(
        actor="richard",
        action=AuditAction.SENT_TO_MODEL,
        destination="anthropic",
        placeholder_tokens=["[HKID_aa11bb]"],
        detail="quotation enquiry, 3 values redacted",
    )
    text = log.export_text()
    assert "anthropic" in text
    assert "[HKID_aa11bb]" not in text  # only the count is exported
    assert "tokens=1" in text


# --- tasks ----------------------------------------------------------------------------


def test_task_lifecycle_is_audited() -> None:
    log, _ = _audit()
    svc = TaskService(InMemoryTaskStore(), log)
    task = svc.create(Instruction(text="prepare the quotation", requester="richard"))
    assert task.state is TaskState.CREATED

    svc.transition(task.id, TaskState.PLANNING)
    svc.transition(task.id, TaskState.RUNNING)
    done = svc.transition(task.id, TaskState.COMPLETED)

    assert done.state is TaskState.COMPLETED
    assert done.finished_at is not None
    log.verify()
    assert log.count == 4  # creation plus three transitions


def test_illegal_transitions_are_refused() -> None:
    log, _ = _audit()
    svc = TaskService(InMemoryTaskStore(), log)
    task = svc.create(Instruction(text="x", requester="r"))
    with pytest.raises(DuckbotError):
        svc.transition(task.id, TaskState.COMPLETED)  # created -> completed


def test_terminal_states_are_terminal() -> None:
    """A task that can be resurrected makes its own audit trail ambiguous."""
    log, _ = _audit()
    svc = TaskService(InMemoryTaskStore(), log)
    task = svc.create(Instruction(text="x", requester="r"))
    svc.transition(task.id, TaskState.CANCELLED)
    with pytest.raises(DuckbotError):
        svc.transition(task.id, TaskState.RUNNING)


def test_failure_must_be_explained() -> None:
    log, _ = _audit()
    svc = TaskService(InMemoryTaskStore(), log)
    task = svc.create(Instruction(text="x", requester="r"))
    svc.transition(task.id, TaskState.PLANNING)
    with pytest.raises(DuckbotError):
        svc.transition(task.id, TaskState.FAILED)


def test_costs_accumulate_without_float_drift() -> None:
    log, _ = _audit()
    svc = TaskService(InMemoryTaskStore(), log)
    task = svc.create(Instruction(text="x", requester="r"))
    for _ in range(10):
        svc.record_cost(task.id, "0.01")
    assert svc.get(task.id).total_cost.amount == "0.10"
    assert svc.get(task.id).model_calls == 10


# --- approvals ------------------------------------------------------------------------


def _gate() -> tuple[ApprovalGate, AuditLog]:
    log, _ = _audit()
    return ApprovalGate(InMemoryApprovalStore(), log), log


def test_financial_and_destructive_can_never_be_auto_approved() -> None:
    """A setting that can disable the control is the control."""
    log, _ = _audit()
    for risk in (RiskClass.FINANCIAL, RiskClass.DESTRUCTIVE):
        with pytest.raises(DuckbotError):
            ApprovalGate(
                InMemoryApprovalStore(), log, auto_approve=frozenset({RiskClass.READ, risk})
            )


def test_read_passes_without_a_human() -> None:
    gate, _ = _gate()
    assert (
        gate.require(task_id="t1", risk_class=RiskClass.READ, action_description="read a file")
        is None
    )


def test_financial_action_stops_and_asks() -> None:
    gate, _ = _gate()
    with pytest.raises(ApprovalRequired) as excinfo:
        gate.require(
            task_id="t1",
            risk_class=RiskClass.FINANCIAL,
            action_description="pay supplier invoice INV-2026-0912",
        )
    assert excinfo.value.approval_id
    assert gate.check(excinfo.value.approval_id) is False  # pending is not approved


def test_approval_records_who_and_why() -> None:
    gate, log = _gate()
    with pytest.raises(ApprovalRequired) as excinfo:
        gate.require(
            task_id="t1", risk_class=RiskClass.EXTERNAL, action_description="send the quotation"
        )
    approval_id = excinfo.value.approval_id
    decided = gate.decide(
        approval_id, approved=True, decided_by="richard", reason="checked figures"
    )
    assert decided.outcome is ApprovalOutcome.APPROVED
    assert decided.decided_by == "richard"
    assert decided.decided_at is not None
    assert gate.check(approval_id) is True
    log.verify()


def test_an_approval_is_decided_once() -> None:
    gate, _ = _gate()
    with pytest.raises(ApprovalRequired) as excinfo:
        gate.require(task_id="t1", risk_class=RiskClass.WRITE, action_description="overwrite")
    approval_id = excinfo.value.approval_id
    gate.decide(approval_id, approved=False, decided_by="richard")
    with pytest.raises(DuckbotError):
        gate.decide(approval_id, approved=True, decided_by="richard")


def test_an_approval_must_be_attributable() -> None:
    gate, _ = _gate()
    with pytest.raises(ApprovalRequired) as excinfo:
        gate.require(task_id="t1", risk_class=RiskClass.WRITE, action_description="overwrite")
    with pytest.raises(DuckbotError):
        gate.decide(excinfo.value.approval_id, approved=True, decided_by="   ")
