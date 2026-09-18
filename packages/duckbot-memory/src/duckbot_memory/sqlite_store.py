"""SQLite storage for memory.

Same shape as :mod:`duckbot_core.sqlite_store`: JSON documents keyed by id, because the
schemas are still settling and a normalised column per field would mean a migration for
every field added during Phase 1.

Two columns are lifted out of the document — ``created_at`` and ``retention`` — because
the retention sweeper runs over every item on a schedule, and making it deserialise the
whole store to answer "what is old" is the difference between a sweep that runs and a
sweep that gets disabled because it is slow.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from duckbot_schemas import MemoryItem

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_items (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    retention TEXT NOT NULL,
    sensitivity INTEGER NOT NULL,
    document TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memory_retention ON memory_items (retention, created_at);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


class SqliteMemoryStore:
    """One file, one table. A twenty-person company should not operate a database server."""

    def __init__(self, path: Path | str) -> None:
        self._conn = connect(path)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SqliteMemoryStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def put(self, item: MemoryItem) -> None:
        self._conn.execute(
            "INSERT INTO memory_items (id, created_at, retention, sensitivity, document) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET created_at=excluded.created_at, "
            "retention=excluded.retention, sensitivity=excluded.sensitivity, "
            "document=excluded.document",
            (
                item.id,
                item.created_at.isoformat(),
                item.retention.value,
                int(item.sensitivity),
                item.model_dump_json(),
            ),
        )
        self._conn.commit()

    def get(self, item_id: str) -> MemoryItem | None:
        row = self._conn.execute(
            "SELECT document FROM memory_items WHERE id=?", (item_id,)
        ).fetchone()
        return MemoryItem.model_validate_json(row["document"]) if row else None

    def all_items(self) -> list[MemoryItem]:
        rows = self._conn.execute(
            "SELECT document FROM memory_items ORDER BY created_at"
        ).fetchall()
        return [MemoryItem.model_validate_json(r["document"]) for r in rows]

    def delete(self, item_id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM memory_items WHERE id=?", (item_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def delete_many(self, item_ids: list[str]) -> int:
        if not item_ids:
            return 0
        placeholders = ",".join("?" for _ in item_ids)
        cursor = self._conn.execute(
            f"DELETE FROM memory_items WHERE id IN ({placeholders})",
            item_ids,
        )
        self._conn.commit()
        return int(cursor.rowcount)

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM memory_items").fetchone()
        return int(row["n"])
