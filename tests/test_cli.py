import json
from pathlib import Path

from mitra.cli import connect_host


def test_connect_forwards_local_approval_secret_without_overwriting_other_servers(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MITRA_INSTANCE_ID", "test-agent")
    monkeypatch.setenv("MITRA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("MITRA_APPROVAL_SECRET", "x" * 48)
    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps({"mcpServers": {"other": {"command": "other"}}}), encoding="utf-8")

    assert connect_host("claude-desktop", str(config_path)) == 0
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["mcpServers"]["other"] == {"command": "other"}
    mitra = saved["mcpServers"]["mitra"]
    assert mitra["env"]["MITRA_INSTANCE_ID"] == "test-agent"
    assert mitra["env"]["MITRA_HOME"] == str(tmp_path / "data")
    assert mitra["env"]["MITRA_APPROVAL_SECRET"] == "x" * 48
