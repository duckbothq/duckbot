"""Task lifecycle."""

from __future__ import annotations

from duckbot_schemas import (
    AuditAction,
    Money,
    Task,
    TaskState,
    TaskStep,
    utc_now,
)

from .audit_log import AuditLog
from .content import Instruction
from .errors import DuckbotError
from .store import TaskStore

_ALLOWED_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.CREATED: frozenset({TaskState.PLANNING, TaskState.CANCELLED, TaskState.FAILED}),
    TaskState.PLANNING: frozenset({TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED}),
    TaskState.RUNNING: frozenset(
        {
            TaskState.AWAITING_APPROVAL,
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.AWAITING_APPROVAL: frozenset(
        {TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED}
    ),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}
"""Terminal states are terminal. A task that can be resurrected makes its own audit
trail ambiguous, which defeats the purpose of having one."""


class TaskService:
    def __init__(self, store: TaskStore, audit: AuditLog) -> None:
        self._store = store
        self._audit = audit

    def create(self, instruction: Instruction) -> Task:
        task = Task(goal=instruction.text, requester=instruction.requester)
        self._store.put(task)
        self._audit.record(
            actor=instruction.requester,
            action=AuditAction.TASK_STATE_CHANGED,
            task_id=task.id,
            detail=f"created: {TaskState.CREATED.value}",
        )
        return task

    def get(self, task_id: str) -> Task:
        task = self._store.get(task_id)
        if task is None:
            raise DuckbotError(f"no such task: {task_id}")
        return task

    def transition(
        self,
        task_id: str,
        new_state: TaskState,
        *,
        actor: str = "system",
        failure_reason: str | None = None,
    ) -> Task:
        task = self.get(task_id)
        if new_state not in _ALLOWED_TRANSITIONS[task.state]:
            raise DuckbotError(f"cannot move a task from {task.state.value} to {new_state.value}")

        update: dict[str, object] = {"state": new_state, "updated_at": utc_now()}
        if new_state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
            update["finished_at"] = utc_now()
        if new_state is TaskState.FAILED:
            if not failure_reason:
                raise DuckbotError("a failed task must record why it failed")
            update["failure_reason"] = failure_reason

        updated = task.model_copy(update=update)
        self._store.put(updated)
        self._audit.record(
            actor=actor,
            action=AuditAction.TASK_STATE_CHANGED,
            task_id=task.id,
            result=new_state.value,
            detail=failure_reason,
        )
        return updated

    def add_step(self, task_id: str, step: TaskStep) -> Task:
        task = self.get(task_id)
        updated = task.model_copy(update={"steps": [*task.steps, step], "updated_at": utc_now()})
        self._store.put(updated)
        return updated

    def record_cost(self, task_id: str, amount: str, *, currency: str = "USD") -> Task:
        """Accumulate cost as decimal strings, never floats.

        The question a customer asks is "what did last month cost me", and answering it
        should not involve explaining floating point.
        """
        from decimal import Decimal

        task = self.get(task_id)
        if task.total_cost.currency != currency:
            raise DuckbotError(f"task totals are in {task.total_cost.currency}; got {currency}")
        total = Decimal(task.total_cost.amount) + Decimal(amount)
        updated = task.model_copy(
            update={
                "total_cost": Money(amount=str(total), currency=currency),
                "model_calls": task.model_calls + 1,
                "updated_at": utc_now(),
            }
        )
        self._store.put(updated)
        return updated
