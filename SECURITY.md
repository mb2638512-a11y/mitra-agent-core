# Security policy

## v0.1 security posture

- Each instance stores its task and memory database in its own local data directory.
- Instance IDs are validated to prevent path traversal.
- No secrets or OAuth tokens are included in the repository.
- OAuth tokens are encrypted at rest with AES-256-GCM in a per-instance vault; the 256-bit key is stored separately in a private local file.
- OAuth authorization uses user-consented Authorization Code with PKCE; access and refresh tokens are never returned by MCP tools.
- Task creation records intent only. The supervised worker executes only allowlisted workspace read/list operations and approved local text writes; it does not send email, spend money or modify third-party services.
- High-impact task transitions are default-denied unless a short-lived, task-intent-bound approval token is verified and consumed. No Gmail, Calendar, browser, payment or other third-party action adapter is enabled.

## Before enabling integrations

1. Use provider OAuth with minimum required scopes; do not collect user passwords.
2. Prefer an OS keychain or vetted secret manager for production deployments; the current local vault uses AES-256-GCM with a private per-instance key file.
3. Bind each credential to an instance and capability; do not share tokens across clones by default.
4. Require explicit approval for external communications, purchases, financial transfers and destructive changes.
5. Record actor, tool, redacted arguments, approval and outcome in an append-only audit trail.
6. Implement provider token refresh/revocation, capability disablement and data export/deletion before production OAuth integrations.
7. For network-exposed MCP, configure authentication, TLS, origin/DNS-rebinding protections and rate limits. Do not expose local HTTP mode directly to the public internet.

## Reporting

Report vulnerabilities privately to the repository maintainer. Do not publish working exploit details in public issues.
