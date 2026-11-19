from pathlib import Path

import pytest

from mitra.store import Store


def running_task(tmp_path: Path):
    store = Store(tmp_path / "receipts.sqlite3")
    task = store.create_task("Approved workspace operation")
    claimed = store.claim_task()
    running = store.start_task(task["id"], claimed["lease_token"])
    return store, task, running


def test_execution_receipt_is_durable_and_idempotent(tmp_path: Path):
    store, task, running = running_task(tmp_path)
    kwargs = {
        "capability_id": "filesystem-read",
        "operation": "read",
        "idempotency_key": "request-001",
        "request_hash": "a" * 64,
    }
    first = store.begin_execution_receipt(task["id"], running["lease_token"], **kwargs)
    again = store.begin_execution_receipt(task["id"], running["lease_token"], **kwargs)
    assert first["id"] == again["id"]
    assert first["status"] == "started"

    completed = store.finish_execution_receipt(
        task["id"], running["lease_token"], first["id"], result={"bytes": 12}
    )
    assert completed["status"] == "completed"
    assert store.execution_receipts(task["id"])[0]["result"] == {"bytes": 12}


def test_receipt_idempotency_key_cannot_be_reused_for_different_intent(tmp_path: Path):
    store, task, running = running_task(tmp_path)
    store.begin_execution_receipt(
        task["id"], running["lease_token"], capability_id="filesystem-read",
        operation="read", idempotency_key="same-key", request_hash="a" * 64,
    )
    with pytest.raises(ValueError, match="different operation"):
        store.begin_execution_receipt(
            task["id"], running["lease_token"], capability_id="filesystem-read",
            operation="read", idempotency_key="same-key", request_hash="b" * 64,
        )


def test_receipt_cannot_be_finalized_twice_or_by_another_task(tmp_path: Path):
    store, task, running = running_task(tmp_path)
    receipt = store.begin_execution_receipt(
        task["id"], running["lease_token"], capability_id="filesystem-read",
        operation="read", idempotency_key="once", request_hash="c" * 64,
    )
    store.finish_execution_receipt(
        task["id"], running["lease_token"], receipt["id"], result={"ok": True}
    )
    with pytest.raises(ValueError, match="already finalized"):
        store.finish_execution_receipt(
            task["id"], running["lease_token"], receipt["id"], result={"ok": True}
        )


def test_receipt_requires_current_lease(tmp_path: Path):
    store, task, running = running_task(tmp_path)
    with pytest.raises(PermissionError, match="active running-task lease"):
        store.begin_execution_receipt(
            task["id"], "wrong-lease", capability_id="filesystem-read",
            operation="read", idempotency_key="bad", request_hash="d" * 64,
        )



def test_expired_lease_with_started_receipt_fails_for_manual_reconciliation(tmp_path: Path):
    store, task, running = running_task(tmp_path)
    store.begin_execution_receipt(
        task["id"], running["lease_token"], capability_id="filesystem-read",
        operation="read", idempotency_key="uncertain-op", request_hash="e" * 64,
    )
    with store._connection() as db:
        db.execute(
            "UPDATE tasks SET lease_until=? WHERE id=?",
            ("2000-01-01T00:00:00+00:00", task["id"]),
        )
    assert store.recover_expired_leases() == 1
    recovered = store.get_task(task["id"])
    assert recovered["status"] == "failed"
    assert "manual reconciliation" in recovered["last_error"]
