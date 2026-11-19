"""Command-line bootstrapper for independent MITRA instances."""

from __future__ import annotations

import argparse
import json
import os

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
    print("Connect this instance to an MCP host using: mitra serve")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="mitra", description="MITRA Universal Agent Core")
    sub = parser.add_subparsers(dest="command")
    init = sub.add_parser("init", help="initialize this agent's isolated profile")
    init.add_argument("--name", default="My MITRA Agent")
    sub.add_parser("serve", help="start the MCP server over stdio")
    sub.add_parser("serve-http", help="start an opt-in local Streamable HTTP MCP server")
    args = parser.parse_args()

    if args.command == "init":
        raise SystemExit(init_instance(args.name))
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
