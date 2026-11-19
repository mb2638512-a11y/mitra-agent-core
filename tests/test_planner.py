import pytest

from mitra.engine import validate_transition
from mitra.planner import TaskPlan
from mitra.security import RiskLevel
from mitra.planner import draft_plan
from mitra.providers import ModelReply


def test_plan_validates_and_normalizes_steps():
    plan = TaskPlan.from_dict({
        "objective": "Prepare a report",
        "success_criteria": ["Report saved"],
        "steps": [{"description": "Read source", "capability": "filesystem-read"}],
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
        "steps": [{"description": "Send", "capability": "gmail", "risk": "external"}],
    })
    assert plan.steps[0].requires_approval


def test_running_requires_signed_approval_flow_for_external():
    with pytest.raises(PermissionError, match="authenticated approval"):
        validate_transition("planning", "running", risk=RiskLevel.EXTERNAL)
    with pytest.raises(PermissionError, match="mitra_approve_task"):
        validate_transition("awaiting_approval", "running", risk=RiskLevel.EXTERNAL)


def test_terminal_state_cannot_restart():
    with pytest.raises(ValueError):
        validate_transition("completed", "running")

def test_plan_rejects_unregistered_capability():
    with pytest.raises(ValueError, match="unknown capability"):
        TaskPlan.from_dict({
            "objective": "Do something", "success_criteria": ["Done"],
            "steps": [{"description": "Run", "capability": "made-up-tool"}],
        })


def test_plan_cannot_understate_registered_capability_risk():
    with pytest.raises(ValueError, match="below capability minimum"):
        TaskPlan.from_dict({
            "objective": "Send email", "success_criteria": ["Sent"],
            "steps": [{"description": "Send", "capability": "gmail", "risk": "read"}],
        })



class FakeProvider:
    def __init__(self, content: str):
        self.content = content
        self.messages = None

    def complete(self, messages):
        self.messages = messages
        return ModelReply(content=self.content, model="fake-model", usage={"total_tokens": 10})


def test_model_plan_is_parsed_and_capabilities_are_validated():
    provider = FakeProvider(
        '{"objective":"Summarize a note","success_criteria":["Summary saved"],'
        '"steps":[{"description":"Read note","capability":"filesystem-read","risk":"read"}]}'
    )
    result = draft_plan(provider, "Summarize a note")
    assert result["plan"]["objective"] == "Summarize a note"
    assert result["model"] == "fake-model"
    assert "ready capabilities" in provider.messages[0].content


def test_model_plan_rejects_planned_external_adapter():
    provider = FakeProvider(
        '{"objective":"Send email","success_criteria":["Sent"],'
        '"steps":[{"description":"Send email","capability":"gmail","risk":"external"}]}'
    )
    with pytest.raises(ValueError, match="without a ready adapter"):
        draft_plan(provider, "Send email")


def test_model_plan_rejects_non_json_output():
    with pytest.raises(ValueError, match="valid JSON"):
        draft_plan(FakeProvider("Here is a plan."), "Do something")
