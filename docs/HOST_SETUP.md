# Universal MCP host setup

MITRA does not require one specific AI application. It exposes a standard MCP server over stdio. Any agent or desktop client that supports MCP and permits a local stdio server can connect to its own MITRA instance.

## One universal command

Install MITRA in a Python 3.11+ environment, then run:

```bash
mitra setup --name "My Agent"
```

This initializes an isolated local profile and prints a portable `mcpServers` JSON entry. Copy the entry into the MCP configuration for the agent you want to connect.

To initialize and merge the entry into a known MCP JSON configuration in one command:

```bash
mitra setup --name "My Agent" --config /path/to/your-agent-mcp.json
```

The command preserves other JSON keys and other MCP servers. It refuses malformed JSON rather than overwriting it.

## Existing profile

To connect an already initialized profile to another MCP client:

```bash
mitra connect --config /path/to/your-agent-mcp.json
```

MITRA also provides a small optional Cursor shortcut:

```bash
mitra connect --host cursor
```

The generic `--config` mode is the portable route for all other MCP-compatible clients. MITRA cannot auto-configure a host that does not expose a supported configuration file or local MCP server feature.

## Manual configuration shape

The universal command prints the exact values for the current Python environment and instance. The portable shape is:

```json
{
  "mcpServers": {
    "mitra": {
      "command": "python",
      "args": ["-m", "mitra.cli", "serve"],
      "env": {
        "MITRA_INSTANCE_ID": "agent-profile"
      }
    }
  }
}
```

Use the Python executable from the environment where MITRA is installed. On Windows, the command normally prints the full path to that interpreter.

## Independent agent identities

Give each agent a distinct `MITRA_INSTANCE_ID`. Each instance has its own local SQLite database, memory, approval key and workspace. A connected host receives only the instance specified in its MCP entry.

## Host compatibility

- MCP support is required.
- Local stdio process launch is required for this configuration shape.
- Some hosted agents accept remote MCP only; those require a separately secured HTTP deployment or a supported bridge.
- A product that does not support MCP needs a custom adapter or bridge. A JSON snippet alone cannot add MCP support to that product.

## Security

- Keep each instance data directory private.
- Never copy `approval.key` into an MCP config or share it between agents.
- The setup command writes only the selected MCP config file.
- Reload the host after updating its configuration.
