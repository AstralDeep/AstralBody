"""T014 — SessionCreds / SessionCredentialStore unit tests."""
from __future__ import annotations

import pytest

from llm_config.session_creds import SessionCreds, SessionCredentialStore


class TestSessionCredsRepr:
    """The custom __repr__ MUST elide the api_key."""

    def test_repr_omits_api_key(self):
        creds = SessionCreds(
            api_key="sk-super-secret-key-abc123",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            set_at=0.0,
        )
        assert "sk-super-secret-key-abc123" not in repr(creds)
        assert "<redacted>" in repr(creds)
        assert "gpt-4o-mini" in repr(creds)
        assert "api.openai.com" in repr(creds)

    def test_str_also_omits_api_key(self):
        creds = SessionCreds(
            api_key="sk-leaky", base_url="x", model="y", set_at=0.0
        )
        assert "sk-leaky" not in str(creds)


class TestSessionCredentialStore:
    def test_get_missing_returns_none(self):
        store = SessionCredentialStore()
        assert store.get(123) is None

    def test_set_then_get_round_trip(self):
        store = SessionCredentialStore()
        creds = store.set(123, "sk-x", "https://example.com/v1", "model-a")
        assert store.get(123) is creds
        assert creds.api_key == "sk-x"
        assert creds.base_url == "https://example.com/v1"
        assert creds.model == "model-a"

    def test_set_strips_trailing_slash_on_base_url(self):
        store = SessionCredentialStore()
        creds = store.set(1, "k", "https://example.com/v1/", "m")
        assert creds.base_url == "https://example.com/v1"

    def test_set_rejects_empty_api_key(self):
        store = SessionCredentialStore()
        with pytest.raises(ValueError, match="api_key"):
            store.set(1, "", "u", "m")
        with pytest.raises(ValueError, match="api_key"):
            store.set(1, "   ", "u", "m")

    def test_set_rejects_empty_base_url(self):
        store = SessionCredentialStore()
        with pytest.raises(ValueError, match="base_url"):
            store.set(1, "k", "", "m")

    def test_set_rejects_empty_model(self):
        store = SessionCredentialStore()
        with pytest.raises(ValueError, match="model"):
            store.set(1, "k", "u", "")

    def test_set_replaces_prior_entry(self):
        store = SessionCredentialStore()
        store.set(1, "k1", "u1", "m1")
        store.set(1, "k2", "u2", "m2")
        creds = store.get(1)
        assert creds.api_key == "k2"

    def test_clear_returns_true_when_existed(self):
        store = SessionCredentialStore()
        store.set(1, "k", "u", "m")
        assert store.clear(1) is True
        assert store.get(1) is None

    def test_clear_returns_false_when_absent(self):
        store = SessionCredentialStore()
        assert store.clear(1) is False

    def test_contains_and_len(self):
        store = SessionCredentialStore()
        assert 1 not in store
        assert len(store) == 0
        store.set(1, "k", "u", "m")
        store.set(2, "k", "u", "m")
        assert 1 in store and 2 in store
        assert len(store) == 2
        store.clear(1)
        assert 1 not in store
        assert len(store) == 1
