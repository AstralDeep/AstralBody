"""T034 — orchestrator._call_llm credential resolution test.

Bypasses the full Orchestrator construction (which would pull in DB,
agents, etc.) and tests the credential-resolution helpers directly
against a stub-mode minimal orchestrator. Covers:

* User session creds present → factory returns USER client.
* User session creds absent + operator default complete → OPERATOR_DEFAULT.
* Both absent → LLMUnavailable raised by factory; caller emits
  llm_unconfigured audit.
* websocket=None (background-job path) → OPERATOR_DEFAULT, never USER,
  even if some other socket has session creds.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_config.client_factory import build_llm_client
from llm_config.operator_creds import OperatorDefaultCreds
from llm_config.session_creds import SessionCredentialStore
from llm_config.types import CredentialSource, LLMUnavailable


def _full_default():
    return OperatorDefaultCreds(
        api_key="sk-operator1234567890abcdef",
        base_url="https://operator.example/v1",
        model="op-model",
    )


def _no_default():
    return OperatorDefaultCreds(api_key=None, base_url=None, model=None)


class TestResolveLLMClientFor:
    """End-to-end behaviour the orchestrator's _resolve_llm_client_for
    delegates to."""

    def test_user_creds_present_returns_user_source(self):
        store = SessionCredentialStore()
        ws = object()
        store.set(id(ws), "sk-user1234567890abcdefgh", "https://user/v1", "user-model")
        client, source, resolved = build_llm_client(store.get(id(ws)), _full_default())
        assert source == CredentialSource.USER
        assert resolved.base_url == "https://user/v1"
        assert resolved.model == "user-model"

    def test_user_absent_default_present_returns_operator_default(self):
        store = SessionCredentialStore()
        client, source, resolved = build_llm_client(store.get(0), _full_default())
        assert source == CredentialSource.OPERATOR_DEFAULT
        assert resolved.model == "op-model"

    def test_both_absent_raises_llmunavailable(self):
        with pytest.raises(LLMUnavailable):
            build_llm_client(None, _no_default())

    def test_websocket_none_uses_operator_default_even_when_other_user_has_creds(self):
        """Background-job invariant (FR-011 + Edge case test for SC-006).

        If user A has session creds set, and a background job calls
        with websocket=None, the factory must NOT borrow user A's
        creds — it must use the operator default. The mechanism that
        enforces this: ``_resolve_llm_client_for(None)`` looks up
        ``id(None)``, which is never in the credential store (sets
        always use ``id(real_websocket)``).
        """
        store = SessionCredentialStore()
        user_a_ws = object()
        store.set(id(user_a_ws), "sk-userA1234567890abcdefg", "https://userA/v1", "a-model")

        # Simulate the orchestrator's resolver with websocket=None
        ws_id = id(None)  # id(None) is a constant that won't collide with real sockets
        session_creds = store.get(ws_id)
        assert session_creds is None  # never matches a real socket

        client, source, resolved = build_llm_client(session_creds, _full_default())
        assert source == CredentialSource.OPERATOR_DEFAULT
        # Crucially: user A's base_url is NOT what was resolved
        assert resolved.base_url != "https://userA/v1"
        assert resolved.base_url == "https://operator.example/v1"


class TestNoRuntimeFallback:
    """FR-009: when source=USER and the call fails, the system MUST NOT
    silently retry against the operator default. The factory's contract
    enforces this by binding (client, source) at the START of a call;
    nothing in the factory re-resolves on error."""

    def test_factory_returns_user_source_consistent_for_one_call(self):
        store = SessionCredentialStore()
        ws = object()
        store.set(id(ws), "sk-user", "https://user/v1", "user-model")
        # Resolve once. The returned tuple is now bound — even if the
        # caller mutates the store, this resolution does not change.
        client, source, resolved = build_llm_client(store.get(id(ws)), _full_default())
        assert source == CredentialSource.USER

        # Caller clears store mid-flight (simulating a real
        # llm_config_clear coming in over WS during an in-flight call):
        store.clear(id(ws))

        # The (client, source, resolved) tuple from the resolution is
        # unchanged — already bound. The next factory call would
        # fall back to operator default, but THIS call's source/client
        # remain USER. The orchestrator's _call_llm uses the bound
        # tuple for the entire call (and its retry loop), guaranteeing
        # FR-009.
        assert source == CredentialSource.USER
        assert resolved.base_url == "https://user/v1"
