"""Safe task lifecycle primitives; no shell, browser or network execution."""
from __future__ import annotations

from mitra.security import RiskLevel, evaluate_action

TASK_STATES = {
    "queued", "planning", "awaiting_approval", "running",
    "verifying", "completed", "failed", "cancelled",
}
TRANSITIONS = {
    "queued": {"planning", "cancelled"},
    "planning": {"awaiting_approval", "running", "failed", "cancelled"},
    "awaiting_approval": {"running", "cancelled"},
    "running": {"verifying", "failed", "cancelled"},
    "verifying": {"completed", "failed", "running", "cancelled"},
    "completed": set(), "failed": set(), "cancelled": set(),
}


def validate_transition(current: str, target: str, *, approved: bool = False,
                        risk: RiskLevel = RiskLevel.READ) -> None:
    if current not in TASK_STATES or target not in TASK_STATES:
        raise ValueError("unknown task state")
    if target not in TRANSITIONS[current]:
        raise ValueError(f"invalid task transition: {current} -> {target}")
    if current == "awaiting_approval" and target == "running" and not approved:
        raise PermissionError("explicit approval is required before execution")
    decision = evaluate_action(risk, approved=approved)
    if target == "running" and not decision.allowed:
        raise PermissionError(decision.reason)
