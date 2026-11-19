import json
from pathlib import Path

from mitra.config import InstanceConfig
from mitra.security import approval_fingerprint, issue_approval_token
from mitra.store import Store
from mitra.worker import Worker


def make_worker(tmp_path: Path):
    config = InstanceConfig("worker-test", "Worker Test", tmp_path / "instance")
    worker = Worker(config)
    return worker, worker.store


def test_worker_executes_read_task_and_persists_result(tmp_path: Path):
    worker, store = make_worker(tmp_path)
    workspace = worker.config.data_dir / "workspace"
    workspace.mkdir()
    (workspace / "note.txt").write_text("hello worker", encoding="utf-8")
    task = store.create_task(
        "Read note",
        details=json.dumps({
            "capability": "filesystem-read", "operation": "read", "path": "note.txt"
        }),
        risk="read",
    )
    result = worker.run_once()
    assert result["status"] == "completed"
    assert result["result_summary"]["path"] == "note.txt"
    assert store.execution_receipts(task["id"])[0]["result"]["content"] == "hello worker"
    assert store.get_task(task["id"])["status"] == "completed"
    receipts = store.execution_receipts(task["id"])
    assert receipts[0]["status"] == "completed"


def test_worker_never_executes_write_before_approval(tmp_path: Path):
    worker, store = make_worker(tmp_path)
    task = store.create_task(
        "Write note",
        details=json.dumps({
            "capability": "filesystem-write", "operation": "write",
            "path": "note.txt", "content": "approved later",
        }),
        risk="write",
    )
    result = worker.run_once()
    assert result == {"task_id": task["id"], "status": "awaiting_approval"}
    assert not (worker.config.data_dir / "workspace" / "note.txt").exists()


def test_worker_executes_only_after_signed_task_approval(tmp_path: Path):
    worker, store = make_worker(tmp_path)
    task = store.create_task(
        "Write note",
        details=json.dumps({
            "capability": "filesystem-write", "operation": "write",
            "path": "note.txt", "content": "approved",
        }),
        risk="write",
    )
    claimed = store.claim_task()
    pending = store.start_task(task["id"], claimed["lease_token"])
    secret = "test-local-approval-secret-123456789"
    token = issue_approval_token(
        task["id"], "local test", secret,
        intent_fingerprint=approval_fingerprint(pending),
    )
    store.approve_task(task["id"], token, secret)
    result = worker.run_once()
    assert result["status"] == "completed"
    assert (worker.config.data_dir / "workspace" / "note.txt").read_text(encoding="utf-8") == "approved"


def test_approved_running_task_can_only_be_claimed_by_one_worker(tmp_path: Path):
    worker, store = make_worker(tmp_path)
    task = store.create_task(
        "Write note",
        details=json.dumps({
            "capability": "filesystem-write", "operation": "write",
            "path": "note.txt", "content": "approved",
        }),
        risk="write",
    )
    claimed = store.claim_task()
    pending = store.start_task(task["id"], claimed["lease_token"])
    secret = "test-local-approval-secret-123456789"
    token = issue_approval_token(
        task["id"], "local test", secret,
        intent_fingerprint=approval_fingerprint(pending),
    )
    store.approve_task(task["id"], token, secret)
    first = store.claim_approved_task()
    second = store.claim_approved_task()
    assert first is not None
    assert first["id"] == task["id"]
    assert second is None



def test_worker_retries_unsupported_capability_without_crashing(tmp_path: Path):
    worker, store = make_worker(tmp_path)
    task = store.create_task(
        "Send email",
        details=json.dumps({
            "capability": "gmail", "operation": "send", "path": "unused"
        }),
        risk="external",
    )
    result = worker.run_once()
    assert result["status"] == "retry_or_failed"
    assert "no supervised worker handler" in result["error"]
    assert store.get_task(task["id"])["status"] == "queued"
