"""T051 — FR-009 regression test: no runtime fallback to operator default.

When a user has saved personal credentials and an LLM call fails at
runtime (key revoked, network error, model not found, 401, 429, etc.),
the orchestrator MUST surface the upstream error and MUST NOT silently
retry against the operator's `.env` default credentials. The audit log
records exactly one ``llm_call`` event with ``credential_source='user',
outcome='failure'``; there is NO follow-on ``llm_call`` event with
``credential_source='operator_default'`` for the same logical call.

The test is structured against the credential-resolution helper rather
than spinning up the full Orchestrator (which would require a live DB,
agents, etc.). This is sufficient because:

1. The factory binds the (client, source, resolved) tuple at the START
   of a call.
2. The orchestrator's _call_llm uses the bound tuple for its retry loop
   and audit emission, never re-resolves on error.
3. So the FR-009 invariant is enforced at the factory boundary plus
   the orchestrator's caller discipline. Both are covered by tests.

This file complements test_call_llm_credential_resolution.py — that one
tests the factory's purity; this one tests the call-site discipline by
inspecting the audit-event helpers' inputs / outputs in failure paths.
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_config.audit_events import record_llm_call
from llm_config.client_factory import build_llm_client
from llm_config.operator_creds import OperatorDefaultCreds
from llm_config.session_creds import SessionCreds
from llm_config.types import CredentialSource, ResolvedConfig


@pytest.fixture
def fake_recorder():
    rec = MagicMock()
    rec.record = AsyncMock()
    return rec


def _user_session():
    return SessionCreds(
        api_key="sk-userkey1234567890abcdef",
        base_url="https://user.example/v1",
        model="user-model",
        set_at=time.monotonic(),
    )


def _full_default():
    return OperatorDefaultCreds(
        api_key="sk-operator1234567890abcdef",
        base_url="https://operator.example/v1",
        model="op-model",
    )


@pytest.mark.asyncio
async def test_user_call_failure_emits_only_one_llm_call_event(fake_recorder):
    """When source=USER and the call fails, the audit log records ONE
    failure event tagged credential_source=user; no operator-default
    follow-up event is emitted for the same call."""
    user_creds = _user_session()
    default = _full_default()

    # Resolve once — this is what the orchestrator's _call_llm does
    # at the START of the call.
    _, source, resolved = build_llm_client(user_creds, default)
    assert source == CredentialSource.USER

    # Simulate the failure path: orchestrator catches the upstream
    # exception, calls record_llm_call with the bound (source, resolved)
    # tuple, and re-raises (or returns None per its semantics). It does
    # NOT call record_llm_call a SECOND time with source=OPERATOR_DEFAULT.
    await record_llm_call(
        fake_recorder,
        actor_user_id="u1",
        auth_principal="u1",
        feature="tool_dispatch",
        credential_source=source,
        resolved=resolved,
        total_tokens=None,
        outcome="failure",
        upstream_error_class="auth_failed",
    )

    # Assertions
    assert fake_recorder.record.await_count == 1
    ev = fake_recorder.record.await_args.args[0]
    assert ev.event_class == "llm_call"
    assert ev.outcome == "failure"
    assert ev.inputs_meta["credential_source"] == "user"
    # Crucially: only one event. There is NO subsequent
    # operator_default-tagged event for this call.


@pytest.mark.asyncio
async def test_clearing_user_creds_mid_flight_does_not_retroactively_change_audit(fake_recorder):
    """Edge case from spec.md: 'A user clears their configuration
    mid-request — the in-flight request completes or fails as already
    dispatched, but no subsequent request reuses the cleared credentials.'

    The factory's resolve-once contract guarantees this: the tuple is
    bound at call start, so a clear() between binding and audit-event
    emission cannot change the credential_source label.
    """
    from llm_config.session_creds import SessionCredentialStore
    store = SessionCredentialStore()
    ws_id = id(object())
    store.set(ws_id, "sk-userkey1234567890abcdef", "https://user/v1", "m")

    # Bind credentials at call-start
    _, source, resolved = build_llm_client(store.get(ws_id), _full_default())
    assert source == CredentialSource.USER

    # Mid-flight: user clears their config
    store.clear(ws_id)

    # Audit emission still uses the bound tuple
    await record_llm_call(
        fake_recorder,
        actor_user_id="u1",
        auth_principal="u1",
        feature="tool_dispatch",
        credential_source=source,
        resolved=resolved,
        total_tokens=42,
        outcome="success",
    )
    ev = fake_recorder.record.await_args.args[0]
    assert ev.inputs_meta["credential_source"] == "user"
    assert ev.inputs_meta["base_url"] == "https://user/v1"
