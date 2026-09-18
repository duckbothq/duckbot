"""Storage interfaces, plus in-memory implementations for tests.

The schemas package deliberately has no persistence, so that the contracts survive the
storage choice changing. The core needs *some* persistence, so it defines protocols and
ships two implementations: in-memory for tests, and SQLite as the reference. Whoever
picks the real storage layer replaces the implementation, not the interface.
"""

from __future__ import annotations

from typing import Protocol

from duckbot_schemas import Approval, AuditEvent, PolicyDecision, Task


class TaskStore(Protocol):
    def put(self, task: Task) -> None: ...
    def get(self, task_id: str) -> Task | None: ...
    def list_all(self) -> list[Task]: ...


class ApprovalStore(Protocol):
    def put(self, approval: Approval) -> None: ...
    def get(self, approval_id: str) -> Approval | None: ...
    def pending_for_task(self, task_id: str) -> list[Approval]: ...


class PolicyDecisionStore(Protocol):
    def put(self, decision: PolicyDecision) -> None: ...
    def get(self, decision_id: str) -> PolicyDecision | None: ...


class AuditStore(Protocol):
    """Append-only. There is deliberately no update and no delete.

    An audit store that can rewrite history is not an audit store, and offering the
    method invites someone to use it during an incident, which is the worst moment.
    """

    def append(self, event: AuditEvent) -> None: ...
    def last(self) -> AuditEvent | None: ...
    def all_events(self) -> list[AuditEvent]: ...
    def count(self) -> int: ...


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._items: dict[str, Task] = {}

    def put(self, task: Task) -> None:
        self._items[task.id] = task

    def get(self, task_id: str) -> Task | None:
        return self._items.get(task_id)

    def list_all(self) -> list[Task]:
        return list(self._items.values())


class InMemoryApprovalStore:
    def __init__(self) -> None:
        self._items: dict[str, Approval] = {}

    def put(self, approval: Approval) -> None:
        self._items[approval.id] = approval

    def get(self, approval_id: str) -> Approval | None:
        return self._items.get(approval_id)

    def pending_for_task(self, task_id: str) -> list[Approval]:
        from duckbot_schemas import ApprovalOutcome

        return [
            a
            for a in self._items.values()
            if a.task_id == task_id and a.outcome is ApprovalOutcome.PENDING
        ]


class InMemoryPolicyDecisionStore:
    def __init__(self) -> None:
        self._items: dict[str, PolicyDecision] = {}

    def put(self, decision: PolicyDecision) -> None:
        self._items[decision.id] = decision

    def get(self, decision_id: str) -> PolicyDecision | None:
        return self._items.get(decision_id)


class InMemoryAuditStore:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self._events.append(event)

    def last(self) -> AuditEvent | None:
        return self._events[-1] if self._events else None

    def all_events(self) -> list[AuditEvent]:
        return list(self._events)

    def count(self) -> int:
        return len(self._events)
