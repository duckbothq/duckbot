"""Duckbot core — the control plane.

Task records, the policy engine, approval gates and the audit log. Everything else in
the product depends on this, which is why it was built first and why its interfaces are
meant to stabilise before its implementations do.

Two structural guarantees live here, both enforced by types rather than by convention:

* Content cannot leave without a policy decision. :class:`~duckbot_core.policy.OutboundPermit`
  is the only way outward and only :class:`~duckbot_core.policy.PolicyEngine` can make one.
* Retrieved content cannot silently become an instruction. See :mod:`duckbot_core.content`.
"""

from .approvals import ApprovalGate
from .audit_log import AuditLog
from .content import Instruction, UntrustedContent, promote_to_instruction
from .errors import (
    ApprovalRequired,
    AuditChainBroken,
    DuckbotError,
    PolicyViolation,
    UntrustedContentMisuse,
)
from .policy import DEFAULT_ACTION_BY_LEVEL, OutboundPermit, PolicyEngine, Rule
from .sqlite_store import SqliteStores
from .store import (
    ApprovalStore,
    AuditStore,
    InMemoryApprovalStore,
    InMemoryAuditStore,
    InMemoryPolicyDecisionStore,
    InMemoryTaskStore,
    PolicyDecisionStore,
    TaskStore,
)
from .tasks import TaskService

__all__ = [
    "DEFAULT_ACTION_BY_LEVEL",
    "ApprovalGate",
    "ApprovalRequired",
    "ApprovalStore",
    "AuditChainBroken",
    "AuditLog",
    "AuditStore",
    "DuckbotError",
    "InMemoryApprovalStore",
    "InMemoryAuditStore",
    "InMemoryPolicyDecisionStore",
    "InMemoryTaskStore",
    "Instruction",
    "OutboundPermit",
    "PolicyDecisionStore",
    "PolicyEngine",
    "PolicyViolation",
    "Rule",
    "SqliteStores",
    "TaskService",
    "TaskStore",
    "UntrustedContent",
    "UntrustedContentMisuse",
    "promote_to_instruction",
]
