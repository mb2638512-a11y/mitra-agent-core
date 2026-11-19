# Security policy

## v0.1 security posture

- Each instance stores its task and memory database in its own local data directory.
- Instance IDs are validated to prevent path traversal.
- No secrets or OAuth tokens are included in the repository.
- Task creation records intent only; it does not send email, spend money or modify third-party services.
- High-impact operations are default-denied until a complete approval and audit flow exists.

## Before enabling integrations

1. Use provider OAuth with minimum required scopes; do not collect user passwords.
2. Encrypt refresh tokens at rest using an OS keychain or vetted secret manager.
3. Bind each credential to an instance and capability; do not share tokens across clones by default.
4. Require explicit approval for external communications, purchases, financial transfers and destructive changes.
5. Record actor, tool, redacted arguments, approval and outcome in an append-only audit trail.
6. Provide token revocation, capability disablement and data export/deletion.
7. For network-exposed MCP, configure authentication, TLS, origin/DNS-rebinding protections and rate limits. Do not expose local HTTP mode directly to the public internet.

## Reporting

Report vulnerabilities privately to the repository maintainer. Do not publish working exploit details in public issues.
