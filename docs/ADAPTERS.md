# Capability adapter contract

MITRA adapters are small, explicit capability implementations. The shared contract is in `src/mitra/adapters.py`:

- `AdapterContext` carries the current instance ID and data directory.
- `AdapterResult` returns a structured success/data/error result.
- `CapabilityAdapter` declares a stable capability ID, minimum risk, supported operations and an execute method.
- `AdapterRegistry` is an explicit per-process allowlist. It rejects duplicate IDs and never imports modules dynamically.

The first adapters are `filesystem-read` and `filesystem-write`. Read supports only `list` and `read`; write supports only `write` against the instance workspace and is exposed through a task-bound approval flow. The MCP server constructs and registers both adapters directly.

## Execution boundary

The task queue does not call adapters. This separation is intentional: adding an adapter does not silently make it autonomous. The `authorize_adapter_execution` gate now checks that the task is running under an unexpired lease, the capability is registered as ready, the adapter is explicitly installed, the operation is allowlisted, and task risk is at least the adapter's minimum risk. Elevated-risk tasks can reach running only through the signed approval path. The approved workspace-write MCP action uses this gate and then reserves a durable SQLite execution receipt before calling the local adapter. Receipts bind task, capability, operation, idempotency key and request hash. A completed receipt is not replayed; an unfinished receipt after a crash is marked uncertain for manual reconciliation. External adapters still require supervised workers, provider-side idempotency, scoped OAuth, bounded timeouts and independent verification.

External adapters must additionally implement least-privilege OAuth or scoped credentials, bounded timeouts, idempotency, redacted logs and mock-service tests. Never add arbitrary shell execution as a generic adapter.


## Durable execution receipts

The SQLite store now persists one receipt per adapter operation. A receipt records the task, capability, operation, idempotency key, request hash, status, timestamps and bounded result/error. Receipt creation is atomic with checking the current running-task lease. Reusing an idempotency key for different request content is rejected. A receipt can be finalized once, and only while the task lease remains valid.

A receipt left in `started` after a process crash is intentionally not replayed automatically: a process may have stopped after the external system completed an action but before MITRA recorded the result. The operator must reconcile that uncertain outcome before retrying. The MCP tool `mitra_execution_receipts` exposes the history.

These receipts are the durable audit foundation, not proof that a third-party operation happened. The supervised local worker uses receipts for workspace read/list and approved text writes; external-service adapters remain disabled.
