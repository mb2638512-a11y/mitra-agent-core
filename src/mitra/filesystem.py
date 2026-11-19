"""Read-only filesystem adapter confined to an instance workspace.

The adapter deliberately rejects symlinks rather than following them. It is not
a general-purpose filesystem browser and exposes no shell or arbitrary paths.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from mitra.adapters import AdapterContext, AdapterResult
from mitra.security import RiskLevel


class Workspace:
    def __init__(self, root: Path, *, max_read_bytes: int = 1_000_000):
        if max_read_bytes < 1:
            raise ValueError("max_read_bytes must be positive")
        root = Path(root).expanduser()
        root.parent.mkdir(parents=True, exist_ok=True)
        if root.is_symlink():
            raise PermissionError("workspace root must not be a symlink")
        root.mkdir(exist_ok=True)
        if root.is_symlink():
            raise PermissionError("workspace root must not be a symlink")
        self.root = root.resolve(strict=True)
        self.max_read_bytes = max_read_bytes

    def _resolve(self, relative_path: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("path must be a non-empty relative path")
        candidate = Path(relative_path)
        if candidate.is_absolute() or any(part in {"..", "."} for part in candidate.parts):
            raise PermissionError("absolute paths and traversal segments are not allowed")
        current = self.root
        for part in candidate.parts:
            current = current / part
            if current.is_symlink():
                raise PermissionError("symlinks are not allowed in the workspace")
        resolved = current.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise PermissionError("path escapes the workspace")
        return resolved

    def list_files(self, relative_path: str = ".", *, limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        directory = self.root if relative_path == "." else self._resolve(relative_path)
        if not directory.is_dir():
            raise ValueError("directory does not exist")
        entries = []
        for item in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
            if item.is_symlink():
                continue
            entries.append({
                "name": item.name,
                "path": item.relative_to(self.root).as_posix(),
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            })
            if len(entries) >= limit:
                break
        return entries

    def write_text(self, relative_path: str, content: str) -> dict:
        if not isinstance(content, str):
            raise ValueError("content must be text")
        payload = content.encode("utf-8")
        if len(payload) > 1_000_000:
            raise ValueError("content exceeds the 1000000-byte write limit")
        target = self._resolve(relative_path)
        if not target.parent.is_dir():
            raise ValueError("parent directory must already exist")
        flags = os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        if target.exists():
            if not target.is_file():
                raise ValueError("target must be a regular file")
            flags |= os.O_TRUNC
        else:
            flags |= os.O_CREAT | os.O_EXCL
        descriptor = os.open(target, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        return {
            "path": target.relative_to(self.root).as_posix(),
            "bytes_written": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    def read_text(self, relative_path: str) -> dict:
        target = self._resolve(relative_path)
        if not target.is_file():
            raise ValueError("file does not exist")
        size = target.stat().st_size
        if size > self.max_read_bytes:
            raise ValueError(f"file exceeds the {self.max_read_bytes}-byte read limit")
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("file is not valid UTF-8 text") from exc
        return {"path": target.relative_to(self.root).as_posix(), "size": size, "content": content}



class FilesystemReadAdapter:
    """Explicit read-only workspace adapter implementing the shared contract."""

    capability_id = "filesystem-read"
    risk = RiskLevel.READ
    operations = frozenset({"list", "read"})

    def execute(
        self, operation: str, arguments: dict[str, Any], context: AdapterContext
    ) -> AdapterResult:
        workspace = Workspace(context.data_dir / "workspace")
        if operation == "list":
            path = arguments.get("path", ".")
            limit = arguments.get("limit", 100)
            if not isinstance(path, str) or not isinstance(limit, int):
                raise ValueError("list requires a string path and integer limit")
            return AdapterResult(
                self.capability_id, operation, True,
                data=workspace.list_files(path, limit=limit),
            )
        if operation == "read":
            path = arguments.get("path")
            if not isinstance(path, str):
                raise ValueError("read requires a string path")
            return AdapterResult(
                self.capability_id, operation, True,
                data=workspace.read_text(path),
            )
        raise ValueError("operation is not supported by filesystem-read")



class FilesystemWriteAdapter:
    """Write text only inside the instance workspace; never exposes OS paths."""

    capability_id = "filesystem-write"
    risk = RiskLevel.WRITE
    operations = frozenset({"write"})

    def execute(
        self, operation: str, arguments: dict[str, Any], context: AdapterContext
    ) -> AdapterResult:
        if operation != "write":
            raise ValueError("operation is not supported by filesystem-write")
        path = arguments.get("path")
        content = arguments.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            raise ValueError("write requires string path and content")
        workspace = Workspace(context.data_dir / "workspace")
        return AdapterResult(
            self.capability_id, operation, True,
            data=workspace.write_text(path, content),
        )
