from pathlib import Path

from mitra.store import Store


def test_task_round_trip(tmp_path: Path):
    store = Store(tmp_path / "test.sqlite3")
    task = store.create_task("Prepare launch plan", "Draft milestones")
    assert task["title"] == "Prepare launch plan"
    assert task["status"] == "queued"
    assert store.get_task(task["id"])["details"] == "Draft milestones"


def test_memory_round_trip(tmp_path: Path):
    store = Store(tmp_path / "test.sqlite3")
    saved = store.save_memory("MITRA is local-first", ["architecture"])
    results = store.search_memory("local-first")
    assert results[0]["id"] == saved["id"]
    assert results[0]["tags"] == ["architecture"]
