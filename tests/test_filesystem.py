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



def test_workspace_write_is_confined_and_returns_digest(tmp_path: Path):
    workspace = Workspace(tmp_path / "workspace")
    (tmp_path / "workspace" / "reports").mkdir()
    result = workspace.write_text("reports/result.txt", "MITRA report")
    assert result["bytes_written"] == len("MITRA report".encode())
    assert len(result["sha256"]) == 64
    assert (tmp_path / "workspace" / "reports" / "result.txt").read_text(encoding="utf-8") == "MITRA report"
    with pytest.raises(PermissionError):
        workspace.write_text("../outside.txt", "no")


def test_workspace_write_rejects_symlink_target(tmp_path: Path):
    workspace = Workspace(tmp_path / "workspace")
    outside = tmp_path / "outside.txt"
    outside.write_text("safe", encoding="utf-8")
    (tmp_path / "workspace" / "link.txt").symlink_to(outside)
    with pytest.raises(PermissionError, match="symlinks"):
        workspace.write_text("link.txt", "unsafe")
    assert outside.read_text(encoding="utf-8") == "safe"



def test_workspace_rejects_symlinked_root(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "workspace"
    linked.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PermissionError, match="root"):
        Workspace(linked)



def test_workspace_write_rejects_hard_linked_target(tmp_path: Path):
    workspace = Workspace(tmp_path / "workspace")
    outside = tmp_path / "outside.txt"
    outside.write_text("protected", encoding="utf-8")
    linked = workspace.root / "linked.txt"
    linked.hardlink_to(outside)
    with pytest.raises(PermissionError, match="hard-linked"):
        workspace.write_text("linked.txt", "changed")
    assert outside.read_text(encoding="utf-8") == "protected"
