# MITRA — Universal Agent Core

**A cloneable, local-first capability layer for AI agents.** Each agent gets its own MCP tools, task ledger, memory store, identity profile and permission policy. MITRA is not a hosted AI model and does not require a central MITRA cloud.

## Design principles

- **Cloneable:** every host can run an independent MITRA instance.
- **MCP-native:** stdio by default; Streamable HTTP is opt-in.
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
mitra connect --host claude-desktop
```

Restart Claude Desktop after connecting. For Cursor, use `mitra connect --host cursor`. See [Host setup](docs/HOST_SETUP.md).

The default server uses **stdio**: the MCP host launches MITRA as a subprocess. No port, frontend or cloud account is needed.

## Isolated clones

Give every host/agent a unique instance ID before running `mitra init` and `mitra connect`:

```bash
# Example: Claude profile
# Windows PowerShell: $env:MITRA_INSTANCE_ID="claude-primary"
# macOS/Linux: export MITRA_INSTANCE_ID=claude-primary
mitra init --name "Claude's MITRA"

# A separate MiniMax profile uses another instance ID:
# export MITRA_INSTANCE_ID=minimax-work
mitra init --name "MiniMax's MITRA"
```

Each instance has its own local database. A host must support MCP and allow local server configuration; connection is not magically automatic in every product.

## MCP tools in v0.1

- `mitra_status` — instance identity and subsystem status.
- `mitra_fs_list`, `mitra_fs_read` — list and read files inside the instance workspace.
- `mitra_execute_workspace_write` — perform a task-bound, approved text write inside the workspace.
- `mitra_execution_receipts` — inspect durable, idempotent operation receipts.
- `mitra_capabilities`, `mitra_get_capability` — machine-readable registry, status, risk and required scopes.
- `mitra_adapter_status` — inspect the explicit adapters registered in this MITRA process.
- `mitra_create_task`, `mitra_list_tasks`, `mitra_get_task` — local task ledger.
- `mitra_save_memory`, `mitra_search_memory` — instance-local memory.
- `mitra_check_permission` — inspect default risk policy; does not authorize an external action.
- `mitra_draft_plan` — optionally ask the configured model to draft a plan, then validate its JSON and ready adapters.
- `mitra_validate_plan` — validate a structured plan against registered capabilities and minimum risk levels.
- `mitra_check_transition` — preview a task-state change and approval gate.
- `mitra_claim_task`, `mitra_start_task` — durable worker claims and risk-gated start.
- `mitra_approve_task` — verify and consume a signed, task-bound, single-use approval token before issuing a fresh lease.
- `mitra_begin_verification`, `mitra_finish_task` — explicit task verification/finalization.
- `mitra_heartbeat_task`, `mitra_queue_stats` — lease renewal and queue health.
- `mitra_retry_task`, `mitra_cancel_task`, `mitra_recover_expired_leases` — retry, cancellation and crash recovery.
- `mitra_task_events` — task lifecycle audit history.

## Scoped workspace

Files are exposed only from `<instance-data-dir>/workspace`. The adapter rejects absolute paths, traversal and symlinks; it reads UTF-8 text only and enforces a 1 MB limit. Approved text writes are available through the separate filesystem-write adapter, with task-bound approval and durable idempotency receipts. See [Filesystem access](docs/FILESYSTEM.md).

## Capability registry

MITRA maintains stable capability IDs with readiness (ready, optional, planned), minimum risk levels, required scopes and adapter identifiers. Plan validation rejects unknown capability IDs and prevents a plan from understating a capability's minimum risk. Planned capabilities are descriptive only; they cannot be executed until an adapter is installed. A typed adapter contract and explicit in-process allowlist are active. `authorize_adapter_execution` checks the active task lease, ready capability, installed adapter, operation allowlist and minimum risk. The filesystem write tool additionally requires an approved running task and records a durable idempotency receipt. No background worker or external-service adapter is enabled yet.

## Authenticated local approvals

High-impact tasks cannot be started with an `approved_by` label. MITRA creates a per-instance signing key at `<instance-data-dir>/approval.key` on first use. On POSIX systems it is created with owner-only mode (`0600`); on Windows it inherits permissions from the user's private application-data directory. The key is not copied into MCP host JSON and must never be committed or shared.

When a task reaches `awaiting_approval`, the local user issues a short-lived token:

```powershell
# Use the same MITRA_INSTANCE_ID and MITRA_HOME as the MCP host
mitra approve-token --task-id TASK_ID --approver "Your local identity"
```

Pass the resulting one-time token to `mitra_approve_task`. Tokens are HMAC-signed, bound to the task ID and a SHA-256 fingerprint of its title, details and risk, expire within 30–600 seconds, and their nonce is consumed once in the same SQLite transaction that issues the worker lease. This proves local control of the instance key, not identity through an external identity provider. Protect the operating-system account and instance data directory accordingly.


## Verify on Windows

From the repository root in PowerShell, run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\check.ps1
```

The script creates a local virtual environment, installs the project and development dependencies, runs pytest, then runs Ruff. It does not start external integrations or modify files outside the repository's local workspace.

## Optional model provider

MITRA includes a stdlib-only OpenAI-compatible chat adapter. It is opt-in and makes no network calls unless application code explicitly calls it. Configure:

```text
MITRA_MODEL_BASE_URL=https://api.example.com/v1
MITRA_MODEL_NAME=your-model-name
MITRA_MODEL_API_KEY_ENV=MITRA_MODEL_API_KEY
```

Set the actual `MITRA_MODEL_API_KEY` secret in the process environment or an OS secret manager. Never put a real key in `.env.example`, source control, task plans or memory. The MCP tool `mitra_draft_plan` uses this provider to propose JSON plans and validates every proposed capability against the ready adapter registry. Model output never executes automatically; write steps still require a task and signed local approval.

## Instance data

- Windows: `%LOCALAPPDATA%/MITRA/instances/<instance-id>/`
- macOS: `~/Library/Application Support/MITRA/instances/<instance-id>/`
- Linux: `$XDG_DATA_HOME/mitra/instances/<instance-id>/` or `~/.local/share/mitra/instances/<instance-id>/`

Override with `MITRA_HOME`. Do not commit instance data, OAuth tokens or API keys.

## Optional local HTTP transport

`mitra serve-http` starts Streamable HTTP on `127.0.0.1:8765`. It is intentionally localhost-only. Do not expose it publicly without authentication, TLS, transport protections and rate limiting.

## Current scope

This is the first foundation, not finished AGI. The durable queue manages task state; the only side-effecting adapter currently enabled is the approved, receipt-tracked text write inside the instance workspace. External services and OS-level commands are not executed. Gated task approval now requires a short-lived HMAC token bound to the task and a single-use nonce. This proves possession of the local approval secret, not identity through an external identity provider. Gmail, browser automation, autonomous sales, payment operations, multi-agent delegation, model routing and enterprise controls remain planned adapter modules and require scoped credentials, audit trails and tests before production use.

- [Architecture](docs/ARCHITECTURE.md)
- [Execution model](docs/EXECUTION_MODEL.md)
- [Adapter contract](docs/ADAPTERS.md)
- [Business roadmap](docs/BUSINESS_ROADMAP.md)
- [Security policy](SECURITY.md)

## License

MIT License — see [LICENSE](LICENSE).
