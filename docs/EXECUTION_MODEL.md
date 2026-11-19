# MITRA planning and execution model

## Current milestone

MITRA has a model-independent plan contract and a durable SQLite task queue. Tasks survive process restarts, worker claims use an atomic transaction, leases expire, retry budgets are bounded, and lifecycle events are recorded. The queue is an orchestration primitive: it does not itself run shell commands, browse sites, send messages, move money or mutate third-party systems.

## Plan contract

A plan contains one objective, 1–20 measurable success criteria, and 1–30 steps. Each step has a capability name and risk level: `read`, `write`, `external`, `financial` or `destructive`. Non-read steps require an approval gate.

## Durable task lifecycle

`queued → planning → awaiting_approval → running → verifying → completed`

A worker claims one queued task and receives a random lease token. The claim only moves the task into planning. Starting a high-impact task moves it to `awaiting_approval`. A local user issues a short-lived HMAC approval token using `mitra approve-token`; `mitra_approve_task` verifies that the token is signed by the configured local secret, bound to the exact task, unexpired and unused. The nonce is consumed transactionally in SQLite before a fresh worker lease is issued. This proves possession of the local secret, not identity from an external identity provider.

Workers must retain the lease token to start, verify and finish a task. Expired leases can be recovered; tasks are requeued only while retry budget remains. Idempotency keys prevent duplicate task creation for the same caller-supplied request key. Cancellation revokes the active lease. Retry delays are bounded to one day and attempts are capped at ten.

## MCP queue tools

- `mitra_claim_task`: atomically claim one queued task for planning.
- `mitra_start_task`: start read-only work or place high-impact work into the approval queue.
- `mitra_approve_task`: verify a short-lived, task-bound, single-use HMAC token and issue a fresh lease.
- `mitra_begin_verification` and `mitra_finish_task`: explicit verification/finalization.
- `mitra_heartbeat_task`: renew an unexpired lease while work is in progress.
- `mitra_queue_stats`: count tasks by lifecycle state.
- `mitra_retry_task`, `mitra_cancel_task`, `mitra_recover_expired_leases`.
- `mitra_task_events`: read the task audit history.

## Scoped filesystem read adapter

The current read adapter exposes only the per-instance `workspace` directory through `mitra_fs_list` and `mitra_fs_read`. It rejects absolute paths, traversal segments and symlinks, and limits UTF-8 text reads to 1 MB. It does not write files or access arbitrary system paths. The workspace boundary is defense in depth, not an OS sandbox.

## Not enabled yet

No capability executor is connected. The worker lifecycle does not execute arbitrary code or external actions. Next gates are external identity-provider integration, process worker loop, capability allowlists, per-step execution receipts, OAuth adapters and mock-service integration tests. Each executor must enforce policy immediately before side effects.
