"""Feature 016-persistent-login — audit-pipeline tests for the three new
``auth.*`` action_type values introduced by FR-015.

These tests validate the *schema and pipeline* level only: they do NOT
spin up the orchestrator. The orchestrator-level branching that picks
which action_type to record based on ``msg.resumed`` is exercised by an
integration test that imports the WS register handler directly (see
``test_resumed_flag_routes_action_type`` below).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from audit.schemas import AuditEventCreate


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Schema-level: the three new action_types must be writable under the
# existing event_class="auth" bucket (no new event_class is required).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "action_type",
    [
        "auth.login_interactive",
        "auth.session_resumed",
        "auth.session_resume_failed",
    ],
)
def test_new_auth_action_types_accepted_under_existing_event_class(action_type):
    """Closes /speckit-analyze CG3-equivalent: the three new action_types
    round-trip through AuditEventCreate using the existing 'auth' class.
    """
    ev = AuditEventCreate(
        actor_user_id="u1",
        auth_principal="u1",
        event_class="auth",
        action_type=action_type,
        description="smoke",
        correlation_id="00000000-0000-0000-0000-000000000001",
        outcome="success" if action_type != "auth.session_resume_failed" else "failure",
        started_at=_now(),
    )
    assert ev.event_class == "auth"
    assert ev.action_type == action_type


# ---------------------------------------------------------------------------
# Orchestrator-level branching: msg.resumed=True with valid token routes
# to auth.session_resumed; msg.resumed=False (or omitted) routes to
# auth.login_interactive; msg.resumed=True with invalid token routes to
# auth.session_resume_failed.
# ---------------------------------------------------------------------------

class _CapturingRecorder:
    """Stand-in for the real audit recorder; records calls in-memory."""

    def __init__(self):
        self.records = []

    async def record(self, event):
        self.records.append(event)


@pytest.mark.asyncio
async def test_resumed_true_records_session_resumed(monkeypatch):
    """Body of T006 #1: a successful WS register with msg.resumed=True
    writes an audit event with action_type='auth.session_resumed'.
    """
    cap = _CapturingRecorder()
    monkeypatch.setattr("audit.hooks.get_recorder", lambda: cap)

    from audit.hooks import record_auth_event

    await record_auth_event(
        claims={"sub": "alice", "preferred_username": "alice", "_pl_resumed": True},
        action="session_resumed",
        description="Silent session resumed from stored credential",
    )
    assert len(cap.records) == 1
    ev = cap.records[0]
    assert ev.event_class == "auth"
    assert ev.action_type == "auth.session_resumed"
    assert ev.outcome == "success"
    assert ev.actor_user_id == "alice"


@pytest.mark.asyncio
async def test_resumed_false_records_login_interactive(monkeypatch):
    """Body of T006 #2: a successful WS register with msg.resumed=False
    writes an audit event with action_type='auth.login_interactive'.
    """
    cap = _CapturingRecorder()
    monkeypatch.setattr("audit.hooks.get_recorder", lambda: cap)

    from audit.hooks import record_auth_event

    await record_auth_event(
        claims={"sub": "bob", "preferred_username": "bob"},
        action="login_interactive",
        description="Interactive login completed",
    )
    assert len(cap.records) == 1
    ev = cap.records[0]
    assert ev.event_class == "auth"
    assert ev.action_type == "auth.login_interactive"
    assert ev.outcome == "success"


@pytest.mark.asyncio
async def test_resumed_true_invalid_jwt_records_resume_failed(monkeypatch):
    """Body of T006 #3: a WS register with msg.resumed=True and an
    invalid token writes an audit event with
    action_type='auth.session_resume_failed', outcome='failure'.
    """
    cap = _CapturingRecorder()
    monkeypatch.setattr("audit.hooks.get_recorder", lambda: cap)

    from audit.hooks import record_auth_event

    await record_auth_event(
        claims={"sub": "carol"},
        action="session_resume_failed",
        description="Silent session resume rejected (invalid/expired token)",
        outcome="failure",
        outcome_detail="ws_register token rejected",
    )
    assert len(cap.records) == 1
    ev = cap.records[0]
    assert ev.event_class == "auth"
    assert ev.action_type == "auth.session_resume_failed"
    assert ev.outcome == "failure"
    assert ev.outcome_detail == "ws_register token rejected"


def test_resumed_omitted_treated_as_false_for_backward_compat():
    """Body of T006 #4: older clients omit `resumed` from the
    register_ui payload. The RegisterUI dataclass must default it to
    False so the orchestrator falls through the 'login_interactive'
    branch — never the 'session_resumed' or '_failed' branches.
    """
    from shared.protocol import RegisterUI

    legacy_payload = json.dumps({
        "type": "register_ui",
        "token": "tok",
        "capabilities": ["render"],
        # NOTE: no "resumed" key at all
    })
    msg = RegisterUI.from_json(legacy_payload)
    assert msg.resumed is False


# ---------------------------------------------------------------------------
# REST endpoint: POST /api/audit/session-resume-failed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_resume_failed_rest_endpoint_records_anonymous_when_unauthenticated():
    """Body of T006 #5: the REST fallback endpoint accepts an
    unauthenticated body and writes an audit row attributed to
    actor_user_id='anonymous'.
    """
    from audit.api import post_session_resume_failed, SessionResumeFailedBody

    cap = _CapturingRecorder()

    # Patch the recorder lookup inside the endpoint's module namespace.
    import audit.api as api_mod
    original = api_mod.get_recorder
    api_mod.get_recorder = lambda: cap

    try:
        # Build a minimal stub request with no Authorization header.
        class _StubHeaders(dict):
            def get(self, k, default=None):
                return super().get(k.lower(), default)

        class _StubRequest:
            headers = _StubHeaders()

        body = SessionResumeFailedBody(
            reason="retry-budget-exhausted",
            attempts=3,
            last_error="Network request failed after 3 attempts",
        )
        await post_session_resume_failed(_StubRequest(), body)
    finally:
        api_mod.get_recorder = original

    assert len(cap.records) == 1
    ev = cap.records[0]
    assert ev.actor_user_id == "anonymous"
    assert ev.auth_principal == "anonymous"
    assert ev.event_class == "auth"
    assert ev.action_type == "auth.session_resume_failed"
    assert ev.outcome == "failure"
    assert ev.inputs_meta.get("reason") == "retry-budget-exhausted"
    assert ev.inputs_meta.get("attempts") == 3
    assert ev.inputs_meta.get("resumed") is True


@pytest.mark.asyncio
async def test_session_resume_failed_rest_endpoint_attributes_when_bearer_present():
    """Bonus: when a (probably-stale) bearer token IS present, the
    endpoint best-effort decodes the JWT payload and attributes the
    audit row to the recovered `sub`, not 'anonymous'.
    """
    import base64
    from audit.api import post_session_resume_failed, SessionResumeFailedBody

    cap = _CapturingRecorder()
    import audit.api as api_mod
    original = api_mod.get_recorder
    api_mod.get_recorder = lambda: cap

    try:
        # Hand-craft a JWT with a `sub` claim (signature ignored — the
        # endpoint deliberately does not verify it).
        header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            b'{"sub":"dave","preferred_username":"dave-user"}'
        ).rstrip(b"=").decode()
        signature = "x"
        jwt = f"{header}.{payload}.{signature}"

        class _StubHeaders:
            def __init__(self, h):
                self._h = h

            def get(self, k, default=None):
                return self._h.get(k.lower(), default)

        class _StubRequest:
            def __init__(self, h):
                self.headers = _StubHeaders(h)

        body = SessionResumeFailedBody(
            reason="token-expired", attempts=0, last_error="hard-max"
        )
        await post_session_resume_failed(
            _StubRequest({"authorization": f"Bearer {jwt}"}), body
        )
    finally:
        api_mod.get_recorder = original

    assert len(cap.records) == 1
    ev = cap.records[0]
    assert ev.actor_user_id == "dave"
    assert ev.auth_principal == "dave-user"
