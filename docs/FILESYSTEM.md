# Scoped filesystem access

MITRA provides a workspace under each instance's local data directory:
`<instance-data-dir>/workspace`. The MCP tools `mitra_fs_list` and
`mitra_fs_read` cannot address arbitrary absolute paths, parent directories,
or symlinks. Text reads are limited to 1 MB by default.

This is a defense-in-depth boundary, not an operating-system sandbox. The user
running MITRA still controls the process and its files. Do not expose the workspace
to untrusted users or run MITRA with elevated privileges.

## Approved workspace writes

The separate filesystem-write adapter supports only UTF-8 text writes within this workspace. It rejects absolute paths, traversal, symlinks, missing parent directories and content larger than 1 MB. It does not create folders, delete files, run commands or access arbitrary OS paths.

The MCP action mitra_execute_workspace_write accepts only task details encoded as JSON with exactly four keys: capability=filesystem-write, operation=write, path, and content.

Create that task with risk write. The normal lifecycle moves it to awaiting_approval. Issue a local token with `mitra approve-token --task-id TASK_ID --approver "local operator"`, then pass the token to `mitra_approve_task`. Only the resulting running lease can invoke the write tool.

Each write is recorded in SQLite with a request hash and idempotency key. A completed operation is not repeated. If the process stops after the receipt is reserved but before the result is recorded, the receipt remains started and the tool refuses to replay it automatically. Reconcile the file and receipt before creating a new task. The approval token demonstrates possession of the local instance key, not third-party identity.

This is still a local-process security boundary, not an OS sandbox. Keep the MITRA data directory private and do not expose the write tool to untrusted clients.
