"""Command-line bootstrapper and host connector for independent MITRA instances."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from mitra.config import InstanceConfig
from mitra.security import approval_fingerprint, issue_approval_token, load_or_create_approval_secret
from mitra.store import Store


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



def create_approval_token(task_id: str, approver: str, expires_in: int) -> int:
    config = InstanceConfig.load()
    store = Store(config.data_dir / "mitra.sqlite3")
    task = store.get_task(task_id)
    if task is None:
        raise SystemExit("Task not found in this MITRA instance.")
    if task["status"] != "awaiting_approval":
        raise SystemExit("Only tasks awaiting approval can receive an approval token.")
    secret = load_or_create_approval_secret(config.data_dir / "approval.key")
    try:
        token = issue_approval_token(task_id, approver, secret, intent_fingerprint=approval_fingerprint(task), expires_in=expires_in)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print("One-time approval token (share only with this MITRA instance):")
    print(token)
    print(f"Expires in {expires_in} seconds. Keep the local approval.key file private.")
    return 0


def default_host_config(host: str) -> Path:
    if host == "cursor":
        return Path.home() / ".cursor" / "mcp.json"
    raise ValueError(f"Unsupported host shortcut: {host}. Use --config for any MCP host.")


def mcp_config_entry() -> dict:
    """Return the portable MCP client entry for the active MITRA instance."""
    config = InstanceConfig.load()
    env = {"MITRA_INSTANCE_ID": config.instance_id}
    if os.getenv("MITRA_HOME"):
        env["MITRA_HOME"] = os.environ["MITRA_HOME"]
    return {"command": sys.executable, "args": ["-m", "mitra.cli", "serve"], "env": env}


def connect_host(custom_path: str | None = None, host: str | None = None) -> int:
    if custom_path:
        config_path = Path(custom_path).expanduser()
    elif host:
        config_path = default_host_config(host)
    else:
        raise SystemExit("Choose --config PATH for any MCP host, or an explicit --host shortcut.")
    config = InstanceConfig.load()
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
        raise SystemExit("'mcpServers' must be a JSON object in the selected config")
    servers["mitra"] = mcp_config_entry()
    temporary = config_path.with_suffix(config_path.suffix + ".tmp")
    temporary.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    temporary.replace(config_path)
    print(f"Connected MITRA instance '{config.instance_id}' in {config_path}")
    print("Reload the MCP client to discover MITRA tools.")
    return 0


def universal_setup(name: str, config_path: str | None = None) -> int:
    """One-command bootstrap for any MCP-compatible agent."""
    init_instance(name)
    if config_path:
        return connect_host(custom_path=config_path)
    print("\nUniversal MCP client configuration (JSON):")
    print(json.dumps({"mcpServers": {"mitra": mcp_config_entry()}}, indent=2))
    print("\nPaste this into the MCP configuration of any compatible agent.")
    print("For automatic installation into a config file, rerun with --config PATH.")
    return 0

def main() -> None:
    parser = argparse.ArgumentParser(prog="mitra", description="MITRA Universal Agent Core")
    sub = parser.add_subparsers(dest="command")
    init = sub.add_parser("init", help="initialize this agent's isolated profile")
    init.add_argument("--name", default="My MITRA Agent")
    setup = sub.add_parser("setup", help="universal one-command setup for any MCP-compatible agent")
    setup.add_argument("--name", default="My Agent")
    setup.add_argument("--config", help="optional MCP client JSON config path to update")
    approval = sub.add_parser("approve-token", help="issue a short-lived local approval token")
    approval.add_argument("--task-id", required=True)
    approval.add_argument("--approver", required=True)
    approval.add_argument("--expires-in", type=int, default=300)
    sub.add_parser("serve", help="start the MCP server over stdio")
    sub.add_parser("serve-http", help="start an opt-in local Streamable HTTP MCP server")
    connect = sub.add_parser("connect", help="connect MITRA to any MCP-compatible client")
    connect.add_argument("--config", help="MCP client JSON config path")
    connect.add_argument("--host", choices=["cursor"], help="optional known-host shortcut")
    args = parser.parse_args()

    if args.command == "init":
        raise SystemExit(init_instance(args.name))
    if args.command == "setup":
        raise SystemExit(universal_setup(args.name, args.config))
    if args.command == "connect":
        raise SystemExit(connect_host(custom_path=args.config, host=args.host))
    if args.command == "approve-token":
        raise SystemExit(create_approval_token(args.task_id, args.approver, args.expires_in))
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
