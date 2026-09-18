"""Failures this package raises."""

from __future__ import annotations


class MemoryError_(Exception):
    """Base for everything this package raises.

    The trailing underscore keeps it from shadowing the builtin ``MemoryError``, which
    means something entirely different and would be a cruel thing to catch by accident.
    """


class LocalOnlyViolation(MemoryError_):
    """Something tried to move a LOCAL_ONLY memory somewhere it may not go.

    Raised rather than filtered silently. A silent filter means the caller believes it
    received everything relevant, and acts on a partial answer without knowing.
    """


class BudgetTooSmall(MemoryError_):
    """The budget cannot hold even what the caller said was mandatory."""
