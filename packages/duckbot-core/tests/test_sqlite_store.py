"""The reference SQLite storage, including that it survives a restart."""

from __future__ import annotations

from pathlib import Path

import pytest
from duckbot_schemas import AuditAction, RiskClass, TaskState

from duckbot_core import (
    ApprovalGate,
    ApprovalRequired,
    AuditLog,
    Instruction,
    SqliteStores,
    TaskService,
)


def test_state_survives_a_restart(tmp_path: Path) -> None:
    db = tmp_path / "duckbot.db"

    with SqliteStores(db) as stores:
        log = AuditLog(stores.audit)
        svc = TaskService(stores.tasks, log)
        task = svc.create(Instruction(text="collect invoices", requester="richard"))
        svc.transition(task.id, TaskState.PLANNING)
        task_id = task.id

    with SqliteStores(db) as stores:
        log = AuditLog(stores.audit)
        svc = TaskService(stores.tasks, log)
        reopened = svc.get(task_id)
        assert reopened.state is TaskState.PLANNING
        log.verify()
        assert log.count == 2


def test_audit_chain_continues_across_restarts(tmp_path: Path) -> None:
    """The chain must not restart at genesis when the process does."""
    db = tmp_path / "duckbot.db"

    with SqliteStores(db) as stores:
        log = AuditLog(stores.audit)
        for _ in range(3):
            log.record(actor="richard", action=AuditAction.TASK_STATE_CHANGED)

    with SqliteStores(db) as stores:
        log = AuditLog(stores.audit)
        log.record(actor="richard", action=AuditAction.TASK_STATE_CHANGED)
        log.verify()
        assert log.count == 4
        assert log._store.all_events()[3].sequence == 3


def test_unsealed_events_are_refused(tmp_path: Path) -> None:
    from duckbot_schemas import AuditEvent

    with SqliteStores(tmp_path / "d.db") as stores, pytest.raises(ValueError):
        stores.audit.append(
            AuditEvent(sequence=0, actor="x", action=AuditAction.TASK_STATE_CHANGED)
        )


def test_pending_approvals_are_queryable(tmp_path: Path) -> None:
    with SqliteStores(tmp_path / "d.db") as stores:
        gate = ApprovalGate(stores.approvals, AuditLog(stores.audit))
        with pytest.raises(ApprovalRequired):
            gate.require(
                task_id="t1", risk_class=RiskClass.FINANCIAL, action_description="pay INV-1"
            )
        pending = stores.approvals.pending_for_task("t1")
        assert len(pending) == 1
        assert pending[0].risk_class is RiskClass.FINANCIAL
