"""Per-instance encrypted storage for OAuth tokens and provider credentials."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CredentialVault:
    """AES-256-GCM credential vault with a private per-instance key file."""

    def __init__(self, database: Path, key_path: Path, *, instance_id: str):
        if not instance_id or len(instance_id) > 64:
            raise ValueError("instance_id must contain 1-64 characters")
        self.database = Path(database)
        self.key_path = Path(key_path)
        self.instance_id = instance_id
        self.database.parent.mkdir(parents=True, exist_ok=True)
        key = self._load_or_create_key()
        self._cipher = AESGCM(key)
        with self._connection() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS credentials (
                    provider TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(provider, account_id)
                )"""
            )

    def _load_or_create_key(self) -> bytes:
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        if self.key_path.is_symlink():
            raise PermissionError("credential vault key must not be a symlink")
        if self.key_path.exists():
            if not self.key_path.is_file():
                raise PermissionError("credential vault key must be a regular file")
            if os.name == "posix" and self.key_path.stat().st_mode & 0o077:
                raise PermissionError("credential vault key permissions must be 0600")
            key = self.key_path.read_bytes()
            if len(key) != 32:
                raise ValueError("credential vault key must contain exactly 32 bytes")
            return key
        key = secrets.token_bytes(32)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self.key_path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(key)
            stream.flush()
            os.fsync(stream.fileno())
        return key

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            with db:
                yield db
        finally:
            db.close()

    def _aad(self, provider: str, account_id: str) -> bytes:
        return f"MITRA:vault:{self.instance_id}:{provider}:{account_id}".encode("utf-8")

    @staticmethod
    def _validate_identity(provider: str, account_id: str) -> None:
        if not isinstance(provider, str) or not provider or len(provider) > 100:
            raise ValueError("provider must contain 1-100 characters")
        if not isinstance(account_id, str) or not account_id or len(account_id) > 200:
            raise ValueError("account_id must contain 1-200 characters")

    def put(self, provider: str, account_id: str, credentials: dict[str, Any]) -> dict:
        self._validate_identity(provider, account_id)
        if not isinstance(credentials, dict):
            raise ValueError("credentials must be a JSON object")
        plaintext = json.dumps(credentials, sort_keys=True, ensure_ascii=False).encode("utf-8")
        if len(plaintext) > 65536:
            raise ValueError("credential payload exceeds 64 KB")
        nonce = secrets.token_bytes(12)
        ciphertext = self._cipher.encrypt(nonce, plaintext, self._aad(provider, account_id))
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as db:
            db.execute(
                """INSERT INTO credentials(provider, account_id, nonce, ciphertext, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(provider, account_id) DO UPDATE SET
                nonce=excluded.nonce, ciphertext=excluded.ciphertext, updated_at=excluded.updated_at""",
                (provider, account_id, nonce, ciphertext, now),
            )
        return {"provider": provider, "account_id": account_id, "updated_at": now}

    def get(self, provider: str, account_id: str) -> dict[str, Any] | None:
        self._validate_identity(provider, account_id)
        with self._connection() as db:
            row = db.execute(
                "SELECT nonce, ciphertext FROM credentials WHERE provider=? AND account_id=?",
                (provider, account_id),
            ).fetchone()
        if row is None:
            return None
        try:
            plaintext = self._cipher.decrypt(
                row["nonce"], row["ciphertext"], self._aad(provider, account_id)
            )
            value = json.loads(plaintext.decode("utf-8"))
        except (InvalidTag, UnicodeDecodeError, json.JSONDecodeError):
            raise PermissionError("credential vault authentication failed") from None
        if not isinstance(value, dict):
            raise PermissionError("credential vault record is invalid")
        return value

    def list_metadata(self) -> list[dict]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT provider, account_id, updated_at FROM credentials ORDER BY provider, account_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def delete(self, provider: str, account_id: str) -> bool:
        self._validate_identity(provider, account_id)
        with self._connection() as db:
            cursor = db.execute(
                "DELETE FROM credentials WHERE provider=? AND account_id=?",
                (provider, account_id),
            )
        return cursor.rowcount == 1
