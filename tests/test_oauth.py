import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from mitra.credentials import CredentialVault
from mitra.oauth import complete_oauth_flow, start_oauth_flow


def make_vault(tmp_path: Path):
    return CredentialVault(
        tmp_path / "credentials.sqlite3", tmp_path / "vault.key", instance_id="oauth-test"
    )


def test_oauth_pkce_flow_stores_tokens_encrypted_and_consumes_state(tmp_path: Path, monkeypatch):
    vault = make_vault(tmp_path)
    started = start_oauth_flow(
        vault,
        provider="google",
        account_id="user@example.test",
        authorization_endpoint="https://accounts.example.test/oauth/authorize",
        token_endpoint="https://accounts.example.test/oauth/token",
        client_id="client-id",
        redirect_uri="http://127.0.0.1:8766/callback",
        scopes=["profile.read", "calendar.read"],
    )
    parsed = urlparse(started["authorization_url"])
    query = parse_qs(parsed.query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] == [started["state"]]
    pending = vault.get("_oauth_pending", started["state"])
    assert pending["verifier"]
    assert pending["client_id"] == "client-id"

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            return json.dumps({
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
                "token_type": "Bearer",
                "expires_in": 3600,
            }).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["body"] = parse_qs(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    metadata = complete_oauth_flow(
        vault, state=started["state"], authorization_code="one-time-code"
    )
    assert metadata["provider"] == "google"
    assert captured["body"]["code_verifier"] == [pending["verifier"]]
    assert vault.get("google", "user@example.test")["access_token"] == "access-secret"
    assert vault.get("_oauth_pending", started["state"]) is None
    with pytest.raises(PermissionError, match="unknown or already consumed"):
        complete_oauth_flow(vault, state=started["state"], authorization_code="again")


def test_oauth_rejects_insecure_remote_endpoints(tmp_path: Path):
    with pytest.raises(ValueError, match="HTTPS"):
        start_oauth_flow(
            make_vault(tmp_path),
            provider="google",
            account_id="user",
            authorization_endpoint="http://accounts.example.test/authorize",
            token_endpoint="https://accounts.example.test/token",
            client_id="client",
            redirect_uri="http://127.0.0.1:8766/callback",
            scopes=["profile.read"],
        )


def test_oauth_extra_parameters_cannot_override_pkce_or_state(tmp_path: Path):
    with pytest.raises(ValueError, match="protected"):
        start_oauth_flow(
            make_vault(tmp_path),
            provider="google",
            account_id="user",
            authorization_endpoint="https://accounts.example.test/authorize",
            token_endpoint="https://accounts.example.test/token",
            client_id="client",
            redirect_uri="http://127.0.0.1:8766/callback",
            scopes=["profile.read"],
            extra_parameters={"state": "fixed"},
        )
