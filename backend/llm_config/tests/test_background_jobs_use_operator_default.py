"""T064a — FR-011 regression test: background-job calls (websocket=None)
use the operator's `.env` default credentials, never user session creds.

The orchestrator's _call_llm accepts ``websocket=None`` for
server-initiated calls (e.g., the daily feedback quality / proposals
job from feature 004). The factory must NOT borrow another connected
user's session credentials for these calls; it must use the operator
default. The mechanism: the credential-resolution helper looks up
``id(websocket)``, and ``id(None)`` is a constant that never matches
any real socket's id() — the lookup misses, the factory falls through
to operator default.

This test demonstrates the invariant by:
  1. Setting up multiple users with personal credentials in a
     :class:`SessionCredentialStore`.
  2. Calling ``build_llm_client(store.get(id(None)), default_creds)``
     with ``websocket=None``.
  3. Asserting the result is ``CredentialSource.OPERATOR_DEFAULT`` and
     that none of the user-specific URLs / models leaks into the
     resolved config.
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_config.audit_events import record_llm_call
from llm_config.client_factory import build_llm_client
from llm_config.operator_creds import OperatorDefaultCreds
from llm_config.session_creds import SessionCredentialStore
from llm_config.types import CredentialSource


@pytest.fixture
def fake_recorder():
    rec = MagicMock()
    rec.record = AsyncMock()
    return rec


def _operator_default():
    return OperatorDefaultCreds(
        api_key="sk-operator1234567890abcdef",
        base_url="https://operator.example/v1",
        model="op-model",
    )


def test_websocket_none_resolves_to_operator_default_even_with_other_users_connected():
    """The principal FR-011 invariant. Multiple users have personal
    creds set; a background job calls with websocket=None; the factory
    MUST return CredentialSource.OPERATOR_DEFAULT and the operator's
    base_url / model — NOT either user's."""
    store = SessionCredentialStore()
    # Two users with personal creds, simulating a busy server
    user_a_ws = object()
    user_b_ws = object()
    store.set(id(user_a_ws), "sk-userA1234567890abcdef", "https://userA/v1", "userA-model")
    store.set(id(user_b_ws), "sk-userB1234567890abcdef", "https://userB/v1", "userB-model")

    # Background job: no websocket
    ws_id = id(None)
    session_creds = store.get(ws_id)
    # id(None) is a constant; never matches a real socket's id.
    assert session_creds is None

    _, source, resolved = build_llm_client(session_creds, _operator_default())
    assert source is CredentialSource.OPERATOR_DEFAULT
    # Crucially: we did not borrow user A's or user B's credentials.
    assert resolved.base_url == "https://operator.example/v1"
    assert resolved.model == "op-model"
    assert resolved.base_url != "https://userA/v1"
    assert resolved.base_url != "https://userB/v1"


@pytest.mark.asyncio
async def test_background_call_audits_with_credential_source_operator_default(fake_recorder):
    """When the orchestrator's _call_llm runs a background job, the
    resulting llm_call audit event records credential_source=operator_default.
    Operators querying the SC-006 invariant ('did any user with personal
    config silently use the operator default?') correctly count this as
    an operator-default call, not a user call."""
    store = SessionCredentialStore()
    # User A is connected with personal creds — the daily background
    # job's call should still tag as operator_default, NOT user.
    user_a_ws = object()
    store.set(id(user_a_ws), "sk-userA1234567890abcdef", "https://userA/v1", "userA-model")

    ws_id = id(None)
    session_creds = store.get(ws_id)
    _, source, resolved = build_llm_client(session_creds, _operator_default())

    # Emit the audit event the orchestrator would emit for a successful
    # background-job call. ``actor_user_id='system'`` per the convention
    # in audit-events.md for system-initiated events.
    await record_llm_call(
        fake_recorder,
        actor_user_id="system",
        auth_principal="system",
        feature="feedback_quality_job",
        credential_source=source,
        resolved=resolved,
        total_tokens=128,
        outcome="success",
    )
    ev = fake_recorder.record.await_args.args[0]
    assert ev.event_class == "llm_call"
    assert ev.actor_user_id == "system"
    assert ev.inputs_meta["credential_source"] == "operator_default"
    # The user's URL must NOT appear in the audit
    blob = ev.model_dump_json()
    assert "userA" not in blob
    assert "operator.example" in blob


def test_neither_session_nor_default_raises_llmunavailable_for_background_job():
    """If the operator hasn't set .env credentials AND no user is
    connected, the background job's call hits LLMUnavailable. Per
    FR-011 + the spec's edge case, the orchestrator's daily quality job
    treats this as 'skip this iteration, log and try again later' —
    not an error condition."""
    from llm_config.types import LLMUnavailable
    empty = OperatorDefaultCreds(api_key=None, base_url=None, model=None)
    with pytest.raises(LLMUnavailable):
        build_llm_client(None, empty)
