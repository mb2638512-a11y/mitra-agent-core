from pathlib import Path

import pytest

from mitra.adapters import AdapterContext, AdapterRegistry, authorize_adapter_execution
from mitra.filesystem import FilesystemReadAdapter
from mitra.store import Store
from mitra.security import RiskLevel


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



def test_execution_permit_requires_running_task_lease_and_allowlisted_operation(tmp_path: Path):
    store = Store(tmp_path / "queue.sqlite3")
    task = store.create_task("Read a note")
    claimed = store.claim_task()
    running = store.start_task(task["id"], claimed["lease_token"])
    registry = AdapterRegistry()
    registry.register(FilesystemReadAdapter())

    permit = authorize_adapter_execution(
        store=store, registry=registry, instance_id="test",
        data_dir=tmp_path, task_id=task["id"],
        lease_token=running["lease_token"],
        capability_id="filesystem-read", operation="read",
    )
    assert permit.operation == "read"
    assert permit.adapter.capability_id == "filesystem-read"

    with pytest.raises(PermissionError, match="allowlisted"):
        authorize_adapter_execution(
            store=store, registry=registry, instance_id="test",
            data_dir=tmp_path, task_id=task["id"],
            lease_token=running["lease_token"],
            capability_id="filesystem-read", operation="delete",
        )

    with pytest.raises(PermissionError, match="active running-task lease"):
        authorize_adapter_execution(
            store=store, registry=registry, instance_id="test",
            data_dir=tmp_path, task_id=task["id"],
            lease_token="invalid", capability_id="filesystem-read",
            operation="read",
        )


def test_execution_permit_rejects_task_risk_below_adapter_risk(tmp_path: Path):
    class ElevatedFilesystemAdapter(FilesystemReadAdapter):
        risk = RiskLevel.EXTERNAL

    store = Store(tmp_path / "queue.sqlite3")
    task = store.create_task("Read a note", risk="read")
    claimed = store.claim_task()
    running = store.start_task(task["id"], claimed["lease_token"])
    registry = AdapterRegistry()
    registry.register(ElevatedFilesystemAdapter())

    with pytest.raises(PermissionError, match="below the adapter"):
        authorize_adapter_execution(
            store=store, registry=registry, instance_id="test",
            data_dir=tmp_path, task_id=task["id"],
            lease_token=running["lease_token"],
            capability_id="filesystem-read", operation="read",
        )
