"""Duckbot schemas — the contracts every other module is built against.

Defined in Phase 0 deliberately, before any feature code, so that later modules cannot
become tightly coupled by accident. See the implementation plan, Sections 7 and 8.
"""

from .approval import Approval, ApprovalOutcome
from .audit import GENESIS_HASH, AuditAction, AuditEvent, verify_chain
from .classification import ContentClassification, DetectedEntity
from .common import (
    ALWAYS_REQUIRES_APPROVAL,
    SCHEMA_VERSION,
    TERMINAL_TASK_STATES,
    DetectionMethod,
    DuckbotModel,
    ModelTier,
    Money,
    PolicyAction,
    RiskClass,
    SensitivityLevel,
    TaskState,
    new_id,
    utc_now,
)
from .memory import MemoryItem, MemoryScope, RetentionPolicy
from .model_request import ModelCall
from .placeholders import PlaceholderMap
from .policy import PolicyDecision
from .task import Task, TaskStep

__all__ = [
    "ALWAYS_REQUIRES_APPROVAL",
    "GENESIS_HASH",
    "SCHEMA_VERSION",
    "TERMINAL_TASK_STATES",
    "Approval",
    "ApprovalOutcome",
    "AuditAction",
    "AuditEvent",
    "ContentClassification",
    "DetectedEntity",
    "DetectionMethod",
    "DuckbotModel",
    "MemoryItem",
    "MemoryScope",
    "ModelCall",
    "ModelTier",
    "Money",
    "PlaceholderMap",
    "PolicyAction",
    "PolicyDecision",
    "RetentionPolicy",
    "RiskClass",
    "SensitivityLevel",
    "Task",
    "TaskState",
    "TaskStep",
    "new_id",
    "utc_now",
    "verify_chain",
]
