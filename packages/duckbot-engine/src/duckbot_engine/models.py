"""Public request and result types for the task engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from duckbot_core import ApprovalStore, AuditStore, TaskStore, UntrustedContent
from duckbot_gateway import Attempt, Capability
from duckbot_memory import Budget, Exclusion
from duckbot_schemas import (
    Approval,
    ContentClassification,
    ModelCall,
    ModelTier,
    Money,
    PolicyAction,
    RiskClass,
    SensitivityLevel,
    Task,
    TaskState,
)


class StoreBundle(Protocol):
    """A core store bundle, structurally compatible with ``SqliteStores``."""

    @property
    def tasks(self) -> TaskStore: ...

    @property
    def approvals(self) -> ApprovalStore: ...

    @property
    def audit(self) -> AuditStore: ...


@dataclass(frozen=True)
class TaskRequest:
    """Everything needed to prepare one task.

    ``context`` is retrieved data, never an instruction. Requiring
    :class:`UntrustedContent` here preserves the prompt-injection boundary for file and
    connector work added above the engine.
    """

    instruction: str
    requester: str
    purpose: str = "general"
    risk_class: RiskClass = RiskClass.READ
    action_description: str | None = None
    budget: Budget = field(default_factory=lambda: Budget(max_tokens=4096, reserve_for_reply=1024))
    destination_ceiling: SensitivityLevel = SensitivityLevel.LOCAL_ONLY
    capabilities: frozenset[Capability] = field(
        default_factory=lambda: frozenset({Capability.TEXT})
    )
    prefer: ModelTier | None = None
    context: tuple[UntrustedContent, ...] = ()
    max_cost: Money | None = None

    def __post_init__(self) -> None:
        if not self.instruction.strip():
            raise ValueError("an instruction cannot be empty")
        if not self.requester.strip():
            raise ValueError("a requester is required")
        if not self.purpose.strip():
            raise ValueError("a purpose is required")
        if self.action_description is not None and not self.action_description.strip():
            raise ValueError("an action description cannot be blank")


@dataclass(frozen=True)
class TaskPreview:
    """The local pre-send view. It never carries the placeholder value map."""

    task_id: str
    state: TaskState
    destination: str
    destination_is_local: bool
    outbound_text: str | None
    classification: ContentClassification
    policy_action: PolicyAction | None
    policy_justification: str
    placeholder_tokens: tuple[str, ...]
    context_sources: tuple[str, ...]
    context_exclusions: tuple[Exclusion, ...]
    estimated_context_tokens: int
    estimated_cost: Money
    approval_required: bool
    risk_class: RiskClass


@dataclass(frozen=True)
class TaskResult:
    """A completed task, including its exact cost and fallback history."""

    task: Task
    preview: TaskPreview
    text: str
    raw_text: str
    model_call: ModelCall
    attempts: tuple[Attempt, ...]
    cost: Money
    cost_is_complete: bool


@dataclass(frozen=True)
class ApprovalPending:
    """Execution paused before the model/action boundary for a human decision."""

    task: Task
    preview: TaskPreview
    approval: Approval


@dataclass(frozen=True)
class TaskCancelled:
    """A task stopped because its requested approval was refused."""

    task: Task
    preview: TaskPreview
    approval: Approval


type EngineOutcome = TaskResult | ApprovalPending | TaskCancelled
