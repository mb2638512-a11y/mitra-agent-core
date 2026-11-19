# MITRA planning and execution model

## Current milestone

MITRA now defines a model-independent plan contract and a guarded task-state transition policy. A compatible host model can propose a plan; MITRA validates its shape and classifies each step by risk. The primitives deliberately do not run commands, browse sites, send messages, move money or mutate third-party systems.

## Plan contract

A plan contains:
- one objective;
- 1–20 measurable success criteria;
- 1–30 steps;
- a capability name and risk level per step.

Risk levels are `read`, `write`, `external`, `financial` and `destructive`. Non-read steps are marked as requiring approval by default.

## Task lifecycle

`queued → planning → awaiting_approval → running → verifying → completed`

Planning may move directly to running only for read-only work. Failed and cancelled states are terminal. Verification may return to running for a bounded correction cycle in a future executor implementation.

The current engine validates transitions and approval gates; it is not yet a worker queue. No task is autonomously executed by these primitives.

## Next implementation gates

1. Persist plan JSON, transition history and approval identity.
2. Add bounded worker leases, idempotency keys, timeouts, retry budgets and cancellation.
3. Add provider adapters with secrets supplied only through environment variables or an OS secret store.
4. Add capability-specific executors. Each executor must enforce policy immediately before side effects.
5. Add OAuth integrations with minimal scopes and revocation support.
6. Add integration tests using mock services before enabling real accounts.
