"""Validated, model-independent task-plan contracts.

The connected host model may produce a plan, but MITRA validates and stores it.
This module does not execute steps or call external services.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from mitra.security import RiskLevel


@dataclass(frozen=True)
class PlanStep:
    id: str
    description: str
    capability: str
    risk: RiskLevel = RiskLevel.READ
    requires_approval: bool = False


@dataclass(frozen=True)
class TaskPlan:
    objective: str
    success_criteria: tuple[str, ...]
    steps: tuple[PlanStep, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TaskPlan":
        if not isinstance(value, dict):
            raise ValueError("plan must be an object")
        objective = str(value.get("objective", "")).strip()
        criteria = value.get("success_criteria", [])
        raw_steps = value.get("steps", [])
        if not objective or len(objective) > 2000:
            raise ValueError("objective must contain 1-2000 characters")
        if not isinstance(criteria, list) or not 1 <= len(criteria) <= 20:
            raise ValueError("success_criteria must contain 1-20 items")
        if any(not isinstance(x, str) or not x.strip() or len(x) > 500 for x in criteria):
            raise ValueError("each success criterion must contain 1-500 characters")
        if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= 30:
            raise ValueError("steps must contain 1-30 items")
        steps = []
        for index, item in enumerate(raw_steps, start=1):
            if not isinstance(item, dict):
                raise ValueError("each step must be an object")
            description = str(item.get("description", "")).strip()
            capability = str(item.get("capability", "")).strip()
            try:
                risk = RiskLevel(item.get("risk", "read"))
            except ValueError as exc:
                raise ValueError("step risk must be read, write, external, financial or destructive") from exc
            if not description or len(description) > 1000 or not capability or len(capability) > 100:
                raise ValueError("each step needs a description (1-1000) and capability (1-100)")
            steps.append(PlanStep(
                id=str(item.get("id") or f"step-{index}"),
                description=description,
                capability=capability,
                risk=risk,
                requires_approval=risk is not RiskLevel.READ or bool(item.get("requires_approval", False)),
            ))
        return cls(objective, tuple(x.strip() for x in criteria), tuple(steps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "success_criteria": list(self.success_criteria),
            "steps": [
                {**asdict(step), "risk": step.risk.value}
                for step in self.steps
            ],
        }
