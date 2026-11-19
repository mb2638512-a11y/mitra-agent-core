"""Permission policy and signed, short-lived approval tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
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
    if risk is RiskLevel.READ:
        return PermissionDecision(True, False, "Read-only action.")
    if approved:
        return PermissionDecision(True, False, "A verified approval token was supplied.")
    return PermissionDecision(False, True, f"{risk.value} actions require authenticated approval.")


def issue_approval_token(task_id: str, approver: str, secret: str, *, expires_in: int = 300) -> str:
    """Create a task-bound HMAC token. The secret must come from a trusted local environment."""
    if not secret or len(secret) < 32:
        raise ValueError("MITRA_APPROVAL_SECRET must contain at least 32 characters")
    if not task_id or not approver.strip() or len(approver) > 200:
        raise ValueError("task_id and a 1-200 character approver are required")
    if not 30 <= expires_in <= 600:
        raise ValueError("expires_in must be between 30 and 600 seconds")
    payload = {
        "task_id": task_id,
        "approver": approver.strip(),
        "expires_at": int(time.time()) + expires_in,
        "nonce": secrets.token_urlsafe(24),
    }
    body = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def verify_approval_token(token: str, task_id: str, secret: str) -> dict:
    if not secret or len(secret) < 32:
        raise PermissionError("approval secret is not configured securely")
    try:
        body, supplied_signature = token.split(".", 1)
        expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected):
            raise ValueError("signature mismatch")
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        if payload["task_id"] != task_id:
            raise ValueError("task mismatch")
        if int(payload["expires_at"]) < int(time.time()):
            raise ValueError("token expired")
        if not payload["approver"] or not payload["nonce"]:
            raise ValueError("missing claims")
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise PermissionError("approval token is invalid, expired or not for this task") from exc
