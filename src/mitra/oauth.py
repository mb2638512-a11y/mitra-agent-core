"""OAuth 2.0 Authorization Code + PKCE helpers; tokens are stored in CredentialVault."""

from __future__ import annotations

import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from hashlib import sha256
from typing import Any

from mitra.credentials import CredentialVault


def _validate_endpoint(value: str, label: str) -> None:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError(f"{label} must use HTTPS (HTTP is allowed only for localhost callbacks)")


def start_oauth_flow(
    vault: CredentialVault,
    *,
    provider: str,
    account_id: str,
    authorization_endpoint: str,
    token_endpoint: str,
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    extra_parameters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a PKCE authorization URL and keep the verifier encrypted locally."""
    CredentialVault._validate_identity(provider, account_id)
    _validate_endpoint(authorization_endpoint, "authorization endpoint")
    _validate_endpoint(token_endpoint, "token endpoint")
    _validate_endpoint(redirect_uri, "redirect URI")
    if not isinstance(client_id, str) or not client_id.strip() or len(client_id) > 500:
        raise ValueError("client_id must contain 1-500 characters")
    if not scopes or any(not isinstance(scope, str) or not scope.strip() for scope in scopes):
        raise ValueError("at least one non-empty OAuth scope is required")
    if extra_parameters and any(
        key in {"state", "code_challenge", "code_challenge_method", "client_id",
                "redirect_uri", "response_type", "scope"}
        for key in extra_parameters
    ):
        raise ValueError("extra parameters cannot override protected OAuth fields")

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = __import__("base64").urlsafe_b64encode(
        sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    pending = {
        "provider": provider,
        "account_id": account_id,
        "verifier": verifier,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "token_endpoint": token_endpoint,
        "created_at": int(time.time()),
    }
    vault.put("_oauth_pending", state, pending)
    parameters = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if extra_parameters:
        parameters.update(extra_parameters)
    separator = "&" if "?" in authorization_endpoint else "?"
    return {
        "authorization_url": authorization_endpoint + separator + urllib.parse.urlencode(parameters),
        "state": state,
        "expires_in": 600,
    }


def complete_oauth_flow(
    vault: CredentialVault,
    *,
    state: str,
    authorization_code: str,
    client_secret_env: str | None = None,
) -> dict[str, Any]:
    """Exchange a one-time authorization code, save encrypted tokens and consume state."""
    if not state or len(state) > 200:
        raise ValueError("invalid OAuth state")
    if not authorization_code or len(authorization_code) > 4000:
        raise ValueError("invalid authorization code")
    pending = vault.get("_oauth_pending", state)
    if pending is None:
        raise PermissionError("OAuth state is unknown or already consumed")
    if int(time.time()) - int(pending.get("created_at", 0)) > 600:
        vault.delete("_oauth_pending", state)
        raise PermissionError("OAuth state has expired")
    form = {
        "grant_type": "authorization_code",
        "code": authorization_code,
        "client_id": pending["client_id"],
        "redirect_uri": pending["redirect_uri"],
        "code_verifier": pending["verifier"],
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    if client_secret_env:
        if not client_secret_env.isidentifier():
            raise ValueError("client_secret_env must be an environment variable name")
        client_secret = os.environ.get(client_secret_env)
        if not client_secret:
            raise RuntimeError("OAuth client secret environment variable is not set")
        form["client_secret"] = client_secret
    request = urllib.request.Request(
        pending["token_endpoint"],
        data=urllib.parse.urlencode(form).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise RuntimeError("OAuth token response exceeds 64 KB")
        token_data = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"OAuth token endpoint returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"OAuth token exchange failed: {type(exc).__name__}") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("OAuth token endpoint returned invalid JSON") from None
    if not isinstance(token_data, dict) or not isinstance(token_data.get("access_token"), str):
        raise RuntimeError("OAuth token response did not contain an access token")
    metadata = vault.put(pending["provider"], pending["account_id"], token_data)
    vault.delete("_oauth_pending", state)
    return metadata
