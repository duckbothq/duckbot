"""Reference SQLite storage.

Records are stored as JSON keyed by id. That is deliberate at this stage: the schemas
are still settling, and a normalised table per model would mean a migration for every
field added during Phase 1. When the shapes stabilise, normalise the ones that need
querying — the interfaces in :mod:`duckbot_core.store` are what keep that cheap.

The audit table has no UPDATE and no DELETE path. Enforcing append-only in the interface
and then offering a delete in the implementation would be theatre.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from duckbot_schemas import Approval, ApprovalOutcome, AuditEvent, PolicyDecision, Task

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    updated_at TEXT NOT NULL,
    document TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    document TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS approvals_task ON approvals (task_id, outcome);
CREATE TABLE IF NOT EXISTS policy_decisions (
    id TEXT PRIMARY KEY,
    document TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    sequence INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    entry_hash TEXT NOT NULL,
    document TEXT NOT NULL
);
"""


def _connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    return conn


class SqliteStores:
    """All four stores over one connection.

    One file is the right shape for the single-user installation this product targets.
    A twenty-person company should not have to operate a database server.
    """

    def __init__(self, path: Path | str) -> None:
        self._conn = _connect(path)
        self.tasks = SqliteTaskStore(self._conn)
        self.approvals = SqliteApprovalStore(self._conn)
        self.policy_decisions = SqlitePolicyDecisionStore(self._conn)
        self.audit = SqliteAuditStore(self._conn)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SqliteStores:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class SqliteTaskStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def put(self, task: Task) -> None:
        self._conn.execute(
            "INSERT INTO tasks (id, updated_at, document) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, "
            "document=excluded.document",
            (task.id, task.updated_at.isoformat(), task.model_dump_json()),
        )
        self._conn.commit()

    def get(self, task_id: str) -> Task | None:
        row = self._conn.execute("SELECT document FROM tasks WHERE id=?", (task_id,)).fetchone()
        return Task.model_validate_json(row["document"]) if row else None

    def list_all(self) -> list[Task]:
        rows = self._conn.execute("SELECT document FROM tasks ORDER BY updated_at").fetchall()
        return [Task.model_validate_json(r["document"]) for r in rows]


class SqliteApprovalStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def put(self, approval: Approval) -> None:
        self._conn.execute(
            "INSERT INTO approvals (id, task_id, outcome, document) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET outcome=excluded.outcome, document=excluded.document",
            (approval.id, approval.task_id, approval.outcome.value, approval.model_dump_json()),
        )
        self._conn.commit()

    def get(self, approval_id: str) -> Approval | None:
        row = self._conn.execute(
            "SELECT document FROM approvals WHERE id=?", (approval_id,)
        ).fetchone()
        return Approval.model_validate_json(row["document"]) if row else None

    def pending_for_task(self, task_id: str) -> list[Approval]:
        rows = self._conn.execute(
            "SELECT document FROM approvals WHERE task_id=? AND outcome=?",
            (task_id, ApprovalOutcome.PENDING.value),
        ).fetchall()
        return [Approval.model_validate_json(r["document"]) for r in rows]


class SqlitePolicyDecisionStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def put(self, decision: PolicyDecision) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO policy_decisions (id, document) VALUES (?, ?)",
            (decision.id, decision.model_dump_json()),
        )
        self._conn.commit()

    def get(self, decision_id: str) -> PolicyDecision | None:
        row = self._conn.execute(
            "SELECT document FROM policy_decisions WHERE id=?", (decision_id,)
        ).fetchone()
        return PolicyDecision.model_validate_json(row["document"]) if row else None


class SqliteAuditStore:
    """Append-only. INSERT on a duplicate sequence fails rather than overwriting."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, event: AuditEvent) -> None:
        if event.entry_hash is None:
            raise ValueError("refusing to append an unsealed audit event")
        self._conn.execute(
            "INSERT INTO audit_events (sequence, id, entry_hash, document) VALUES (?, ?, ?, ?)",
            (event.sequence, event.id, event.entry_hash, event.model_dump_json()),
        )
        self._conn.commit()

    def last(self) -> AuditEvent | None:
        row = self._conn.execute(
            "SELECT document FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        return AuditEvent.model_validate_json(row["document"]) if row else None

    def all_events(self) -> list[AuditEvent]:
        rows = self._conn.execute("SELECT document FROM audit_events ORDER BY sequence").fetchall()
        return [AuditEvent.model_validate_json(r["document"]) for r in rows]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM audit_events").fetchone()
        return int(row["n"])


def _json(value: object) -> str:  # pragma: no cover - helper kept for future use
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
