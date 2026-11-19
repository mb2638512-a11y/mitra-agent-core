"""MCP interface for the MITRA local-first core."""

from __future__ import annotations

from mcp.server import MCPServer

from mitra import __version__
from mitra.config import InstanceConfig
from mitra.security import RiskLevel, evaluate_action
from mitra.planner import TaskPlan
from mitra.engine import validate_transition
from mitra.store import Store

config = InstanceConfig.load()
store = Store(config.data_dir / "mitra.sqlite3")
mcp = MCPServer(
    "MITRA",
    version=__version__,
    instructions=(
        "MITRA is a local-first agent capability core. Inspect capabilities and task state "
        "before acting. Task creation only records intent; it does not execute external actions. "
        "Respect user permissions and request approval for external, financial or destructive work."
    ),
)


@mcp.tool()
def mitra_status() -> dict:
    """Return this MITRA instance's identity, version and local subsystem status."""
    return {
        "name": "MITRA",
        "version": __version__,
        "instance_id": config.instance_id,
        "display_name": config.display_name,
        "storage": "local-sqlite",
        "subsystems": {
            "mcp": "ready",
            "task_ledger": "ready",
            "local_memory": "ready",
            "permission_primitives": "ready",
            "external_integrations": "not_installed",
            "autonomous_execution": "guarded_queue_only",
        },
    }


@mcp.tool()
def mitra_capabilities() -> list[dict]:
    """List built-in capabilities and their current implementation status."""
    return [
        {"id": "mcp-core", "status": "ready", "description": "MCP tools over stdio; HTTP transport is opt-in."},
        {"id": "instance-isolation", "status": "ready", "description": "Separate local data by MITRA_INSTANCE_ID."},
        {"id": "task-ledger", "status": "ready", "description": "Create and inspect durable task records."},
        {"id": "durable-worker-queue", "status": "ready", "description": "Atomic claims, worker leases, bounded retries, cancellation and crash recovery; no external action adapters."},
        {"id": "task-audit", "status": "ready", "description": "Append-only task lifecycle event history."},
        {"id": "memory-local", "status": "ready", "description": "SQLite memory with substring retrieval."},
        {"id": "permission-primitives", "status": "ready", "description": "Read-only allowed; high-impact actions default-denied."},
        {"id": "gmail", "status": "planned", "description": "OAuth-based Gmail adapter; user authorization required."},
        {"id": "browser", "status": "planned", "description": "Policy-bound browser adapter with action approvals."},
        {"id": "plan-contract", "status": "ready", "description": "Validate structured plans and risk-tagged steps."},
        {"id": "guarded-task-lifecycle", "status": "ready", "description": "Validate task-state transitions and approval gates; no workers execute tasks yet."},
        {"id": "model-provider", "status": "ready_optional", "description": "Optional OpenAI-compatible chat provider; credentials are read from an environment variable."},
        {"id": "planner-executor", "status": "in_progress", "description": "Planning contracts are available; durable worker queue and execution adapters remain future work."},
        {"id": "multi-agent", "status": "planned", "description": "Delegation with per-agent identity and scoped tools."},
    ]


@mcp.tool()
def mitra_validate_plan(plan: dict) -> dict:
    """Validate a proposed plan and return normalized steps with approval requirements."""
    return TaskPlan.from_dict(plan).to_dict()


@mcp.tool()
def mitra_check_transition(current: str, target: str, risk: str = "read", approved: bool = False) -> dict:
    """Preview a task-state transition. This checks policy but does not execute work."""
    try:
        level = RiskLevel(risk)
        validate_transition(current, target, approved=approved, risk=level)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    except PermissionError as exc:
        return {"valid": False, "current": current, "target": target, "reason": str(exc)}
    return {"valid": True, "current": current, "target": target, "risk": level.value, "approved": approved}

@mcp.tool()
def mitra_check_permission(risk: str) -> dict:
    """Check the default policy for read, write, external, financial or destructive actions."""
    try:
        level = RiskLevel(risk)
    except ValueError as exc:
        raise ValueError("risk must be one of: read, write, external, financial, destructive") from exc
    decision = evaluate_action(level)
    return {
        "risk": level.value,
        "allowed": decision.allowed,
        "requires_approval": decision.requires_approval,
        "reason": decision.reason,
    }


