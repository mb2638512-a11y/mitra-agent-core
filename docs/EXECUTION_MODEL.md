# MITRA planning and execution model

## Current milestone

MITRA has a model-independent plan contract and a durable SQLite task queue. Tasks survive process restarts, worker claims use an atomic transaction, leases expire, retry budgets are bounded, and lifecycle events are recorded. The queue is an orchestration primitive: it does not itself run shell commands, browse sites, send messages, move money or mutate third-party systems.

## Plan contract

A plan contains one objective, 1–20 measurable success criteria, and 1–30 steps. Each step has a capability name and risk level: `read`, `write`, `external`, `financial` or `destructive`. Non-read steps require an approval gate.

## Durable task lifecycle

`queued → planning → awaiting_approval → running → verifying → completed`

A worker claims one queued task and receives a random lease token. The claim only moves the task into planning. Starting a high-impact task without an approver label moves it to `awaiting_approval`. A later start call must supply an approver label; that label is recorded in the task event log. This is an auditable *claim*, not verified human identity: a production host must authenticate the approving user and bind the identity to the approval request before enabling real side-effect adapters.

Workers must retain the lease token to start, verify and finish a task. Expired leases can be recovered; tasks are requeued only while retry budget remains. Idempotency keys prevent duplicate task creation for the same caller-supplied request key. Cancellation revokes the active lease. Retry delays are bounded to one day and attempts are capped at ten.

## MCP queue tools

- `mitra_claim_task`: atomically claim one queued task for planning.
- `mitra_start_task`: start a task after risk policy checks; high-impact tasks need an approver label.
- `mitra_begin_verification` and `mitra_finish_task`: explicit verification/finalization.
- `mitra_retry_task`, `mitra_cancel_task`, `mitra_recover_expired_leases`.
- `mitra_task_events`: read the task audit history.

## Not enabled yet

No capability executor is connected. The worker lifecycle does not execute arbitrary code or external actions. Next gates are authenticated approval records, heartbeat/lease renewal, process worker loop, capability allowlists, per-step execution receipts, OAuth adapters and mock-service integration tests. Each executor must enforce policy immediately before side effects.
