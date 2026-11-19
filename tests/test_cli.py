import json
from pathlib import Path

from mitra.cli import connect_host


def test_connect_preserves_other_servers_and_does_not_export_signing_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MITRA_INSTANCE_ID", "test-agent")
    monkeypatch.setenv("MITRA_HOME", str(tmp_path / "data"))
    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps({"mcpServers": {"other": {"command": "other"}}}), encoding="utf-8")

    assert connect_host("claude-desktop", str(config_path)) == 0
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["mcpServers"]["other"] == {"command": "other"}
    mitra = saved["mcpServers"]["mitra"]
    assert mitra["env"]["MITRA_INSTANCE_ID"] == "test-agent"
    assert mitra["env"]["MITRA_HOME"] == str(tmp_path / "data")
    assert "MITRA_APPROVAL_SECRET" not in mitra["env"]
