from pathlib import Path

import pytest

from mitra.store import Store
from mitra.security import issue_approval_token


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
    assert gated["lease_token"] is None
    secret = "approval-secret-for-tests-only-123456"
    approval = issue_approval_token(task["id"], "local-host-user", secret)
    approved = store.approve_task(task["id"], approval, secret)
    assert approved["status"] == "running"
    assert store.task_events(task["id"])[0]["event"] == "approved_and_started"
    with pytest.raises(PermissionError, match="already been used"):
        store.approve_task(task["id"], approval, secret)


def test_idempotency_key_prevents_duplicate_task(tmp_path: Path):
    store = Store(tmp_path / "queue.sqlite3")
    first = store.create_task("One", idempotency_key="request-123")
    second = store.create_task("One again", idempotency_key="request-123")
    assert first["id"] == second["id"]
    assert len(store.list_tasks()) == 1


def test_retry_budget_and_cancel(tmp_path: Path):
    store = Store(tmp_path / "queue.sqlite3")
    task = store.create_task("Retry me", max_attempts=1)
    store.claim_task()
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
    store.claim_task(lease_seconds=5)
    with store._connection() as db:
        db.execute(
            "UPDATE tasks SET lease_until='2000-01-01T00:00:00+00:00' WHERE id=?",
            (task["id"],),
        )
    assert store.recover_expired_leases() == 1
    recovered = store.get_task(task["id"])
    assert recovered["status"] == "queued"
    assert recovered["lease_token"] is None

def test_lease_heartbeat_and_queue_stats(tmp_path: Path):
    store = Store(tmp_path / "queue.sqlite3")
    task = store.create_task("Long running")
    claimed = store.claim_task(lease_seconds=60)
    renewed = store.renew_lease(task["id"], claimed["lease_token"], lease_seconds=120)
    assert renewed["lease_until"] > claimed["lease_until"]
    assert store.queue_stats()["planning"] == 1
    with pytest.raises(PermissionError):
        store.renew_lease(task["id"], "wrong-token", lease_seconds=60)


from pathlib import Path

import pytest

from mitra.store import Store


def test_expired_planning_lease_cannot_start(tmp_path: Path):
    store = Store(tmp_path / "queue.sqlite3")
    task = store.create_task("Expired plan")
    claimed = store.claim_task(lease_seconds=5)
    with store._connection() as db:
        db.execute(
            "UPDATE tasks SET lease_until='2000-01-01T00:00:00+00:00' WHERE id=?",
            (task["id"],),
        )
    with pytest.raises(PermissionError, match="unexpired"):
        store.start_task(task["id"], claimed["lease_token"])


def test_expired_running_lease_cannot_begin_verification(tmp_path: Path):
    store = Store(tmp_path / "queue.sqlite3")
    task = store.create_task("Expired run")
    claimed = store.claim_task()
    store.start_task(task["id"], claimed["lease_token"])
    with store._connection() as db:
        db.execute(
            "UPDATE tasks SET lease_until='2000-01-01T00:00:00+00:00' WHERE id=?",
            (task["id"],),
        )
    with pytest.raises(PermissionError, match="unexpired"):
        store.begin_verification(task["id"], claimed["lease_token"])
