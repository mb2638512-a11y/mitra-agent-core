"""SQLite-backed per-instance task and memory store."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, details TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY, content TEXT NOT NULL, tags TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")

    def create_task(self, title: str, details: str = "") -> dict[str, Any]:
        now, task_id = utc_now(), str(uuid.uuid4())
        with self._connect() as db:
            db.execute(
                "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, title, details, "queued", now, now),
            )
        return self.get_task(task_id) or {}

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def save_memory(self, content: str, tags: list[str] | None = None) -> dict[str, Any]:
        memory_id, now = str(uuid.uuid4()), utc_now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?)",
                (memory_id, content, json.dumps(tags or []), now),
            )
        return {"id": memory_id, "content": content, "tags": tags or [], "created_at": now}

    def search_memory(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        needle = f"%{query}%"
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM memories WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
                (needle, limit),
            ).fetchall()
        return [
            {"id": row["id"], "content": row["content"],
             "tags": json.loads(row["tags"]), "created_at": row["created_at"]}
            for row in rows
        ]
