import json
from pathlib import Path

from mitra.cli import connect_host, universal_setup


def test_connect_preserves_other_servers_and_does_not_export_signing_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MITRA_INSTANCE_ID", "test-agent")
    monkeypatch.setenv("MITRA_HOME", str(tmp_path / "data"))
    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps({"mcpServers": {"other": {"command": "other"}}}), encoding="utf-8")

    assert connect_host(custom_path=str(config_path)) == 0
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["mcpServers"]["other"] == {"command": "other"}
    mitra = saved["mcpServers"]["mitra"]
    assert mitra["env"]["MITRA_INSTANCE_ID"] == "test-agent"
    assert mitra["env"]["MITRA_HOME"] == str(tmp_path / "data")
    assert "MITRA_APPROVAL_SECRET" not in mitra["env"]



def test_universal_setup_prints_generic_mcp_config(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("MITRA_INSTANCE_ID", "universal-agent")
    monkeypatch.setenv("MITRA_HOME", str(tmp_path / "instances"))
    assert universal_setup("Universal Agent") == 0
    output = capsys.readouterr().out
    config_text = output.split("Universal MCP client configuration (JSON):", 1)[1]
    config = json.loads(config_text.split("\\n\\nPaste this", 1)[0])
    entry = config["mcpServers"]["mitra"]
    assert entry["env"]["MITRA_INSTANCE_ID"] == "universal-agent"
    assert entry["args"] == ["-m", "mitra.cli", "serve"]
    assert "claude" not in output.lower()
