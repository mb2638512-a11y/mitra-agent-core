import pytest

from mitra.engine import validate_transition
from mitra.planner import TaskPlan
from mitra.security import RiskLevel


def test_plan_validates_and_normalizes_steps():
    plan = TaskPlan.from_dict({
        "objective": "Prepare a report",
        "success_criteria": ["Report saved"],
        "steps": [{"description": "Read source", "capability": "files"}],
    })
    assert plan.steps[0].id == "step-1"
    assert plan.steps[0].risk is RiskLevel.READ
    assert plan.to_dict()["objective"] == "Prepare a report"


def test_plan_rejects_empty_success_criteria():
    with pytest.raises(ValueError):
        TaskPlan.from_dict({"objective": "x", "success_criteria": [], "steps": [{"description": "x", "capability": "x"}]})


def test_external_step_requires_approval_flag():
    plan = TaskPlan.from_dict({
        "objective": "Send message", "success_criteria": ["Sent"],
        "steps": [{"description": "Send", "capability": "email", "risk": "external"}],
    })
    assert plan.steps[0].requires_approval


def test_running_requires_explicit_approval_for_external():
    with pytest.raises(PermissionError):
        validate_transition("awaiting_approval", "running", risk=RiskLevel.EXTERNAL)
    validate_transition("awaiting_approval", "running", approved=True, risk=RiskLevel.EXTERNAL)


def test_terminal_state_cannot_restart():
    with pytest.raises(ValueError):
        validate_transition("completed", "running")
