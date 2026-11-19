from pathlib import Path

import pytest

from mitra.store import Store


def test_atomic_queue_lifecycle_and_audit(tmp_path: Path):
    store = Store(tmp_path / "queue.sqlite3")
    task = store.create_task("Build report")
    claimed = store.claim_task()
    assert claimed["id"] == task["id"]
    assert claimed["status"] == "planning"
    assert store.claim_task() is None

    running = store.start_task(task["id"], claimed["lease_token"])
    assert running["status"] == "running"
    verifying = store.begin_verification(task["id"], claimed["lease_token"])
    assert verifying["status"] == "verifying"
    done = store.finish_task(task["id"], claimed["lease_token"], success=True)
    assert done["status"] == "completed"
    assert [event["event"] for event in store.task_events(task["id"])] == [
        "completed", "verification_started", "started", "claimed", "created"
    ]


def test_high_impact_task_waits_for_explicit_approval(tmp_path: Path):
    store = Store(tmp_path / "queue.sqlite3")
    task = store.create_task("Send an email", risk="external")
    claimed = store.claim_task()
    gated = store.start_task(task["id"], claimed["lease_token"])
    assert gated["status"] == "awaiting_approval"
    approved = store.start_task(task["id"], claimed["lease_token"], approved=True)
    assert approved["status"] == "running"


def test_idempotency_key_prevents_duplicate_task(tmp_path: Path):
    store = Store(tmp_path / "queue.sqlite3")
    first = store.create_task("One", idempotency_key="request-123")
    second = store.create_task("One again", idempotency_key="request-123")
    assert first["id"] == second["id"]
    assert len(store.list_tasks()) == 1


def test_retry_budget_and_cancel(tmp_path: Path):
    store = Store(tmp_path / "queue.sqlite3")
    task = store.create_task("Retry me", max_attempts=1)
    claimed = store.claim_task()
    result = store.retry_task(task["id"], delay_seconds=1, reason="temporary error")
    assert result["status"] == "failed"

    pending = store.create_task("Cancel me")
    cancelled = store.cancel_task(pending["id"])
    assert cancelled["status"] == "cancelled"
    with pytest.raises(ValueError):
        store.cancel_task(pending["id"])


def test_lease_recovery_requeues_expired_worker(tmp_path: Path):
    store = Store(tmp_path / "queue.sqlite3")
    task = store.create_task("Recover me")
    claimed = store.claim_task(lease_seconds=5)
    with store._connection() as db:
        db.execute(
            "UPDATE tasks SET lease_until='2000-01-01T00:00:00+00:00' WHERE id=?",
            (task["id"],),
        )
    assert store.recover_expired_leases() == 1
    recovered = store.get_task(task["id"])
    assert recovered["status"] == "queued"
    assert recovered["lease_token"] is None
