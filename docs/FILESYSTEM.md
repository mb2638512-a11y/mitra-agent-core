# Scoped filesystem access

MITRA provides a read-only workspace under each instance's local data directory:
`<instance-data-dir>/workspace`. The MCP tools `mitra_fs_list` and
`mitra_fs_read` cannot address arbitrary absolute paths, parent directories,
or symlinks. Text reads are limited to 1 MB by default.

This is a defense-in-depth boundary, not an operating-system sandbox. The user
running MITRA still controls the process and its files. Do not expose the workspace
to untrusted users or run MITRA with elevated privileges.

Filesystem writes remain planned. High-impact task approval now uses a short-lived,
task-bound HMAC token with a single-use nonce. The token demonstrates possession
of the local approval secret, not third-party identity; a future write adapter must
still add strict allowlists, atomic writes, audit receipts and tests.
