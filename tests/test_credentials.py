from pathlib import Path

import pytest

from mitra.credentials import CredentialVault


def make_vault(tmp_path: Path, instance_id: str = "agent-one"):
    return CredentialVault(
        tmp_path / "credentials.sqlite3",
        tmp_path / "vault.key",
        instance_id=instance_id,
    )


def test_credential_vault_round_trip_and_metadata_never_exposes_tokens(tmp_path: Path):
    vault = make_vault(tmp_path)
    secret = {"access_token": "very-secret-token", "refresh_token": "refresh-secret"}
    metadata = vault.put("google", "account@example.test", secret)
    assert metadata["provider"] == "google"
    assert vault.get("google", "account@example.test") == secret
    listed = vault.list_metadata()
    assert listed == [{
        "provider": "google", "account_id": "account@example.test",
        "updated_at": metadata["updated_at"],
    }]
    raw_db = (tmp_path / "credentials.sqlite3").read_bytes()
    assert b"very-secret-token" not in raw_db
    assert b"refresh-secret" not in raw_db


def test_credential_vault_binds_ciphertext_to_instance_identity(tmp_path: Path):
    vault = make_vault(tmp_path, "agent-one")
    vault.put("google", "account@example.test", {"access_token": "secret"})
    other = CredentialVault(
        tmp_path / "credentials.sqlite3", tmp_path / "vault.key", instance_id="agent-two"
    )
    with pytest.raises(PermissionError, match="authentication failed"):
        other.get("google", "account@example.test")


def test_credential_vault_detects_ciphertext_tampering(tmp_path: Path):
    vault = make_vault(tmp_path)
    vault.put("google", "account@example.test", {"access_token": "secret"})
    with vault._connection() as db:
        db.execute(
            "UPDATE credentials SET ciphertext=? WHERE provider=? AND account_id=?",
            (b"tampered", "google", "account@example.test"),
        )
    with pytest.raises(PermissionError, match="authentication failed"):
        vault.get("google", "account@example.test")


def test_credential_vault_rejects_symlinked_key_file(tmp_path: Path):
    real_key = tmp_path / "real.key"
    real_key.write_bytes(b"x" * 32)
    linked_key = tmp_path / "vault.key"
    linked_key.symlink_to(real_key)
    with pytest.raises(PermissionError, match="symlink"):
        CredentialVault(tmp_path / "db.sqlite3", linked_key, instance_id="agent")


def test_credential_vault_delete_removes_record(tmp_path: Path):
    vault = make_vault(tmp_path)
    vault.put("google", "account@example.test", {"access_token": "secret"})
    assert vault.delete("google", "account@example.test")
    assert vault.get("google", "account@example.test") is None
    assert not vault.delete("google", "account@example.test")



def test_pending_oauth_states_are_not_listed_as_connected_accounts(tmp_path: Path):
    vault = make_vault(tmp_path)
    vault.put("_oauth_pending", "random-state", {"verifier": "temporary"})
    vault.put("google", "user@example.test", {"access_token": "encrypted"})
    assert [item["provider"] for item in vault.list_metadata()] == ["google"]
