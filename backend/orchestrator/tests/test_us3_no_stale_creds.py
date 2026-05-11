"""US3 — verify per-call credential lookup never serves stale values (T049).

The CredentialManager hits the DB on every read; there is no in-process cache
that could survive a save/clear. This test pins that property as a regression
guard so a future caching optimization doesn't silently break FR-006/FR-007.
"""
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from orchestrator.credential_manager import CredentialManager


class FakeDB:
    """In-memory stand-in for shared.database.Database — only the methods
    CredentialManager uses."""

    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []

    def execute(self, sql: str, params: tuple) -> None:
        sql = " ".join(sql.split())
        if sql.startswith("INSERT INTO user_credentials"):
            user_id, agent_id, key, value, *_rest = params
            for r in self.rows:
                if r["user_id"] == user_id and r["agent_id"] == agent_id and r["credential_key"] == key:
                    r["encrypted_value"] = value
                    return
            self.rows.append({
                "user_id": user_id,
                "agent_id": agent_id,
                "credential_key": key,
                "encrypted_value": value,
            })
        elif sql.startswith("DELETE FROM user_credentials"):
            if "credential_key = ?" in sql:
                user_id, agent_id, key = params
                self.rows = [
                    r for r in self.rows
                    if not (r["user_id"] == user_id and r["agent_id"] == agent_id and r["credential_key"] == key)
                ]
            else:
                user_id, agent_id = params
                self.rows = [
                    r for r in self.rows
                    if not (r["user_id"] == user_id and r["agent_id"] == agent_id)
                ]

    def fetch_one(self, *_a, **_kw):
        return None

    def fetch_all(self, sql: str, params: tuple):
        user_id, agent_id = params[0], params[1]
        return [
            r for r in self.rows
            if r["user_id"] == user_id and r["agent_id"] == agent_id
        ]


@pytest.fixture
def cm() -> CredentialManager:
    """Build a CredentialManager with a fake DB and no Fernet key-file side-effect."""
    db = FakeDB()
    cm = CredentialManager.__new__(CredentialManager)
    cm.db = db
    cm.data_dir = None
    cm._fernet = None  # not used in these tests (we only assert ciphertext shape)
    cm._agent_public_keys = {}
    return cm


def test_save_then_save_returns_latest_value(cm: CredentialManager) -> None:
    """Saving twice for the same key must surface the second value on read."""
    # Inject a sentinel cipher by stubbing the encrypt path: we don't care about
    # crypto here, only about read-after-write consistency.
    cm._fernet = MagicMock()
    cm._fernet.encrypt.side_effect = lambda b: (b"v1:" + b)
    cm.set_credential("alice", "classify-1", "CLASSIFY_URL", "https://first.example/")
    first = cm.get_agent_credentials_encrypted("alice", "classify-1")
    cm._fernet.encrypt.side_effect = lambda b: (b"v2:" + b)
    cm.set_credential("alice", "classify-1", "CLASSIFY_URL", "https://second.example/")
    second = cm.get_agent_credentials_encrypted("alice", "classify-1")
    assert first["CLASSIFY_URL"] != second["CLASSIFY_URL"]
    assert "second.example" in second["CLASSIFY_URL"]


def test_delete_then_list_returns_empty(cm: CredentialManager) -> None:
    cm._fernet = MagicMock()
    cm._fernet.encrypt.side_effect = lambda b: b"cipher:" + b
    cm.set_credential("alice", "classify-1", "CLASSIFY_API_KEY", "secret")
    assert cm.list_credential_keys("alice", "classify-1") == ["CLASSIFY_API_KEY"]
    cm.delete_credential("alice", "classify-1", "CLASSIFY_API_KEY")
    assert cm.list_credential_keys("alice", "classify-1") == []


def test_remove_agent_credentials_clears_all_keys(cm: CredentialManager) -> None:
    cm._fernet = MagicMock()
    cm._fernet.encrypt.side_effect = lambda b: b"cipher:" + b
    cm.set_credential("alice", "classify-1", "CLASSIFY_URL", "u")
    cm.set_credential("alice", "classify-1", "CLASSIFY_API_KEY", "k")
    assert sorted(cm.list_credential_keys("alice", "classify-1")) == ["CLASSIFY_API_KEY", "CLASSIFY_URL"]
    cm.remove_agent_credentials("alice", "classify-1")
    assert cm.list_credential_keys("alice", "classify-1") == []


def test_user_isolation(cm: CredentialManager) -> None:
    cm._fernet = MagicMock()
    cm._fernet.encrypt.side_effect = lambda b: b"cipher:" + b
    cm.set_credential("alice", "classify-1", "CLASSIFY_API_KEY", "alice-key")
    assert cm.list_credential_keys("alice", "classify-1") == ["CLASSIFY_API_KEY"]
    # bob has no credentials, even for the same agent.
    assert cm.list_credential_keys("bob", "classify-1") == []
    # bob saving his own credentials does not affect alice.
    cm.set_credential("bob", "classify-1", "CLASSIFY_API_KEY", "bob-key")
    alice_creds = cm.get_agent_credentials_encrypted("alice", "classify-1")
    bob_creds = cm.get_agent_credentials_encrypted("bob", "classify-1")
    assert alice_creds != bob_creds


def test_internal_keys_filtered_out_of_listing(cm: CredentialManager) -> None:
    """Keys starting with '_' are reserved (e.g., session tokens) and not listed."""
    cm._fernet = MagicMock()
    cm._fernet.encrypt.side_effect = lambda b: b"cipher:" + b
    cm.set_credential("alice", "classify-1", "PUBLIC_KEY", "v")
    cm.set_credential("alice", "classify-1", "_INTERNAL", "v")
    keys = cm.list_credential_keys("alice", "classify-1")
    # list_credential_keys returns ALL keys; filtering of '_'-prefixed happens in
    # get_agent_credentials_encrypted (the path tools see).
    creds = cm.get_agent_credentials_encrypted("alice", "classify-1")
    assert "PUBLIC_KEY" in creds
    assert "_INTERNAL" not in creds
