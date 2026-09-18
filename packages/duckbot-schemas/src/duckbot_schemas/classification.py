"""What was found in a piece of content, and how sensitive it is."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from .common import (
    DetectionMethod,
    DuckbotModel,
    SensitivityLevel,
    new_id,
    utc_now,
)


class DetectedEntity(DuckbotModel):
    """One detection inside a piece of content.

    Note what is absent: the raw value. An entity records *where* something was found
    and *what token replaced it*, never the value itself. The value exists only in the
    :class:`~duckbot_schemas.placeholders.PlaceholderMap`, in memory, on this machine.
    """

    entity_type: str = Field(min_length=1, description="e.g. HKID, PHONE, PERSON_NAME")
    start: int = Field(ge=0, description="character offset, inclusive")
    end: int = Field(gt=0, description="character offset, exclusive")
    confidence: float = Field(ge=0.0, le=1.0)
    method: DetectionMethod
    placeholder_token: str | None = Field(
        default=None, description="token substituted for this value, if it was replaced"
    )

    @model_validator(mode="after")
    def _offsets_ordered(self) -> DetectedEntity:
        if self.end <= self.start:
            raise ValueError("end offset must be greater than start offset")
        return self


class ContentClassification(DuckbotModel):
    """The classification of one piece of content, at one point in time."""

    id: str = Field(default_factory=lambda: new_id("cls"))
    content_id: str = Field(min_length=1)
    sensitivity: SensitivityLevel
    entities: list[DetectedEntity] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=utc_now)

    reviewer_override: SensitivityLevel | None = Field(
        default=None,
        description="a human disagreed with the automatic classification",
    )
    override_reason: str | None = Field(default=None, min_length=1)
    overridden_by: str | None = Field(default=None, min_length=1)

    @field_validator("detected_at")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("naive datetime is not permitted; use utc_now()")
        return v

    @model_validator(mode="after")
    def _override_is_accountable(self) -> ContentClassification:
        if self.reviewer_override is not None and (
            not self.override_reason or not self.overridden_by
        ):
            raise ValueError(
                "an override must record who made it and why; "
                "an unattributable override is worse than none"
            )
        return self

    @property
    def effective_sensitivity(self) -> SensitivityLevel:
        """What the policy engine acts on: the human's view wins if there is one."""
        return self.reviewer_override if self.reviewer_override is not None else self.sensitivity
