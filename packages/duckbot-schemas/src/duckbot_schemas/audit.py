"""The audit log: append-only, hash-chained, exportable, human-readable.

The chain is not cryptographic proof against a determined attacker with write access to
the file — nothing on a single machine is. It is enough to make silent tampering
detectable, which is what an auditor, a client questionnaire, or an incident review
actually needs.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from .common import DuckbotModel, PolicyAction, SensitivityLevel, new_id, utc_now

GENESIS_HASH = "0" * 64


class AuditAction(StrEnum):
    CONTENT_CLASSIFIED = "content_classified"
    POLICY_EVALUATED = "policy_evaluated"
    CONTENT_REDACTED = "content_redacted"
    SENT_TO_MODEL = "sent_to_model"
    RESPONSE_RESTORED = "response_restored"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    EXTERNAL_ACTION = "external_action"
    TASK_STATE_CHANGED = "task_state_changed"
    POLICY_OVERRIDDEN = "policy_overridden"


class AuditEvent(DuckbotModel):
    """One immutable line in the log.

    Deliberately absent: any raw sensitive value. An event references a classification
    and a policy decision by id, and records placeholder tokens where relevant. If an
    audit export could leak the data the product exists to protect, the product would be
    arguing against itself.
    """

    id: str = Field(default_factory=lambda: new_id("aud"))
    sequence: int = Field(ge=0, description="monotonic within one log")
    occurred_at: datetime = Field(default_factory=utc_now)

    actor: str = Field(min_length=1, description="user id, or 'system'")
    action: AuditAction
    target: str | None = Field(default=None, min_length=1)

    task_id: str | None = Field(default=None, min_length=1)
    classification_id: str | None = Field(default=None, min_length=1)
    policy_decision_id: str | None = Field(default=None, min_length=1)
    model_call_id: str | None = Field(default=None, min_length=1)
    approval_id: str | None = Field(default=None, min_length=1)

    sensitivity: SensitivityLevel | None = None
    policy_action: PolicyAction | None = None
    destination: str | None = Field(default=None, min_length=1)
    placeholder_tokens: list[str] = Field(default_factory=list)

    result: str = Field(default="ok", min_length=1)
    detail: str | None = Field(
        default=None, description="human-readable; must not contain sensitive values"
    )

    prev_hash: str = Field(default=GENESIS_HASH, pattern=r"^[0-9a-f]{64}$")
    entry_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    def compute_hash(self) -> str:
        """Hash of this entry's content plus the previous entry's hash."""
        payload = self.model_dump(mode="json", exclude={"entry_hash"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def sealed(self) -> AuditEvent:
        """Return a copy with ``entry_hash`` filled in. Seal once, then append."""
        return self.model_copy(update={"entry_hash": self.compute_hash()})

    @model_validator(mode="after")
    def _external_actions_are_attributable(self) -> AuditEvent:
        if self.action is AuditAction.SENT_TO_MODEL and not self.destination:
            raise ValueError("an outbound event must record where it went")
        return self


def verify_chain(events: list[AuditEvent]) -> tuple[bool, int | None]:
    """Verify a sealed log.

    Returns ``(True, None)`` when intact, or ``(False, sequence)`` at the first entry
    that does not verify. Checks three things: every entry is sealed, each entry's hash
    matches its content, and each entry's ``prev_hash`` matches the one before it.
    """
    expected_prev = GENESIS_HASH
    for event in events:
        if event.entry_hash is None:
            return False, event.sequence
        if event.prev_hash != expected_prev:
            return False, event.sequence
        if event.compute_hash() != event.entry_hash:
            return False, event.sequence
        expected_prev = event.entry_hash
    return True, None
