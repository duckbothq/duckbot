"""Approval gates.

The rule from the plan: financial and destructive actions always require explicit human
approval, with no configuration option to disable it. That is enforced in the schemas by
``ALWAYS_REQUIRES_APPROVAL``; this service is where it becomes a gate rather than a fact.
"""

from __future__ import annotations

from duckbot_schemas import (
    Approval,
    ApprovalOutcome,
    AuditAction,
    RiskClass,
    utc_now,
)

from .audit_log import AuditLog
from .errors import ApprovalRequired, DuckbotError
from .store import ApprovalStore


class ApprovalGate:
    """Requests approvals, records decisions, and refuses to be talked around."""

    def __init__(
        self,
        store: ApprovalStore,
        audit: AuditLog,
        *,
        auto_approve: frozenset[RiskClass] = frozenset({RiskClass.READ}),
    ) -> None:
        """
        ``auto_approve`` is the set of risk classes that proceed without a human. Read is
        the sensible default. Financial and destructive are rejected here even if a caller
        passes them in — the configuration cannot be used to remove the gate, because a
        setting that can disable the control is the control.
        """
        forbidden = auto_approve & {RiskClass.FINANCIAL, RiskClass.DESTRUCTIVE}
        if forbidden:
            raise DuckbotError(
                f"{', '.join(sorted(r.value for r in forbidden))} can never be "
                "auto-approved; see the implementation plan, Section 11"
            )
        self._store = store
        self._audit = audit
        self._auto = auto_approve

    def request(
        self,
        *,
        task_id: str,
        risk_class: RiskClass,
        action_description: str,
        step_id: str | None = None,
        actor: str = "system",
    ) -> Approval:
        """Create an approval request and record it.

        ``action_description`` is shown to the person approving, in their own language.
        It is written for an office manager, not for the engineer who wrote the step.
        """
        approval = Approval(
            task_id=task_id,
            step_id=step_id,
            risk_class=risk_class,
            action_description=action_description,
        )
        self._store.put(approval)
        self._audit.record(
            actor=actor,
            action=AuditAction.APPROVAL_REQUESTED,
            task_id=task_id,
            approval_id=approval.id,
            detail=f"{risk_class.value}: {action_description}",
        )
        return approval

    def decide(
        self, approval_id: str, *, approved: bool, decided_by: str, reason: str | None = None
    ) -> Approval:
        """Record a human decision. Attribution is mandatory."""
        existing = self._store.get(approval_id)
        if existing is None:
            raise DuckbotError(f"no such approval: {approval_id}")
        if existing.outcome is not ApprovalOutcome.PENDING:
            raise DuckbotError(
                f"approval {approval_id} is already {existing.outcome.value}; "
                "an approval is decided once"
            )
        if not decided_by.strip():
            raise DuckbotError(
                "an approval must record who decided it; an unattributable approval is "
                "not evidence of oversight"
            )

        decided = existing.model_copy(
            update={
                "outcome": ApprovalOutcome.APPROVED if approved else ApprovalOutcome.REJECTED,
                "decided_by": decided_by,
                "decided_at": utc_now(),
                "decision_reason": reason,
            }
        )
        self._store.put(decided)
        self._audit.record(
            actor=decided_by,
            action=AuditAction.APPROVAL_DECIDED,
            task_id=decided.task_id,
            approval_id=decided.id,
            result="approved" if approved else "rejected",
            detail=reason,
        )
        return decided

    def require(
        self,
        *,
        task_id: str,
        risk_class: RiskClass,
        action_description: str,
        step_id: str | None = None,
    ) -> Approval | None:
        """Gate an action.

        Returns ``None`` when the risk class is auto-approved. Otherwise raises
        :class:`ApprovalRequired` carrying the approval id, so the caller stops and the
        user is asked. Call :meth:`check` once a decision exists.
        """
        if risk_class in self._auto and not Approval.is_mandatory(risk_class):
            return None
        approval = self.request(
            task_id=task_id,
            risk_class=risk_class,
            action_description=action_description,
            step_id=step_id,
        )
        raise ApprovalRequired(
            approval.id,
            f"human approval required for a {risk_class.value} action: {action_description}",
        )

    def check(self, approval_id: str) -> bool:
        """True only when a human approved. Pending is not approved."""
        approval = self._store.get(approval_id)
        if approval is None:
            raise DuckbotError(f"no such approval: {approval_id}")
        return approval.outcome is ApprovalOutcome.APPROVED
