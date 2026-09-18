"""Human approval: the gate, and the record that it was passed."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field, model_validator

from .common import (
    ALWAYS_REQUIRES_APPROVAL,
    DuckbotModel,
    RiskClass,
    new_id,
    utc_now,
)


class ApprovalOutcome(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Approval(DuckbotModel):
    """A request for a human to approve an action, and the answer.

    ``action_description`` is in plain language because the person approving is an
    office manager, not the engineer who wrote the step. An approval prompt that cannot
    be understood is a rubber stamp, and a rubber stamp is worse than no gate at all:
    it produces a record implying oversight that did not happen.
    """

    id: str = Field(default_factory=lambda: new_id("apr"))
    task_id: str = Field(min_length=1)
    step_id: Optional[str] = Field(default=None, min_length=1)

    risk_class: RiskClass
    action_description: str = Field(
        min_length=1, description="plain language, in the user's own language"
    )
    requested_at: datetime = Field(default_factory=utc_now)

    outcome: ApprovalOutcome = ApprovalOutcome.PENDING
    decided_by: Optional[str] = Field(default=None, min_length=1)
    decided_at: Optional[datetime] = None
    decision_reason: Optional[str] = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _decided_means_attributed(self) -> "Approval":
        decided = self.outcome in (ApprovalOutcome.APPROVED, ApprovalOutcome.REJECTED)
        if decided and (not self.decided_by or self.decided_at is None):
            raise ValueError(
                "a decided approval must record who decided and when; "
                "an unattributable approval is not evidence of oversight"
            )
        if not decided and (self.decided_by or self.decided_at):
            raise ValueError("a pending or expired approval cannot carry a decider")
        return self

    @staticmethod
    def is_mandatory(risk_class: RiskClass) -> bool:
        """Financial and destructive always require approval in v1. No configuration."""
        return risk_class in ALWAYS_REQUIRES_APPROVAL
