"""Shared primitives for every Duckbot schema.

Two rules govern this package and are enforced by tests rather than by comment:

1. Every persisted record carries ``schema_version``. Migration discipline from the
   first commit costs days; retrofitting it costs months.
2. Real sensitive values never appear in a persisted or outbound record. The mapping
   between real values and placeholders lives only in
   :mod:`duckbot_schemas.placeholders`, which is deliberately not a serialisable model.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1
"""Package-wide schema version.

Bump on any breaking change to a persisted shape. Adding an optional field is not
breaking. Removing a field, renaming one, narrowing a type, or changing the meaning of
an existing value is breaking, and needs a migration written in the same pull request.
"""


def utc_now() -> datetime:
    """Timezone-aware UTC. Naive datetimes are rejected everywhere in this package."""
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    """Prefixed, sortable-enough identifier, e.g. ``task_9f2c1a...``.

    The prefix is for humans reading logs and audit exports at three in the morning.
    """
    return f"{prefix}_{secrets.token_hex(12)}"


class DuckbotModel(BaseModel):
    """Base for every schema in this package.

    ``extra="forbid"`` is deliberate: an unexpected field is a bug or a version skew,
    and silently accepting it is how sensitive data ends up somewhere it was never
    meant to be.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    schema_version: int = Field(default=SCHEMA_VERSION)


class SensitivityLevel(IntEnum):
    """Security levels, matching the context and privacy document, Section 9.

    The ordering is meaningful: a higher level is more restrictive, and comparisons
    such as ``level >= SensitivityLevel.DERIVE`` are used by the policy engine.
    """

    PUBLIC = 0
    MINIMIZE = 1
    ANONYMIZE = 2
    DERIVE = 3
    LOCAL_ONLY = 4


class DetectionMethod(StrEnum):
    RULE = "rule"
    MODEL = "model"
    MANUAL = "manual"


class PolicyAction(StrEnum):
    ALLOW = "allow"
    REDACT = "redact"
    DERIVE = "derive"
    LOCAL_ONLY = "local_only"
    BLOCK = "block"


class RiskClass(StrEnum):
    """Approval risk classes, matching the runtime document, Section 22."""

    READ = "read"
    WRITE = "write"
    EXTERNAL = "external"
    FINANCIAL = "financial"
    DESTRUCTIVE = "destructive"


ALWAYS_REQUIRES_APPROVAL: frozenset[RiskClass] = frozenset(
    {RiskClass.FINANCIAL, RiskClass.DESTRUCTIVE}
)
"""Financial and destructive actions always require explicit human approval in v1.

There is deliberately no configuration option to disable this. That option can be
considered when there is operational evidence, not before.
"""


class ModelTier(StrEnum):
    LOCAL = "local"
    LOW_COST = "low_cost"
    FRONTIER = "frontier"


class TaskState(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_TASK_STATES: frozenset[TaskState] = frozenset(
    {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}
)


class Money(DuckbotModel):
    """Cost, carried as a decimal string to avoid float drift in accumulated totals."""

    amount: str = Field(default="0", pattern=r"^-?\d+(\.\d+)?$")
    currency: str = Field(default="USD", min_length=3, max_length=3)

    def as_float(self) -> float:
        """For display and comparison only. Never accumulate totals in float."""
        return float(self.amount)


def _assert_aware(value: Any) -> Any:
    if isinstance(value, datetime) and value.tzinfo is None:
        raise ValueError("naive datetime is not permitted; use utc_now()")
    return value
