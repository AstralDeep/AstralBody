"""Feature 054 — per-user credential isolation (spec FR-007, US3-AS5).

The persisted store keys strictly on the caller's own ``user_id``; there
is no lookup path that can hand user B a record belonging to user A, and
user rows never serve the system context (or vice versa).
"""
from __future__ import annotations

from llm_config.client_factory import build_llm_client
from llm_config.types import CredentialSource, LLMUnavailable

import pytest


ALICE_KEY = "sk-userA-1234567890abcdef"
BOB_KEY = "sk-userB-1234567890abcdef"


def _seed_alice(store):
    store.set_sync("alice", provider="custom",
                   base_url="https://userA.example/v1",
                   model="userA-model", api_key=ALICE_KEY)


def test_two_users_rows_are_independent(store, fake_db):
    _seed_alice(store)
    store.set_sync("bob", provider="custom",
                   base_url="https://userB.example/v1",
                   model="userB-model", api_key=BOB_KEY)
    assert len(fake_db.users) == 2
    a = store.get_sync("alice")
    b = store.get_sync("bob")
    assert a.api_key == ALICE_KEY and a.base_url == "https://userA.example/v1"
    assert b.api_key == BOB_KEY and b.base_url == "https://userB.example/v1"
    # Clearing one leaves the other untouched.
    assert store.clear_sync("alice") is True
    assert store.get_sync("alice") is None
    assert store.get_sync("bob").api_key == BOB_KEY


def test_user_b_lookup_never_returns_user_a_record(store):
    _seed_alice(store)
    # Bob has no record: the lookup misses — it can never fall through to
    # Alice's row.
    assert store.get_sync("bob") is None
    # And the resulting factory call is the gate, not a borrowed client.
    with pytest.raises(LLMUnavailable):
        build_llm_client(store.get_sync("bob"), CredentialSource.USER)


def test_unknown_user_returns_none(store):
    assert store.get_sync("never-seen-user") is None


def test_user_rows_do_not_serve_the_system_context(store):
    """FR-007: system/background work must not use any user's personal
    credentials — a configured user does not make get_system() non-empty."""
    _seed_alice(store)
    assert store.get_system_sync() is None
    with pytest.raises(LLMUnavailable):
        build_llm_client(store.get_system_sync(), CredentialSource.SYSTEM)


def test_system_row_does_not_serve_user_lookups(store):
    """The system credential is never used for user-context calls
    (US4-AS4): an unconfigured user stays gated even when the admin
    record exists."""
    store.set_system_sync(provider="openai",
                          base_url="https://api.openai.com/v1",
                          model="gpt-4o", api_key="sk-system-1234567890abcd",
                          updated_by="admin")
    assert store.get_sync("alice") is None
    with pytest.raises(LLMUnavailable):
        build_llm_client(store.get_sync("alice"), CredentialSource.USER)


def test_resolved_config_for_a_matches_a_never_b(store):
    _seed_alice(store)
    store.set_sync("bob", provider="custom",
                   base_url="https://userB.example/v1",
                   model="userB-model", api_key=BOB_KEY)
    client, source, resolved = build_llm_client(
        store.get_sync("bob"), CredentialSource.USER)
    assert source is CredentialSource.USER
    assert resolved.base_url == "https://userB.example/v1"
    assert resolved.base_url != "https://userA.example/v1"
    assert client.api_key == BOB_KEY
