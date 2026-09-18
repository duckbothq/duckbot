"""Errors the core raises. Each one exists because something must not be allowed."""

from __future__ import annotations


class DuckbotError(Exception):
    """Base for everything this package raises."""


class PolicyViolation(DuckbotError):
    """Content was about to leave without a policy decision permitting it."""


class ApprovalRequired(DuckbotError):
    """An action needs a human decision that has not been made."""

    def __init__(self, approval_id: str, message: str) -> None:
        super().__init__(message)
        self.approval_id = approval_id


class AuditChainBroken(DuckbotError):
    """The audit log does not verify. Treat as an incident, not a bug."""


class UntrustedContentMisuse(DuckbotError):
    """Retrieved content was about to be treated as an instruction."""
