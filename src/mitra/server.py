"""MCP interface for the MITRA local-first core."""

from __future__ import annotations

from mcp.server import MCPServer

from mitra import __version__
from mitra.config import InstanceConfig
from mitra.security import RiskLevel, evaluate_action
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
            "autonomous_execution": "not_enabled",
        },
    }


@mcp.tool()
def mitra_capabilities() -> list[dict]:
    """List built-in capabilities and their current implementation status."""
    return [
        {"id": "mcp-core", "status": "ready", "description": "MCP tools over stdio; HTTP transport is opt-in."},
        {"id": "instance-isolation", "status": "ready", "description": "Separate local data by MITRA_INSTANCE_ID."},
        {"id": "task-ledger", "status": "ready", "description": "Create and inspect task records."},
        {"id": "memory-local", "status": "ready", "description": "SQLite memory with substring retrieval."},
        {"id": "permission-primitives", "status": "ready", "description": "Read-only allowed; high-impact actions default-denied."},
        {"id": "gmail", "status": "planned", "description": "OAuth-based Gmail adapter; user authorization required."},
        {"id": "browser", "status": "planned", "description": "Policy-bound browser adapter with action approvals."},
        {"id": "planner-executor", "status": "planned", "description": "Model-backed planning and auditable execution queue."},
        {"id": "multi-agent", "status": "planned", "description": "Delegation with per-agent identity and scoped tools."},
    ]


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
def mitra_create_task(title: str, details: str = "") -> dict:
    """Record a task in this instance's queue. This does not perform external actions."""
    clean_title = title.strip()
    if not clean_title or len(clean_title) > 200:
        raise ValueError("title must contain 1-200 characters")
    if len(details) > 10_000:
        raise ValueError("details must be at most 10000 characters")
    return store.create_task(clean_title, details)


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


if __name__ == "__main__":
    mcp.run()
