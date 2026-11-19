"""Command-line bootstrapper and host connector for independent MITRA instances."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from mitra.config import InstanceConfig


def init_instance(name: str) -> int:
    os.environ["MITRA_DISPLAY_NAME"] = name
    config = InstanceConfig.load()
    profile = {
        "product": "MITRA",
        "instance_id": config.instance_id,
        "display_name": name,
        "data_dir": str(config.data_dir),
        "transport": "stdio",
        "created_by": "mitra init",
    }
    profile_path = config.data_dir / "profile.json"
    if profile_path.exists():
        print(f"Profile already exists: {profile_path}")
        return 0
    profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(f"Initialized {name} ({config.instance_id}) at {config.data_dir}")
    return 0


def default_host_config(host: str) -> Path:
    if host == "claude-desktop":
        if sys.platform == "win32":
            base = Path(os.getenv("APPDATA", Path.home() / "AppData/Roaming"))
            return base / "Claude" / "claude_desktop_config.json"
        if sys.platform == "darwin":
            return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
        return Path.home() / ".config/Claude/claude_desktop_config.json"
    if host == "cursor":
        return Path.home() / ".cursor" / "mcp.json"
    raise ValueError(f"Unsupported host: {host}")


def connect_host(host: str, custom_path: str | None = None) -> int:
    config = InstanceConfig.load()
    config_path = Path(custom_path).expanduser() if custom_path else default_host_config(host)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    existing = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Cannot safely edit invalid JSON at {config_path}: {exc}") from exc
    if not isinstance(existing, dict):
        raise SystemExit(f"Expected a JSON object in {config_path}")

    servers = existing.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise SystemExit(f"'mcpServers' must be a JSON object in {config_path}")

    entry = {
        "command": sys.executable,
        "args": ["-m", "mitra.cli", "serve"],
        "env": {"MITRA_INSTANCE_ID": config.instance_id},
    }
    if os.getenv("MITRA_HOME"):
        entry["env"]["MITRA_HOME"] = os.environ["MITRA_HOME"]
    servers["mitra"] = entry

    temporary = config_path.with_suffix(config_path.suffix + ".tmp")
    temporary.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    temporary.replace(config_path)
    print(f"Connected MITRA instance '{config.instance_id}' in {config_path}")
    print("Restart or reload the MCP host to discover MITRA tools.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="mitra", description="MITRA Universal Agent Core")
    sub = parser.add_subparsers(dest="command")
    init = sub.add_parser("init", help="initialize this agent's isolated profile")
    init.add_argument("--name", default="My MITRA Agent")
    sub.add_parser("serve", help="start the MCP server over stdio")
    sub.add_parser("serve-http", help="start an opt-in local Streamable HTTP MCP server")
    connect = sub.add_parser("connect", help="add MITRA to a supported host MCP config")
    connect.add_argument("--host", choices=["claude-desktop", "cursor"], default="claude-desktop")
    connect.add_argument("--config", help="custom MCP JSON config path (overrides host default)")
    args = parser.parse_args()

    if args.command == "init":
        raise SystemExit(init_instance(args.name))
    if args.command == "connect":
        raise SystemExit(connect_host(args.host, args.config))
    if args.command == "serve":
        from mitra.server import mcp
        mcp.run()
        return
    if args.command == "serve-http":
        from mitra.server import mcp
        mcp.run(transport="streamable-http", host="127.0.0.1", port=8765)
        return
    parser.print_help()
    raise SystemExit(0)


if __name__ == "__main__":
    main()
