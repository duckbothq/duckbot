"""A unit of work Duckbot was asked to do."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field, model_validator

from .common import (
    DuckbotModel,
    Money,
    RiskClass,
    TERMINAL_TASK_STATES,
    TaskState,
    new_id,
    utc_now,
)


class TaskStep(DuckbotModel):
    """One step in a task's execution."""

    id: str = Field(default_factory=lambda: new_id("step"))
    ordinal: int = Field(ge=0)
    description: str = Field(min_length=1)
    risk_class: RiskClass = RiskClass.READ

    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    succeeded: Optional[bool] = None
    approval_id: Optional[str] = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _times_ordered(self) -> "TaskStep":
        if self.finished_at and not self.started_at:
            raise ValueError("a step cannot finish without having started")
        if self.started_at and self.finished_at and self.finished_at < self.started_at:
            raise ValueError("a step cannot finish before it started")
        return self


class Task(DuckbotModel):
    """The record of one goal, from request to outcome.

    Cost totals live here rather than being recomputed, because the question a customer
    asks is "what did last month cost me", and answering it should not require replaying
    every model call.
    """

    id: str = Field(default_factory=lambda: new_id("task"))
    goal: str = Field(min_length=1)
    requester: str = Field(min_length=1)
    state: TaskState = TaskState.CREATED

    steps: list[TaskStep] = Field(default_factory=list)
    approval_ids: list[str] = Field(default_factory=list)
    audit_event_ids: list[str] = Field(default_factory=list)

    total_cost: Money = Field(default_factory=Money)
    model_calls: int = Field(default=0, ge=0)
    human_interventions: int = Field(default=0, ge=0)

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    finished_at: Optional[datetime] = None
    failure_reason: Optional[str] = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _terminal_state_is_explained(self) -> "Task":
        if self.state in TERMINAL_TASK_STATES and self.finished_at is None:
            raise ValueError(f"a task in state {self.state.value} must record finished_at")
        if self.state is TaskState.FAILED and not self.failure_reason:
            raise ValueError("a failed task must record why it failed")
        if self.state is not TaskState.FAILED and self.failure_reason:
            raise ValueError("only a failed task carries a failure reason")
        ordinals = [s.ordinal for s in self.steps]
        if len(ordinals) != len(set(ordinals)):
            raise ValueError("step ordinals must be unique within a task")
        return self
