"""SQLite-backed per-instance task queue and memory store."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, database: Path):
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, details TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")
            # Forward-only, additive migrations keep existing user databases intact.
            existing = {row["name"] for row in db.execute("PRAGMA table_info(tasks)")}
            migrations = {
                "risk": "TEXT NOT NULL DEFAULT 'read'",
                "attempts": "INTEGER NOT NULL DEFAULT 0",
                "max_attempts": "INTEGER NOT NULL DEFAULT 3",
                "available_at": "TEXT",
                "lease_token": "TEXT",
                "lease_until": "TEXT",
                "last_error": "TEXT",
                "idempotency_key": "TEXT",
            }
            for name, declaration in migrations.items():
                if name not in existing:
                    db.execute(f"ALTER TABLE tasks ADD COLUMN {name} {declaration}")
            db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_queue ON tasks(status, available_at, created_at)")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_idempotency ON tasks(idempotency_key) WHERE idempotency_key IS NOT NULL")
            db.execute("""CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY, content TEXT NOT NULL, tags TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS used_approval_nonces (
                nonce TEXT PRIMARY KEY, task_id TEXT NOT NULL, used_at TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                event TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )""")

    def _event(self, db: sqlite3.Connection, task_id: str, event: str, detail: str = "") -> None:
        db.execute(
            "INSERT INTO task_events(task_id, event, detail, created_at) VALUES (?, ?, ?, ?)",
            (task_id, event, detail[:2000], utc_now()),
        )

    def create_task(
        self, title: str, details: str = "", *, risk: str = "read",
        max_attempts: int = 3, idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if risk not in {"read", "write", "external", "financial", "destructive"}:
            raise ValueError("invalid task risk")
        if not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        now, task_id = utc_now(), str(uuid.uuid4())
        with self._connection() as db:
            if idempotency_key:
                row = db.execute("SELECT * FROM tasks WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
                if row:
                    return dict(row)
            db.execute(
                """INSERT INTO tasks
                (id, title, details, status, created_at, updated_at, risk, max_attempts, available_at, idempotency_key)
                VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?)""",
                (task_id, title, details, now, now, risk, max_attempts, now, idempotency_key),
            )
            self._event(db, task_id, "created", f"risk={risk}")
        return self.get_task(task_id) or {}

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._connection() as db:
            row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def claim_task(self, *, lease_seconds: int = 60) -> dict[str, Any] | None:
        """Atomically claim one queued task for planning; claiming never runs its actions."""
        if not 5 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 5 and 3600")
        now = datetime.now(timezone.utc)
        now_text = now.isoformat()
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        token = str(uuid.uuid4())
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT * FROM tasks WHERE status='queued'
                AND (available_at IS NULL OR available_at <= ?)
                AND attempts < max_attempts ORDER BY created_at LIMIT 1""",
                (now_text,),
            ).fetchone()
            if row is None:
                return None
            changed = db.execute(
                """UPDATE tasks SET status='planning', attempts=attempts+1,
                lease_token=?, lease_until=?, updated_at=?
                WHERE id=? AND status='queued'""",
                (token, lease_until, now_text, row["id"]),
            ).rowcount
            if changed != 1:
                return None
            self._event(db, row["id"], "claimed", f"attempt={row['attempts'] + 1}")
            claimed = db.execute("SELECT * FROM tasks WHERE id=?", (row["id"],)).fetchone()
        return dict(claimed) if claimed else None

    def start_task(self, task_id: str, lease_token: str) -> dict[str, Any]:
        """Start read-only tasks; all elevated-risk tasks are moved to approval."""
        from mitra.security import RiskLevel, evaluate_action

        with self._connection() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("Task not found")
            now_text = utc_now()
            if (row["status"] != "planning" or row["lease_token"] != lease_token
                    or not row["lease_until"] or row["lease_until"] <= now_text):
                raise PermissionError("valid unexpired planning lease is required")
            decision = evaluate_action(RiskLevel(row["risk"]))
            if not decision.allowed:
                db.execute(
                    "UPDATE tasks SET status='awaiting_approval', lease_token=NULL, lease_until=NULL, updated_at=? WHERE id=?",
                    (utc_now(), task_id),
                )
                self._event(db, task_id, "approval_required", decision.reason)
                return dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())
            db.execute("UPDATE tasks SET status='running', updated_at=? WHERE id=?", (utc_now(), task_id))
            self._event(db, task_id, "started")
            return dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def approve_task(self, task_id: str, approval_token: str, secret: str, *, lease_seconds: int = 60) -> dict[str, Any]:
        """Consume a signed, task-bound, single-use approval token and issue a worker lease."""
        from mitra.security import approval_fingerprint, verify_approval_token

        if not 5 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 5 and 3600")
        task = self.get_task(task_id)
        if task is None:
            raise ValueError('Task not found')
        now = datetime.now(timezone.utc)
        now_text = now.isoformat()
        worker_token = str(uuid.uuid4())
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("Task not found")
            if row["status"] != "awaiting_approval":
                raise ValueError("task is not awaiting approval")
            claims = verify_approval_token(
                approval_token, task_id, secret,
                intent_fingerprint=approval_fingerprint(dict(row)),
            )
            try:
                db.execute(
                    "INSERT INTO used_approval_nonces(nonce, task_id, used_at) VALUES (?, ?, ?)",
                    (claims["nonce"], task_id, now_text),
                )
            except sqlite3.IntegrityError as exc:
                raise PermissionError("approval token has already been used") from exc
            db.execute(
                """UPDATE tasks SET status='running', lease_token=?, lease_until=?,
                updated_at=? WHERE id=?""",
                (worker_token, (now + timedelta(seconds=lease_seconds)).isoformat(), now_text, task_id),
            )
            self._event(db, task_id, "approved_and_started", f"verified_approver={claims['approver']}")
            return dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def renew_lease(self, task_id: str, lease_token: str, *, lease_seconds: int = 60) -> dict[str, Any]:
        """Renew an unexpired worker lease using its secret token."""
        if not 5 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 5 and 3600")
        now = datetime.now(timezone.utc)
        now_text = now.isoformat()
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self._connection() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("Task not found")
            if row["status"] not in {"planning", "running", "verifying"}:
                raise PermissionError("task does not hold an active worker lease")
            if row["lease_token"] != lease_token or not row["lease_until"] or row["lease_until"] <= now_text:
                raise PermissionError("worker lease is invalid or expired")
            db.execute(
                "UPDATE tasks SET lease_until=?, updated_at=? WHERE id=?",
                (lease_until, now_text, task_id),
            )
            self._event(db, task_id, "lease_renewed", f"lease_seconds={lease_seconds}")
            return dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def queue_stats(self) -> dict[str, int]:
        with self._connection() as db:
            rows = db.execute("SELECT status, COUNT(*) AS count FROM tasks GROUP BY status").fetchall()
        stats = {state: 0 for state in (
            "queued", "planning", "awaiting_approval", "running",
            "verifying", "completed", "failed", "cancelled",
        )}
        stats.update({row["status"]: row["count"] for row in rows})
        stats["total"] = sum(stats.values())
        return stats

    def begin_verification(self, task_id: str, lease_token: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("Task not found")
            now_text = utc_now()
            if (row["status"] != "running" or row["lease_token"] != lease_token
                    or not row["lease_until"] or row["lease_until"] <= now_text):
                raise PermissionError("valid unexpired running task lease is required")
            db.execute("UPDATE tasks SET status='verifying', updated_at=? WHERE id=?", (utc_now(), task_id))
            self._event(db, task_id, "verification_started")
            return dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def finish_task(self, task_id: str, lease_token: str, *, success: bool, detail: str = "") -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("Task not found")
            now_text = utc_now()
            if (row["status"] != "verifying" or row["lease_token"] != lease_token
                    or not row["lease_until"] or row["lease_until"] <= now_text):
                raise PermissionError("task must be verifying under an unexpired lease")
            status = "completed" if success else "failed"
            db.execute(
                "UPDATE tasks SET status=?, last_error=?, lease_token=NULL, lease_until=NULL, updated_at=? WHERE id=?",
                (status, "" if success else detail[:2000], utc_now(), task_id),
            )
            self._event(db, task_id, status, detail)
            return dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def retry_task(self, task_id: str, *, delay_seconds: int = 30, reason: str = "") -> dict[str, Any]:
        if not 1 <= delay_seconds <= 86400:
            raise ValueError("delay_seconds must be between 1 and 86400")
        with self._connection() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("Task not found")
            if row["status"] not in {"planning", "running", "verifying"}:
                raise ValueError("only active tasks can be retried")
            if row["attempts"] >= row["max_attempts"]:
                status = "failed"
            else:
                status = "queued"
            available = (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat()
            db.execute(
                """UPDATE tasks SET status=?, available_at=?, lease_token=NULL,
                lease_until=NULL, last_error=?, updated_at=? WHERE id=?""",
                (status, available, reason[:2000], utc_now(), task_id),
            )
            self._event(db, task_id, "retry_scheduled" if status == "queued" else "retry_exhausted", reason)
            return dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("Task not found")
            if row["status"] in {"completed", "failed", "cancelled"}:
                raise ValueError("terminal task cannot be cancelled")
            db.execute(
                "UPDATE tasks SET status='cancelled', lease_token=NULL, lease_until=NULL, updated_at=? WHERE id=?",
                (utc_now(), task_id),
            )
            self._event(db, task_id, "cancelled")
            return dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def recover_expired_leases(self) -> int:
        """Requeue expired worker leases, or fail tasks whose retry budget is exhausted."""
        now = utc_now()
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT id, attempts, max_attempts FROM tasks WHERE lease_until IS NOT NULL AND lease_until <= ?",
                (now,),
            ).fetchall()
            for row in rows:
                status = "queued" if row["attempts"] < row["max_attempts"] else "failed"
                db.execute(
                    """UPDATE tasks SET status=?, lease_token=NULL, lease_until=NULL,
                    available_at=?, last_error='worker lease expired', updated_at=? WHERE id=?""",
                    (status, now, now, row["id"]),
                )
                self._event(db, row["id"], "lease_recovered", f"new_status={status}")
            return len(rows)

    def task_events(self, task_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT event, detail, created_at FROM task_events WHERE task_id=? ORDER BY id DESC LIMIT ?",
                (task_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_memory(self, content: str, tags: list[str] | None = None) -> dict[str, Any]:
        memory_id, now = str(uuid.uuid4()), utc_now()
        with self._connection() as db:
            db.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?)",
                (memory_id, content, json.dumps(tags or []), now),
            )
        return {"id": memory_id, "content": content, "tags": tags or [], "created_at": now}

    def search_memory(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        needle = f"%{query}%"
        with self._connection() as db:
            rows = db.execute(
                "SELECT * FROM memories WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
                (needle, limit),
            ).fetchall()
        return [
            {"id": row["id"], "content": row["content"],
             "tags": json.loads(row["tags"]), "created_at": row["created_at"]}
            for row in rows
        ]