@mcp.tool()
def mitra_create_task(title: str, details: str = "", risk: str = "read", max_attempts: int = 3, idempotency_key: str = "") -> dict:
    """Record a durable task. High-impact work requires approval; no actions are executed."""
    clean_title = title.strip()
    if not clean_title or len(clean_title) > 200:
        raise ValueError("title must contain 1-200 characters")
    if len(details) > 10_000:
        raise ValueError("details must be at most 10000 characters")
    return store.create_task(clean_title, details, risk=risk, max_attempts=max_attempts, idempotency_key=idempotency_key or None)


@mcp.tool()
def mitra_list_tasks(limit: int = 20) -> list[dict]:
    """List recent tasks for this instance (maximum 100)."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    return store.list_tasks(limit)


@mcp.tool()
def mitra_get_task(task_id: str) -> dict:
    """Get one task by its ID."""
    task = store.get_task(task_id)
    if task is None:
        raise ValueError("Task not found")
    return task


@mcp.tool()
def mitra_save_memory(content: str, tags: list[str] | None = None) -> dict:
    """Save a note in this instance's local memory."""
    clean = content.strip()
    if not clean or len(clean) > 20_000:
        raise ValueError("content must contain 1-20000 characters")
    if tags and (len(tags) > 20 or any(len(tag) > 40 for tag in tags)):
        raise ValueError("Use at most 20 tags, each at most 40 characters")
    return store.save_memory(clean, tags)


@mcp.tool()
def mitra_search_memory(query: str, limit: int = 10) -> list[dict]:
    """Search this instance's local memory using keyword matching."""
    if not query.strip():
        raise ValueError("query cannot be empty")
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    return store.search_memory(query.strip(), limit)


@mcp.tool()
def mitra_claim_task(lease_seconds: int = 60) -> dict:
    """Claim one queued task for planning. This does not execute its actions."""
    task = store.claim_task(lease_seconds=lease_seconds)
    return task or {"claimed": False, "reason": "no eligible queued task"}


@mcp.tool()
def mitra_start_task(task_id: str, lease_token: str, approved_by: str = "") -> dict:
    """Move a claimed task to running; high-impact work records the host-claimed approver label."""
    return store.start_task(task_id, lease_token, approved_by=approved_by or None)


@mcp.tool()
def mitra_approve_task(task_id: str, approved_by: str, lease_seconds: int = 60) -> dict:
    """Approve a gated task using a host-claimed approver label and issue a fresh worker lease."""
    return store.approve_task(task_id, approved_by, lease_seconds=lease_seconds)


@mcp.tool()
def mitra_begin_verification(task_id: str, lease_token: str) -> dict:
    """Mark a running task as ready for independent result verification."""
    return store.begin_verification(task_id, lease_token)


@mcp.tool()
def mitra_finish_task(task_id: str, lease_token: str, success: bool, detail: str = "") -> dict:
    """Finalize a verifying task with an explicit success/failure result."""
    if len(detail) > 2000:
        raise ValueError("detail must be at most 2000 characters")
    return store.finish_task(task_id, lease_token, success=success, detail=detail)


@mcp.tool()
def mitra_retry_task(task_id: str, delay_seconds: int = 30, reason: str = "") -> dict:
    """Schedule a controlled retry for an active task; no action is executed here."""
    return store.retry_task(task_id, delay_seconds=delay_seconds, reason=reason)


@mcp.tool()
def mitra_cancel_task(task_id: str) -> dict:
    """Cancel a non-terminal task and revoke its worker lease."""
    return store.cancel_task(task_id)


@mcp.tool()
def mitra_recover_expired_leases() -> dict:
    """Recover tasks whose worker lease expired after a crash or disconnect."""
    return {"recovered": store.recover_expired_leases()}


@mcp.tool()
def mitra_task_events(task_id: str, limit: int = 50) -> list[dict]:
    """Return the audit events for one task."""
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    if store.get_task(task_id) is None:
        raise ValueError("Task not found")
    return store.task_events(task_id, limit)



if __name__ == "__main__":
    mcp.run()
