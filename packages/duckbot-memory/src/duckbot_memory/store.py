"""Where memories live.

One contrast with :mod:`duckbot_core.store` is worth stating outright. The audit log is
append-only and deliberately offers no delete: an audit store that can rewrite history is
not an audit store. Memory is the opposite. It **must** be deletable, item by item and in
bulk, because retention promises are worthless without enforcement and because a person
is entitled to ask for their data to be removed. Offering retention policies and no
delete would be the same theatre in the other direction.
"""

from __future__ import annotations

from typing import Protocol

from duckbot_schemas import MemoryItem, MemoryScope


class MemoryStore(Protocol):
    def put(self, item: MemoryItem) -> None: ...
    def get(self, item_id: str) -> MemoryItem | None: ...
    def all_items(self) -> list[MemoryItem]: ...
    def delete(self, item_id: str) -> bool:
        """Remove one memory. Returns whether it was there."""
        ...

    def delete_many(self, item_ids: list[str]) -> int:
        """Remove several, returning how many were removed."""
        ...

    def count(self) -> int: ...


class InMemoryMemoryStore:
    """For tests, and for the session-scoped tier where persistence is the wrong answer."""

    def __init__(self) -> None:
        self._items: dict[str, MemoryItem] = {}

    def put(self, item: MemoryItem) -> None:
        self._items[item.id] = item

    def get(self, item_id: str) -> MemoryItem | None:
        return self._items.get(item_id)

    def all_items(self) -> list[MemoryItem]:
        return sorted(self._items.values(), key=lambda i: i.created_at)

    def delete(self, item_id: str) -> bool:
        return self._items.pop(item_id, None) is not None

    def delete_many(self, item_ids: list[str]) -> int:
        return sum(1 for i in item_ids if self.delete(i))

    def count(self) -> int:
        return len(self._items)

    def scoped(self, scope: MemoryScope) -> list[MemoryItem]:
        return [i for i in self.all_items() if i.scope is scope]
