# Capability adapter contract

MITRA adapters are small, explicit capability implementations. The shared contract is in `src/mitra/adapters.py`:

- `AdapterContext` carries the current instance ID and data directory.
- `AdapterResult` returns a structured success/data/error result.
- `CapabilityAdapter` declares a stable capability ID, minimum risk, supported operations and an execute method.
- `AdapterRegistry` is an explicit per-process allowlist. It rejects duplicate IDs and never imports modules dynamically.

The first adapter is `filesystem-read`. It supports only `list` and `read` against the instance workspace. A `write` operation is rejected. The MCP server constructs and registers this adapter directly.

## Execution boundary

The task queue does not call adapters. This separation is intentional: adding an adapter does not silently make it autonomous. Before an adapter can be called by a worker, MITRA still needs a central execution gate that validates the registered capability, operation allowlist, task-intent fingerprint, risk policy, approval state, lease ownership and an audit receipt immediately before the side effect.

External adapters must additionally implement least-privilege OAuth or scoped credentials, bounded timeouts, idempotency, redacted logs and mock-service tests. Never add arbitrary shell execution as a generic adapter.
