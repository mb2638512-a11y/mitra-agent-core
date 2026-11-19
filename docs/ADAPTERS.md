# Capability adapter contract

MITRA adapters are small, explicit capability implementations. The shared contract is in `src/mitra/adapters.py`:

- `AdapterContext` carries the current instance ID and data directory.
- `AdapterResult` returns a structured success/data/error result.
- `CapabilityAdapter` declares a stable capability ID, minimum risk, supported operations and an execute method.
- `AdapterRegistry` is an explicit per-process allowlist. It rejects duplicate IDs and never imports modules dynamically.

The first adapter is `filesystem-read`. It supports only `list` and `read` against the instance workspace. A `write` operation is rejected. The MCP server constructs and registers this adapter directly.

## Execution boundary

The task queue does not call adapters. This separation is intentional: adding an adapter does not silently make it autonomous. The `authorize_adapter_execution` gate now checks that the task is running under an unexpired lease, the capability is registered as ready, the adapter is explicitly installed, the operation is allowlisted, and task risk is at least the adapter's minimum risk. Elevated-risk tasks can reach running only through the signed approval path. This gate returns a permit but does not call the adapter. A supervised worker, durable per-step execution receipts and idempotent side-effect handling are still required before any external adapter is enabled.

External adapters must additionally implement least-privilege OAuth or scoped credentials, bounded timeouts, idempotency, redacted logs and mock-service tests. Never add arbitrary shell execution as a generic adapter.


## Durable execution receipts

The SQLite store now persists one receipt per adapter operation. A receipt records the task, capability, operation, idempotency key, request hash, status, timestamps and bounded result/error. Receipt creation is atomic with checking the current running-task lease. Reusing an idempotency key for different request content is rejected. A receipt can be finalized once, and only while the task lease remains valid.

A receipt left in `started` after a process crash is intentionally not replayed automatically: a process may have stopped after the external system completed an action but before MITRA recorded the result. The operator must reconcile that uncertain outcome before retrying. The MCP tool `mitra_execution_receipts` exposes the history.

These receipts are the durable audit foundation, not proof that an external operation actually happened. No external side-effect worker is enabled by this change.
