"""One call to one model, with what it cost and what it was allowed to see."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from .common import DuckbotModel, ModelTier, Money, SensitivityLevel, new_id, utc_now


class ModelCall(DuckbotModel):
    """A single model invocation.

    ``max_sensitivity_permitted`` records the ceiling that applied to this call, so an
    auditor can see not only what was sent but what the system believed it was allowed
    to send. ``fallback_chain`` records what was tried before this succeeded, because
    "it worked" and "it worked first time" are different operational facts.
    """

    id: str = Field(default_factory=lambda: new_id("mcall"))
    task_id: str | None = Field(default=None, min_length=1)
    policy_decision_id: str | None = Field(default=None, min_length=1)

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    tier: ModelTier
    purpose: str = Field(min_length=1, description="classification, extraction, drafting, ...")

    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    cost: Money = Field(default_factory=Money)
    latency_ms: int = Field(default=0, ge=0)

    max_sensitivity_permitted: SensitivityLevel
    fallback_chain: list[str] = Field(
        default_factory=list, description="providers tried before this one, in order"
    )

    succeeded: bool = True
    error: str | None = Field(default=None, min_length=1)
    called_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _local_is_free_and_unrestricted(self) -> ModelCall:
        if not self.succeeded and not self.error:
            raise ValueError("a failed call must record why it failed")
        if self.succeeded and self.error:
            raise ValueError("a successful call cannot carry an error")
        if self.tier is ModelTier.LOCAL and self.cost.as_float() != 0.0:
            raise ValueError("a local model call has no per-call cost")
        return self
