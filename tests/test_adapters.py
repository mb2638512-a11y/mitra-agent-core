from pathlib import Path
import hashlib
import json

import pytest

from mitra.adapters import AdapterContext, AdapterRegistry, authorize_adapter_execution
from mitra.filesystem import FilesystemReadAdapter, FilesystemWriteAdapter
from mitra.store import Store
from mitra.security import RiskLevel, approval_fingerprint, issue_approval_token


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



def test_write_adapter_is_separate_and_confined_to_workspace(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adapter = FilesystemWriteAdapter()
    context = AdapterContext("test", tmp_path)
    result = adapter.execute(
        "write", {"path": "hello.txt", "content": "approved"},
        context,
    )
    assert result.success
    assert (workspace / "hello.txt").read_text(encoding="utf-8") == "approved"
    with pytest.raises(ValueError, match="not supported"):
        adapter.execute("delete", {"path": "hello.txt"}, context)



def test_approved_write_requires_token_and_records_receipt(tmp_path: Path):
    details = json.dumps({
        "capability": "filesystem-write",
        "operation": "write",
        "path": "approved.txt",
        "content": "approved content",
    }, sort_keys=True)
    store = Store(tmp_path / "queue.sqlite3")
    task = store.create_task("Write approved file", details=details, risk="write")
    claimed = store.claim_task()
    gated = store.start_task(task["id"], claimed["lease_token"])
    assert gated["status"] == "awaiting_approval"

    secret = "local-test-secret-that-is-long-enough-123"
    token = issue_approval_token(
        task["id"], "test operator", secret,
        intent_fingerprint=approval_fingerprint(gated),
    )
    approved = store.approve_task(task["id"], token, secret)
    registry = AdapterRegistry()
    registry.register(FilesystemWriteAdapter())
    permit = authorize_adapter_execution(
        store=store, registry=registry, instance_id="test",
        data_dir=tmp_path, task_id=task["id"],
        lease_token=approved["lease_token"],
        capability_id="filesystem-write", operation="write",
    )
    request_hash = hashlib.sha256(details.encode("utf-8")).hexdigest()
    receipt = store.begin_execution_receipt(
        task["id"], approved["lease_token"], capability_id="filesystem-write",
        operation="write", idempotency_key="approved-write-1",
        request_hash=request_hash,
    )
    assert receipt["_created"]
    result = permit.adapter.execute(
        "write", {"path": "approved.txt", "content": "approved content"},
        permit.context,
    )
    store.finish_execution_receipt(
        task["id"], approved["lease_token"], receipt["id"], result=result.data,
    )
    assert (tmp_path / "workspace" / "approved.txt").read_text(encoding="utf-8") == "approved content"
    assert store.execution_receipts(task["id"])[0]["status"] == "completed"
