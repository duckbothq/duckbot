"""What the policy engine decided, and the sentence the user is shown."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field, model_validator

from .common import DuckbotModel, PolicyAction, SensitivityLevel, new_id, utc_now


class PolicyDecision(DuckbotModel):
    """One decision about one piece of content going to one destination.

    ``justification`` is not a debug string. It is the sentence shown to the user on
    the pre-send screen, so it is written for the person whose data it is, in their
    language, and it is stored because a decision nobody can explain later is not a
    control.
    """

    id: str = Field(default_factory=lambda: new_id("pol"))
    classification_id: str = Field(min_length=1)
    input_sensitivity: SensitivityLevel
    action: PolicyAction
    destination: Optional[str] = Field(
        default=None,
        description="provider or model the content was bound for; None when blocked or local",
    )
    matched_rule_id: Optional[str] = Field(default=None, min_length=1)
    justification: str = Field(min_length=1)
    decided_at: datetime = Field(default_factory=utc_now)

    user_override: bool = Field(
        default=False, description="the user chose to send anyway"
    )
    override_reason: Optional[str] = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _coherent(self) -> "PolicyDecision":
        if self.action in (PolicyAction.BLOCK, PolicyAction.LOCAL_ONLY) and self.destination:
            raise ValueError(
                f"action {self.action.value} cannot carry an outbound destination"
            )
        if self.action in (PolicyAction.ALLOW, PolicyAction.REDACT) and not self.destination:
            raise ValueError(f"action {self.action.value} requires a destination")
        if self.user_override and not self.override_reason:
            raise ValueError("an override must record a reason")
        return self
