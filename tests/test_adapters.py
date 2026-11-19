from pathlib import Path

import pytest

from mitra.adapters import AdapterContext, AdapterRegistry
from mitra.filesystem import FilesystemReadAdapter


def test_registry_requires_unique_explicit_adapters():
    registry = AdapterRegistry()
    adapter = FilesystemReadAdapter()
    registry.register(adapter)
    assert registry.get("filesystem-read") is adapter
    assert registry.list_registered() == ["filesystem-read"]
    with pytest.raises(ValueError, match="unique"):
        registry.register(adapter)


def test_filesystem_adapter_exposes_only_declared_read_operations(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "note.txt").write_text("hello MITRA", encoding="utf-8")
    adapter = FilesystemReadAdapter()
    context = AdapterContext("test", tmp_path)

    listed = adapter.execute("list", {"path": ".", "limit": 10}, context)
    assert listed.success
    assert listed.data[0]["name"] == "note.txt"

    read = adapter.execute("read", {"path": "note.txt"}, context)
    assert read.data["content"] == "hello MITRA"

    with pytest.raises(ValueError, match="not supported"):
        adapter.execute("write", {"path": "note.txt", "content": "tampered"}, context)
