"""Retention, enforced rather than recorded.

A retention field that nothing acts on is a compliance claim the product cannot back. If
:class:`~duckbot_schemas.MemoryItem` says a memory is kept for thirty days, something has
to delete it on the thirty-first, and that something is here.

Two decisions that look small and are not.

**Age is measured from creation, never from last use.** Refreshing the clock on access
would turn "kept for 30 days" into "kept for 30 days after you stop touching it", which
is a different and much weaker promise than the one the customer was given. ``last_used_at``
exists for relevance ranking, not for retention.

**Session memory and indefinite memory are different things that both have no deadline.**
They are swept by different triggers — the end of a session and never — so they are
handled by different methods rather than by one method and a flag, which is how the two
get confused.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from duckbot_schemas import MemoryItem, RetentionPolicy, utc_now

MAX_AGE: dict[RetentionPolicy, timedelta | None] = {
    RetentionPolicy.SESSION: None,
    RetentionPolicy.DAYS_30: timedelta(days=30),
    RetentionPolicy.DAYS_365: timedelta(days=365),
    RetentionPolicy.INDEFINITE: None,
}
"""``None`` means "no deadline on the clock", which SESSION and INDEFINITE share and mean
oppositely. Read :func:`expires_at` rather than this table."""


def expires_at(item: MemoryItem) -> datetime | None:
    """When this memory stops being allowed to exist, if a clock decides that.

    ``None`` for SESSION (the session's end decides) and for INDEFINITE (nothing does).
    """
    window = MAX_AGE[item.retention]
    return None if window is None else item.created_at + window


def is_expired(item: MemoryItem, now: datetime | None = None) -> bool:
    deadline = expires_at(item)
    return deadline is not None and (now or utc_now()) >= deadline


class Deletable(Protocol):
    """The part of a store this module needs, and no more.

    Narrower than :class:`~duckbot_memory.store.MemoryStore` on purpose: a sweeper that
    could also read or write individual items would eventually be asked to.
    """

    def all_items(self) -> list[MemoryItem]: ...
    def delete_many(self, item_ids: list[str]) -> int: ...


@dataclass(frozen=True)
class SweepResult:
    """What a sweep did. Returned so it can be logged, and so a dry run is possible."""

    examined: int
    expired_ids: tuple[str, ...]
    deleted: int

    @property
    def would_delete(self) -> int:
        return len(self.expired_ids)


class RetentionSweeper:
    """Deletes what is past its date.

    ``dry_run`` exists because the first question anybody asks before switching this on
    is "what would it remove", and the answer must not require them to find out by losing
    it.
    """

    def __init__(self, store: Deletable) -> None:
        self._store = store

    def sweep(self, *, now: datetime | None = None, dry_run: bool = False) -> SweepResult:
        items = self._store.all_items()
        expired = [i.id for i in items if is_expired(i, now)]
        deleted = 0 if dry_run else self._store.delete_many(expired)
        return SweepResult(examined=len(items), expired_ids=tuple(expired), deleted=deleted)

    def end_session(self, *, dry_run: bool = False) -> SweepResult:
        """Drop every session-scoped memory. Triggered by the session ending, not by time."""
        items = self._store.all_items()
        session = [i.id for i in items if i.retention is RetentionPolicy.SESSION]
        deleted = 0 if dry_run else self._store.delete_many(session)
        return SweepResult(examined=len(items), expired_ids=tuple(session), deleted=deleted)

    def forget(self, item_ids: Iterable[str]) -> int:
        """Delete specific memories, because somebody asked.

        Separate from sweeping so that an erasure request appears in the code as its own
        act rather than as a special case of housekeeping.
        """
        return self._store.delete_many(list(item_ids))
