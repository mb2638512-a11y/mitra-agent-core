# MITRA architecture

## Product boundary

MITRA is a portable capability runtime, not a cloud-hosted personality and not an LLM. An AI host (any MCP-compatible assistant, IDE agent or custom runtime) connects to a local MITRA MCP server. The host remains responsible for model inference and agent policy; MITRA provides tools, local state, adapters and guardrails.

## Instance model

Each host profile should have a unique `MITRA_INSTANCE_ID`. Each instance owns:
- profile and preferences;
- task ledger and execution history;
- local memory;
- separately authorized provider credentials;
- installed capability manifest;
- permission policy and audit log.

No credentials or personal memory are shared between clones by default. A user can explicitly export/import selected data.

## Runtime layers

1. **Bootstrapper:** install, initialize, upgrade, diagnose and remove an instance.
2. **MCP surface:** expose tools/resources/prompts over stdio; opt-in Streamable HTTP for supported remote hosts.
3. **Capability registry:** manifest, version, dependencies, permissions and health state for each adapter.
4. **Identity and credential vault:** provider OAuth, token refresh, encryption and revocation.
5. **Memory:** structured records, searchable notes, embeddings as an optional provider, retention controls.
6. **Task engine:** durable queue, states, retries, cancellation, deadlines and idempotency keys.
7. **Planner/executor:** model-agnostic plans, validation, tool selection and result verification.
8. **Policy engine:** least privilege, approvals, budgets, allowlists, deny rules and audit trail.
9. **Agent federation:** optional delegation to other MITRA instances through authenticated, scoped channels.
10. **Observability:** structured logs, metrics, traces, health and exportable diagnostics.

## Trust boundaries

- The model proposes; the runtime validates.
- An MCP tool is a capability boundary, not permission to do everything.
- External, financial and destructive actions require explicit policy and approval.
- Secrets never enter prompts, logs or repository files.
- Remote HTTP transport is disabled by default and must be protected before network exposure.
- Every adapter declares its scopes and side effects before installation.

## Initial implementation status

| Area | v0.1 status |
|---|---|
| MCP stdio server | Implemented |
| Local instance separation | Implemented |
| SQLite task ledger | Implemented |
| Local keyword memory | Implemented |
| Permission primitives | Implemented |
| Capability registry and risk metadata | Implemented |
| Plan-to-capability validation | Implemented |
| Scoped filesystem workspace | Read and approved text write implemented; path confinement, symlink rejection and size limits |
| Durable task queue, leases and audit events | Implemented |
| Per-instance AES-256-GCM credential vault and OAuth PKCE flow | Implemented foundation; provider-specific API adapters remain planned |
| Gmail / calendar / drive adapters | Planned |
| Browser automation | Planned |

| Supervised local worker | Implemented for workspace read/list and approved text writes; no shell or external execution |
| Multi-provider model routing and plan drafting | Implemented; named routes, ordered fallback, strict JSON and ready-adapter validation |
| Agent-to-agent federation | Planned |
| Enterprise multi-tenant controls | Planned |

## Compatibility strategy

MCP is the common interface where a host supports it. For products without native MCP support, future adapters can expose a CLI, SDK or REST bridge. The project must not claim universal auto-connection: each host has its own configuration and security model.
