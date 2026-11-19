# Host setup and clone isolation

MITRA speaks MCP. A host needs an MCP client and a way to launch or reach the MITRA server. This guide covers host config formats we currently generate.

## Claude Desktop

After installing MITRA into a Python environment:

```bash
mitra connect --host claude-desktop
```

This safely merges a `mitra` entry into the Claude Desktop JSON config without removing other MCP servers. Restart Claude Desktop.

## Cursor

```bash
mitra connect --host cursor
```

This updates the Cursor MCP JSON config. Reload/restart Cursor to discover the tools.

## Other MCP hosts

Use the generic config option to merge into a host's MCP JSON config:

```bash
mitra connect --config /path/to/host-mcp-config.json
```

Or use this equivalent entry in the host's configuration (replace the Python executable path with the environment where MITRA is installed):

```json
{
  "mcpServers": {
    "mitra": {
      "command": "python",
      "args": ["-m", "mitra.cli", "serve"],
      "env": {"MITRA_INSTANCE_ID": "agent-profile"}
    }
  }
}
```

## Per-agent identity

Set a different `MITRA_INSTANCE_ID` for each host profile. For example, `claude-primary`, `minimax-work`, `gemini-research`. Each ID gets a separate SQLite database and memory directory.

A provider/host may use a different configuration format or may not expose MCP at all. In those cases, use its documented adapter or a bridge; do not assume that one config file can connect every product.

## Safety notes

- The connector writes only the selected MCP config file and preserves other JSON keys.
- It refuses to overwrite malformed JSON.
- Host restart/reload may be required.
- MITRA currently records tasks and stores local memory; it does not yet send email or execute external tasks.
