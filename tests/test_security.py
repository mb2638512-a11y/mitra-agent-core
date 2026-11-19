from pathlib import Path

import pytest

from mitra.security import (
    RiskLevel,
    evaluate_action,
    issue_approval_token,
    verify_approval_token,
    load_or_create_approval_secret,
)


def test_read_action_allowed():
    decision = evaluate_action(RiskLevel.READ)
    assert decision.allowed
    assert not decision.requires_approval


def test_external_action_requires_approval():
    decision = evaluate_action(RiskLevel.EXTERNAL)
    assert not decision.allowed
    assert decision.requires_approval


def test_signed_approval_token_is_task_bound():
    secret = "x" * 48
    token = issue_approval_token("task-1", "local-user", secret)
    claims = verify_approval_token(token, "task-1", secret)
    assert claims["approver"] == "local-user"
    with pytest.raises(PermissionError):
        verify_approval_token(token, "task-2", secret)


def test_approval_token_rejects_wrong_secret_and_tampering():
    token = issue_approval_token("task-1", "local-user", "s" * 48)
    with pytest.raises(PermissionError):
        verify_approval_token(token, "task-1", "z" * 48)
    body, signature = token.split(".", 1)
    tampered = body[:-1] + ("A" if body[-1] != "A" else "B") + "." + signature
    with pytest.raises(PermissionError):
        verify_approval_token(tampered, "task-1", "s" * 48)


def test_token_configuration_and_lifetime_are_bounded():
    with pytest.raises(ValueError):
        issue_approval_token("task-1", "user", "short")
    with pytest.raises(ValueError):
        issue_approval_token("task-1", "user", "s" * 48, expires_in=9999)


def test_instance_approval_key_is_created_once_and_reused(tmp_path: Path):
    key_path = tmp_path / "private" / "approval.key"
    first = load_or_create_approval_secret(key_path)
    second = load_or_create_approval_secret(key_path)
    assert len(first) >= 32
    assert second == first
    assert key_path.exists()
    if __import__("os").name != "nt":
        assert key_path.stat().st_mode & 0o777 == 0o600
