"""The audit log service: sequencing, sealing, and verification.

Callers describe what happened. They do not manage sequence numbers or hashes, because
an audit log whose integrity depends on every caller remembering to do something is an
audit log that will be broken by the first person in a hurry.
"""

from __future__ import annotations

from typing import Any

from duckbot_schemas import (
    GENESIS_HASH,
    AuditAction,
    AuditEvent,
    PolicyAction,
    SensitivityLevel,
    verify_chain,
)

from .errors import AuditChainBroken
from .store import AuditStore


class AuditLog:
    """Append-only, hash-chained log over an :class:`~duckbot_core.store.AuditStore`."""

    def __init__(self, store: AuditStore) -> None:
        self._store = store

    def record(
        self,
        *,
        actor: str,
        action: AuditAction,
        target: str | None = None,
        task_id: str | None = None,
        classification_id: str | None = None,
        policy_decision_id: str | None = None,
        model_call_id: str | None = None,
        approval_id: str | None = None,
        sensitivity: SensitivityLevel | None = None,
        policy_action: PolicyAction | None = None,
        destination: str | None = None,
        placeholder_tokens: list[str] | None = None,
        result: str = "ok",
        detail: str | None = None,
    ) -> AuditEvent:
        """Append one sealed event and return it.

        ``detail`` is human-readable and must not contain sensitive values. Everything
        sensitive is referenced by id or by placeholder token.
        """
        previous = self._store.last()
        kwargs: dict[str, Any] = {
            "sequence": 0 if previous is None else previous.sequence + 1,
            "prev_hash": GENESIS_HASH
            if previous is None
            else (previous.entry_hash or GENESIS_HASH),
            "actor": actor,
            "action": action,
            "target": target,
            "task_id": task_id,
            "classification_id": classification_id,
            "policy_decision_id": policy_decision_id,
            "model_call_id": model_call_id,
            "approval_id": approval_id,
            "sensitivity": sensitivity,
            "policy_action": policy_action,
            "destination": destination,
            "placeholder_tokens": placeholder_tokens or [],
            "result": result,
            "detail": detail,
        }
        event = AuditEvent(**kwargs).sealed()
        self._store.append(event)
        return event

    def verify(self) -> None:
        """Raise :class:`AuditChainBroken` if the log does not verify."""
        ok, sequence = verify_chain(self._store.all_events())
        if not ok:
            raise AuditChainBroken(
                f"audit chain fails to verify at sequence {sequence}; "
                "treat this as an incident, not as a bug to be worked around"
            )

    def export_text(self) -> str:
        """Human-readable export.

        This is what gets handed to an auditor or attached to a client security
        questionnaire, so it is plain text and contains no sensitive values.
        """
        lines: list[str] = []
        for e in self._store.all_events():
            parts = [
                f"#{e.sequence:06d}",
                e.occurred_at.isoformat(),
                e.actor,
                e.action.value,
            ]
            if e.destination:
                parts.append(f"-> {e.destination}")
            if e.target:
                parts.append(f"target={e.target}")
            if e.policy_action:
                parts.append(f"policy={e.policy_action.value}")
            if e.sensitivity is not None:
                parts.append(f"sensitivity={e.sensitivity.name}")
            if e.placeholder_tokens:
                parts.append(f"tokens={len(e.placeholder_tokens)}")
            parts.append(f"result={e.result}")
            if e.detail:
                parts.append(f"| {e.detail}")
            lines.append("  ".join(parts))
        return "\n".join(lines)

    @property
    def count(self) -> int:
        return self._store.count()
