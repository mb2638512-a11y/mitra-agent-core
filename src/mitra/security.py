"""Permission primitives; integrations must enforce these before side effects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    READ = "read"
    WRITE = "write"
    EXTERNAL = "external"
    FINANCIAL = "financial"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    requires_approval: bool
    reason: str


def evaluate_action(risk: RiskLevel, *, approved: bool = False) -> PermissionDecision:
    """Default-deny high-impact actions until an auditable approval flow exists."""
    if risk is RiskLevel.READ:
        return PermissionDecision(True, False, "Read-only action.")
    if approved:
        return PermissionDecision(True, False, "Explicit approval supplied for this action.")
    return PermissionDecision(
        False,
        True,
        f"{risk.value} actions are not enabled in the foundation; implement an auditable approval flow.",
    )
