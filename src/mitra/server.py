"""MCP interface for the MITRA local-first core."""

from __future__ import annotations

import hashlib
import json
from mcp.server import MCPServer

from mitra import __version__
from mitra.config import InstanceConfig
from mitra.security import RiskLevel, evaluate_action, load_or_create_approval_secret
from mitra.planner import TaskPlan
from mitra.engine import validate_transition
from mitra.store import Store
from mitra.registry import get_capability, list_capabilities
from mitra.adapters import AdapterContext, AdapterRegistry, authorize_adapter_execution
from mitra.filesystem import FilesystemReadAdapter, FilesystemWriteAdapter

config = InstanceConfig.load()
adapter_context = AdapterContext(config.instance_id, config.data_dir)
adapters = AdapterRegistry()
adapters.register(FilesystemReadAdapter())
adapters.register(FilesystemWriteAdapter())
filesystem_adapter = adapters.get("filesystem-read")
if filesystem_adapter is None:
    raise RuntimeError("required filesystem-read adapter failed to register")
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
            "capability_registry": "ready",
            "external_integrations": "not_installed",
            "autonomous_execution": "guarded_queue_only",
        },
    }


@mcp.tool()
def mitra_capabilities(include_planned: bool = True) -> list[dict]:
    """List registered MITRA capabilities, status, risk and required scopes."""
    return list_capabilities(include_planned=include_planned)


@mcp.tool()
def mitra_adapter_status() -> list[dict]:
    """List only the capability adapters explicitly registered in this process."""
    return [
        {
            "capability_id": capability_id,
            "risk": adapters.get(capability_id).risk.value,
            "operations": sorted(adapters.get(capability_id).operations),
        }
        for capability_id in adapters.list_registered()
    ]


@mcp.tool()
def mitra_get_capability(capability_id: str) -> dict:
    """Inspect one capability by its stable registry ID."""
    capability = get_capability(capability_id)
    if capability is None:
        raise ValueError("Unknown capability ID")
    return capability.to_dict()


@mcp.tool()
def mitra_fs_list(path: str = ".", limit: int = 100) -> list[dict]:
    """List entries inside this MITRA instance's read-only workspace."""
    result = filesystem_adapter.execute("list", {"path": path, "limit": limit}, adapter_context)
    return result.data


@mcp.tool()
def mitra_fs_read(path: str) -> dict:
    """Read a UTF-8 text file inside this instance's read-only workspace (max 1 MB)."""
    result = filesystem_adapter.execute("read", {"path": path}, adapter_context)
    return result.data


@mcp.tool()
def mitra_execute_workspace_write(task_id: str, lease_token: str, idempotency_key: str) -> dict:
    """Execute one approved write described by the task's JSON details, inside this instance workspace."""
    task = store.get_task(task_id)
    if task is None:
        raise ValueError("Task not found")
    try:
        intent = json.loads(task["details"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("task details must be valid JSON write intent") from exc
    if not isinstance(intent, dict) or set(intent) != {"capability", "operation", "path", "content"}:
        raise ValueError("write intent must contain exactly capability, operation, path and content")
    if (intent["capability"] != "filesystem-write" or intent["operation"] != "write"
            or not isinstance(intent["path"], str) or not isinstance(intent["content"], str)):
        raise ValueError("task does not describe a valid filesystem write")
    request = {
        "capability": intent["capability"], "operation": intent["operation"],
        "path": intent["path"], "content": intent["content"],
    }
    request_hash = hashlib.sha256(
        json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    permit = authorize_adapter_execution(
        store=store, registry=adapters, instance_id=config.instance_id,
        data_dir=config.data_dir, task_id=task_id, lease_token=lease_token,
        capability_id="filesystem-write", operation="write",
    )
    receipt = store.begin_execution_receipt(
        task_id, lease_token, capability_id="filesystem-write", operation="write",
        idempotency_key=idempotency_key, request_hash=request_hash,
    )
    if not receipt["_created"]:
        if receipt["status"] == "completed":
            return {"receipt_id": receipt["id"], "status": "completed",
                    "result": json.loads(receipt["result_json"])}
        if receipt["status"] == "failed":
            raise RuntimeError("this idempotent operation already failed; inspect its receipt")
        return {"receipt_id": receipt["id"], "status": "started",
                "message": "Outcome is uncertain; reconcile before retrying"}
    try:
        result = permit.adapter.execute(
            permit.operation, {"path": intent["path"], "content": intent["content"]},
            permit.context,
        )
        finalized = store.finish_execution_receipt(
            task_id, lease_token, receipt["id"], result=result.data,
        )
        return {"receipt_id": finalized["id"], "status": finalized["status"],
                "result": result.data}
    except Exception as exc:
        store.finish_execution_receipt(
            task_id, lease_token, receipt["id"], error=str(exc)[:2000],
        )
        raise


@mcp.tool()
def mitra_validate_plan(plan: dict) -> dict:
    """Validate a proposed plan and return normalized steps with approval requirements."""
    return TaskPlan.from_dict(plan).to_dict()


@mcp.tool()
def mitra_check_transition(current: str, target: str, risk: str = "read") -> dict:
    """Preview a task-state transition. This checks policy but does not execute work."""
    try:
        level = RiskLevel(risk)
        validate_transition(current, target, risk=level)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    except PermissionError as exc:
        return {"valid": False, "current": current, "target": target, "reason": str(exc)}
    return {"valid": True, "current": current, "target": target, "risk": level.value, "approval_required": level is not RiskLevel.READ}

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
    if len(details.encode("utf-8")) > 1_050_000:
        raise ValueError("details must be at most 1050000 UTF-8 bytes")
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
def mitra_start_task(task_id: str, lease_token: str) -> dict:
    """Start a read-only task; elevated-risk tasks are moved to awaiting approval."""
    return store.start_task(task_id, lease_token)


@mcp.tool()
def mitra_approve_task(task_id: str, approval_token: str, lease_seconds: int = 60) -> dict:
    """Approve a gated task using a signed, task-bound, single-use local approval token."""
    secret = load_or_create_approval_secret(config.data_dir / "approval.key")
    return store.approve_task(task_id, approval_token, secret, lease_seconds=lease_seconds)


@mcp.tool()
def mitra_heartbeat_task(task_id: str, lease_token: str, lease_seconds: int = 60) -> dict:
    """Renew a valid worker lease before it expires."""
    task = store.renew_lease(task_id, lease_token, lease_seconds=lease_seconds)
    return {"task_id": task["id"], "status": task["status"], "lease_until": task["lease_until"]}


@mcp.tool()
def mitra_execution_receipts(task_id: str, limit: int = 50) -> list[dict]:
    """Inspect durable adapter-operation receipts for one task."""
    if store.get_task(task_id) is None:
        raise ValueError("Task not found")
    return store.execution_receipts(task_id, limit)


@mcp.tool()
def mitra_queue_stats() -> dict:
    """Return counts of tasks in each lifecycle state."""
    return store.queue_stats()


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
