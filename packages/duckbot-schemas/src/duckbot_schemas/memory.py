"""Local memory: what Duckbot remembers, and for how long."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from .common import DuckbotModel, SensitivityLevel, new_id, utc_now


class MemoryScope(StrEnum):
    USER = "user"
    TEAM = "team"
    ORGANISATION = "organisation"


class RetentionPolicy(StrEnum):
    SESSION = "session"
    DAYS_30 = "days_30"
    DAYS_365 = "days_365"
    INDEFINITE = "indefinite"


class MemoryItem(DuckbotModel):
    """One durable memory, held locally.

    A memory classified at ``LOCAL_ONLY`` may never be embedded by a remote service.
    That is enforced here rather than left to the retrieval layer, because the
    retrieval layer is where such a rule is most likely to be forgotten.
    """

    id: str = Field(default_factory=lambda: new_id("mem"))
    source: str = Field(min_length=1, description="where this came from: file, email, chat")
    scope: MemoryScope = MemoryScope.USER
    text: str = Field(min_length=1)

    embedding_ref: str | None = Field(
        default=None, description="pointer into the local vector index, never the vector"
    )
    embedded_remotely: bool = Field(
        default=False, description="whether a remote service produced the embedding"
    )

    sensitivity: SensitivityLevel = SensitivityLevel.MINIMIZE
    retention: RetentionPolicy = RetentionPolicy.DAYS_365

    created_at: datetime = Field(default_factory=utc_now)
    last_used_at: datetime | None = None

    @model_validator(mode="after")
    def _local_only_stays_local(self) -> MemoryItem:
        if self.sensitivity is SensitivityLevel.LOCAL_ONLY and self.embedded_remotely:
            raise ValueError("a LOCAL_ONLY memory cannot have been embedded by a remote service")
        return self
