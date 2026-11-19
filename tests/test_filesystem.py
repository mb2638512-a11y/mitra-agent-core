from pathlib import Path

import pytest

from mitra.filesystem import Workspace


def test_lists_and_reads_only_workspace_files(tmp_path: Path):
    workspace = Workspace(tmp_path / "workspace")
    (workspace.root / "notes").mkdir()
    (workspace.root / "notes" / "hello.txt").write_text("hello", encoding="utf-8")
    assert workspace.list_files()[0]["name"] == "notes"
    result = workspace.read_text("notes/hello.txt")
    assert result["content"] == "hello"
    assert result["path"] == "notes/hello.txt"


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", "notes/../../outside.txt"])
def test_rejects_absolute_and_traversal_paths(tmp_path: Path, path: str):
    workspace = Workspace(tmp_path / "workspace")
    with pytest.raises(PermissionError):
        workspace.read_text(path)


def test_rejects_symlink_escape(tmp_path: Path):
    workspace = Workspace(tmp_path / "workspace")
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (workspace.root / "escape.txt").symlink_to(outside)
    with pytest.raises(PermissionError):
        workspace.read_text("escape.txt")


def test_enforces_read_size_limit(tmp_path: Path):
    workspace = Workspace(tmp_path / "workspace", max_read_bytes=4)
    (workspace.root / "large.txt").write_text("12345", encoding="utf-8")
    with pytest.raises(ValueError, match="read limit"):
        workspace.read_text("large.txt")


def test_rejects_binary_file(tmp_path: Path):
    workspace = Workspace(tmp_path / "workspace")
    (workspace.root / "binary.bin").write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="UTF-8"):
        workspace.read_text("binary.bin")
