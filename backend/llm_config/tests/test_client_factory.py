"""T015 — build_llm_client factory unit tests.

Covers all five branches of the resolution decision tree:
1. user-only      → returns USER client
2. default-only   → returns OPERATOR_DEFAULT client
3. both-present   → user wins
4. neither       → raises LLMUnavailable
5. partial-default with user present → user still wins (irrelevant default)
"""
from __future__ import annotations

import time

import pytest

from llm_config.client_factory import build_llm_client
from llm_config.operator_creds import OperatorDefaultCreds
from llm_config.session_creds import SessionCreds
from llm_config.types import CredentialSource, LLMUnavailable


def _user_creds() -> SessionCreds:
    return SessionCreds(
        api_key="sk-user",
        base_url="https://user.example/v1",
        model="user-model",
        set_at=time.monotonic(),
    )


def _full_default() -> OperatorDefaultCreds:
    return OperatorDefaultCreds(
        api_key="sk-operator",
        base_url="https://operator.example/v1",
        model="operator-model",
    )


def _empty_default() -> OperatorDefaultCreds:
    return OperatorDefaultCreds(api_key=None, base_url=None, model=None)


def _partial_default() -> OperatorDefaultCreds:
    """Real-world: api_key set, base_url missing (deployment misconfiguration)."""
    return OperatorDefaultCreds(api_key="sk-op", base_url=None, model="m")


class TestFactoryBranches:
    def test_user_creds_present_default_absent(self):
        client, source, resolved = build_llm_client(_user_creds(), _empty_default())
        assert source is CredentialSource.USER
        assert resolved.base_url == "https://user.example/v1"
        assert resolved.model == "user-model"
        assert client is not None

    def test_user_absent_default_complete(self):
        client, source, resolved = build_llm_client(None, _full_default())
        assert source is CredentialSource.OPERATOR_DEFAULT
        assert resolved.base_url == "https://operator.example/v1"
        assert resolved.model == "operator-model"

    def test_both_present_user_wins(self):
        _, source, resolved = build_llm_client(_user_creds(), _full_default())
        assert source is CredentialSource.USER
        assert resolved.base_url == "https://user.example/v1"

    def test_neither_present_raises(self):
        with pytest.raises(LLMUnavailable):
            build_llm_client(None, _empty_default())

    def test_user_present_default_partial_user_still_wins(self):
        _, source, _ = build_llm_client(_user_creds(), _partial_default())
        assert source is CredentialSource.USER

    def test_user_absent_default_partial_raises(self):
        with pytest.raises(LLMUnavailable):
            build_llm_client(None, _partial_default())


class TestFactoryDoesNotCacheClients:
    """FR-012: clearing user creds takes effect on next call.
    The factory MUST NOT cache the OpenAI client across calls; each
    invocation rebuilds from the passed credentials.
    """

    def test_two_calls_with_different_user_creds_yield_different_clients(self):
        c1, _, _ = build_llm_client(_user_creds(), _empty_default())
        other = SessionCreds(
            api_key="sk-other",
            base_url="https://other.example/v1",
            model="other-model",
            set_at=time.monotonic(),
        )
        c2, _, _ = build_llm_client(other, _empty_default())
        # Different OpenAI() instances each time.
        assert c1 is not c2

    def test_user_then_default_yields_different_clients(self):
        c1, _, _ = build_llm_client(_user_creds(), _full_default())
        c2, _, _ = build_llm_client(None, _full_default())
        assert c1 is not c2


class TestTimeoutPassthrough:
    def test_timeout_kwarg_is_threaded_through(self):
        # OpenAI client accepts timeout — we verify it doesn't raise
        # when we pass a value. Behavioural assertion (no exception);
        # full HTTP-level verification is outside the scope of a unit test.
        client, _, _ = build_llm_client(_user_creds(), _empty_default(), timeout=5.0)
        assert client is not None
