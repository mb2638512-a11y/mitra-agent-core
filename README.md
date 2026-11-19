# MITRA — Universal Agent Core

**A cloneable, local-first capability layer for AI agents.** MITRA gives each agent its own MCP tools, task ledger, memory store, identity profile and permission policy. It is not a hosted AI model and does not require a central MITRA cloud.

## Design principles

- **Cloneable:** every host can run an independent MITRA instance.
- **MCP-native:** exposes tools over stdio by default; Streamable HTTP is opt-in.
- **Agent-owned:** data, credentials and memory belong to the instance owner.
- **Least privilege:** integrations are explicit; high-impact actions require approval.
- **Model-agnostic:** compatible MCP hosts can use the same capability layer.
- **Honest autonomy:** MITRA supplies capabilities and governance; the connected host/model supplies reasoning unless a model provider is configured separately.

## Quick start

Requirements: Python 3.11+.

```bash
git clone https://github.com/mb2638512-a11y/mitra-agent-core.git
cd mitra-agent-core
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
mitra init --name my-agent
mitra serve
```

The default server uses **stdio**, so the MCP host launches it as a subprocess. No port, web frontend or cloud account is needed.

## MCP tools in v0.1

- `mitra_status` — instance identity and subsystem status.
- `mitra_capabilities` — capability readiness and roadmap status.
- `mitra_create_task`, `mitra_list_tasks`, `mitra_get_task` — local task ledger.
- `mitra_save_memory`, `mitra_search_memory` — instance-local memory.
- `mitra_check_permission` — inspect default risk policy; does not authorize an external action.

## Connect to an MCP host

Use the host's MCP configuration format. A typical stdio entry is:

```json
{
  "mcpServers": {
    "mitra": {
      "command": "mitra",
      "args": ["serve"],
      "env": {
        "MITRA_INSTANCE_ID": "claude-primary"
      }
    }
  }
}
```

For another agent, use a different `MITRA_INSTANCE_ID` (for example `minimax-work`) to keep memory and task data isolated. The host must support MCP and allow local server configuration; connection is not magically automatic in every product.

## Instance data

- Windows: `%LOCALAPPDATA%/MITRA/instances/<instance-id>/`
- macOS: `~/Library/Application Support/MITRA/instances/<instance-id>/`
- Linux: `$XDG_DATA_HOME/mitra/instances/<instance-id>/` or `~/.local/share/mitra/instances/<instance-id>/`

Override with `MITRA_HOME`. Do not commit instance data, OAuth tokens or API keys.

## Optional local HTTP transport

`mitra serve-http` starts Streamable HTTP on `127.0.0.1:8765`. It is intentionally localhost-only. Do not expose it publicly without authentication, TLS, transport protections and rate limiting.

## Current scope

This is the first working foundation, not finished AGI. Gmail, browser automation, autonomous sales, payment operations, multi-agent delegation, model routing and enterprise controls are planned adapter modules. They must be implemented with explicit authorization, scoped credentials, audit trails and tests before being advertised as available.

## Roadmap

See [Architecture](docs/ARCHITECTURE.md) and [Business roadmap](docs/BUSINESS_ROADMAP.md).

## Security

MITRA does not create Gmail accounts without a supported provider flow. Users authorize their own mailbox or an administrator provisions a Workspace mailbox. Secrets must be supplied through secure local mechanisms; never paste them into issues or commit them. See [SECURITY.md](SECURITY.md).

## License

MIT License — see [LICENSE](LICENSE).
