# MITRA planning and execution model

## Current milestone

MITRA has a model-independent plan contract and a durable SQLite task queue. Tasks survive process restarts, worker claims use an atomic transaction, leases expire, retry budgets are bounded, and lifecycle events are recorded. The queue is an orchestration primitive: it does not itself run shell commands, browse sites, send messages, move money or mutate third-party systems.

## Plan contract

A plan contains one objective, 1–20 measurable success criteria, and 1–30 steps. Each step has a capability name and risk level: `read`, `write`, `external`, `financial` or `destructive`. Non-read steps require an approval gate.

## Durable task lifecycle

`queued → planning → awaiting_approval → running → verifying → completed`

A worker claims one queued task and receives a random lease token. The claim only moves the task into planning. Starting a high-impact task moves it to `awaiting_approval`. A local user issues a short-lived HMAC approval token using `mitra approve-token`; MITRA signs it with a per-instance key stored in the private local data directory (not in MCP host configuration). `mitra_approve_task` verifies that the token is signed, bound to the exact task, unexpired and unused. The nonce is consumed transactionally in SQLite before a fresh worker lease is issued. This proves possession of the local secret, not identity from an external identity provider.

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

The supervised local worker is available as `mitra worker`. It atomically claims queued tasks and separately reserves approved running tasks. Its explicit handlers support workspace read/list and task-approved text writes only. Each operation checks the live lease, ready capability, adapter allowlist and minimum risk, then records a durable idempotency receipt before finalizing the task. It does not run arbitrary code, shell commands or external actions. Remaining gates are stronger host identity, OAuth adapters, provider-side idempotency and integration tests against mock services.


## Optional model planning

When an OpenAI-compatible provider is configured, `mitra_draft_plan` asks it for a JSON proposal. MITRA parses the response strictly, validates the plan schema, and rejects any step that references a capability without a ready adapter. The prompt includes only ready adapter-backed capabilities. Model output is untrusted: it cannot register tools, lower risk, approve a task or execute a step. A proposed write must still be translated into a specific task intent and pass the local signed-approval flow.


## Worker operation contract

A worker task's JSON details must declare a ready capability, an allowlisted operation and its exact arguments. The current handler supports `filesystem-read` with `read` or `list`, and `filesystem-write` with `write`. Write tasks move to `awaiting_approval`; the worker cannot execute them until the local task-bound approval flow issues a running lease. Unsupported task types are retried under the task's bounded retry budget. Read output is retained in the local execution receipt; the worker's console summary omits file contents.
