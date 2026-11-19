from mitra.security import RiskLevel, evaluate_action


def test_read_action_allowed():
    decision = evaluate_action(RiskLevel.READ)
    assert decision.allowed
    assert not decision.requires_approval


def test_external_action_requires_approval():
    decision = evaluate_action(RiskLevel.EXTERNAL)
    assert not decision.allowed
    assert decision.requires_approval
