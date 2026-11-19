import pytest

from mitra.engine import validate_transition
from mitra.security import RiskLevel


def test_read_only_planning_transition_is_valid():
    validate_transition("planning", "running", risk=RiskLevel.READ)


def test_elevated_risk_transition_cannot_be_authorized_by_boolean():
    with pytest.raises(PermissionError, match="authenticated approval"):
        validate_transition("planning", "running", risk=RiskLevel.EXTERNAL)


def test_approval_state_requires_token_consumption_path():
    with pytest.raises(PermissionError, match="mitra_approve_task"):
        validate_transition("awaiting_approval", "running", risk=RiskLevel.READ)
