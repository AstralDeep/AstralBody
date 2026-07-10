"""Feature 028 — /auth/callback and /auth/login route-level tests (FR-003/004/005).

Covers the OIDC callback's deep-link preservation on success and on every
error exit (IdP ``error`` param, missing/unknown state, token-exchange
failure), the FR-005 role gate at the callback (a token with neither the
'user' nor the 'admin' role gets a bounded 403, no session, its refresh
credential revoked-or-queued, and a ``login_interactive`` failure audit),
and the FR-004 identity-provider pre-flight in ``/auth/login`` (503 bounded
error page with a retry link when the IdP is unreachable; 60-second positive
probe cache on success).

Mirrors tests/test_logout_revocation.py: live Postgres via shared.database
defaults, uuid-keyed rows cleaned up in ``finally`` blocks, fake
``httpx.AsyncClient`` classes, and unsigned best-effort JWTs.
"""
import asyncio
import base64
import json
import secrets
import time
import uuid

import pytest
from cryptography.fernet import Fernet
from fastapi.responses import HTMLResponse

from orchestrator import web_auth
from orchestrator.session_store import WebSessionStore
from shared.database import Database

# The canonical deep link used across these tests and its URL-encoded form
# as it must appear inside ?next= (quote(DEEP_LINK, safe="")).
DEEP_LINK = "/?chat=abc"
DEEP_LINK_ENC = "%2F%3Fchat%3Dabc"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

class _FakeRequest:
    def __init__(self, cookies=None, query_params=None, base_url="http://localhost:8001/"):
        self.cookies = cookies or {}
        self.query_params = query_params or {}
        self.base_url = base_url


def _fake_jwt(payload: dict) -> str:
    """Unsigned base64url header.payload.sig JWT (web_auth decodes best-effort)."""
    def enc(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'none', 'typ': 'JWT'})}.{enc(payload)}.sig"


def _token_client(token_response: dict):
    """Fake httpx.AsyncClient class whose POST yields the given token JSON."""
    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return token_response

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, data=None):
            return _FakeResponse()

    return _FakeAsyncClient


def _capture_audit(monkeypatch):
    """Swap web_auth._audit for a recorder; returns the call list."""
    calls = []

    async def fake_audit(action, sub, description, *, outcome="success"):
        calls.append({"action": action, "sub": sub,
                      "description": description, "outcome": outcome})

    monkeypatch.setattr(web_auth, "_audit", fake_audit)
    return calls


def _seed_pending(nxt=DEEP_LINK):
    """Register a pending login (as /auth/login would) and return its state."""
    state = secrets.token_urlsafe(16)
    web_auth._PENDING[state] = {"code_verifier": "v" * 43,
                                "created_at": time.time(), "next": nxt}
    return state


@pytest.fixture(autouse=True)
def _reset_web_auth():
    """Fresh module state per test: cached store, IdP probe cache, reasons."""
    web_auth.reset_store_for_tests()
    yield
    web_auth.reset_store_for_tests()


@pytest.fixture(scope="module")
def db():
    return Database()


@pytest.fixture()
def store(db, monkeypatch):
    """A WebSessionStore with a real Fernet key, wired into web_auth."""
    monkeypatch.setenv("WEB_SESSION_ENC_KEY", Fernet.generate_key().decode())
    s = WebSessionStore(db=db)
    monkeypatch.setattr(web_auth, "_get_store", lambda: s)
    return s


@pytest.fixture()
def real_auth_env(monkeypatch):
    """Mock auth OFF + a Keycloak authority so OIDC URLs build."""
    monkeypatch.setenv("USE_MOCK_AUTH", "false")
    monkeypatch.setenv("KEYCLOAK_AUTHORITY", "http://keycloak.test/realms/astral")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "astral-frontend")
    monkeypatch.delenv("KEYCLOAK_CLIENT_SECRET", raising=False)


def _purge_queue(db, *user_ids):
    for uid in user_ids:
        db.execute("DELETE FROM auth_revocation_queue WHERE user_id = ?", (uid,))


def _session_rows(db, user_id):
    return db.fetch_all("SELECT * FROM web_session WHERE user_id = ?", (user_id,))


# ---------------------------------------------------------------------------
# /auth/callback — success path (FR-003: deep link honored)
# ---------------------------------------------------------------------------

def test_callback_success_redirects_to_deep_link(db, store, monkeypatch, real_auth_env):
    """028 FR-003: a successful callback 303s to the exact non-'/' next that
    was seeded at /auth/login time (deep links are never dropped)."""
    user_id = f"u-{uuid.uuid4()}"
    state = _seed_pending(DEEP_LINK)
    token_response = {
        "access_token": _fake_jwt({"sub": user_id, "exp": int(time.time()) + 300,
                                   "realm_access": {"roles": ["user"]}}),
        "refresh_token": f"rt-{uuid.uuid4()}",
    }
    monkeypatch.setattr(web_auth.httpx, "AsyncClient", _token_client(token_response))
    _capture_audit(monkeypatch)

    req = _FakeRequest(query_params={"code": "authcode-1", "state": state})
    new_sids = []
    try:
        resp = asyncio.run(web_auth.auth_callback(req))
        assert resp.status_code == 303
        assert resp.headers["location"] == DEEP_LINK
        assert web_auth.COOKIE_NAME in resp.headers.get("set-cookie", "")
        new_sids = [s for s, v in web_auth._SESSIONS.items() if v.get("sub") == user_id]
        assert len(new_sids) == 1
    finally:
        for s in new_sids:
            web_auth._SESSIONS.pop(s, None)
        store.delete_for_user(user_id)
        web_auth._PENDING.pop(state, None)


# ---------------------------------------------------------------------------
# /auth/callback — error exits preserve the deep link (FR-003/FR-004)
# ---------------------------------------------------------------------------

def test_callback_idp_error_preserves_encoded_deep_link(real_auth_env):
    """028 FR-003/FR-004: error=access_denied (user cancelled at the IdP, no
    code) yields the bounded error page whose retry link carries the
    URL-ENCODED deep link — next=%2F%3Fchat%3Dabc, not a bare next=%2F."""
    state = _seed_pending(DEEP_LINK)
    req = _FakeRequest(query_params={"state": state, "error": "access_denied"})
    resp = asyncio.run(web_auth.auth_callback(req))
    assert isinstance(resp, HTMLResponse)
    body = resp.body.decode("utf-8")
    assert f"/auth/login?next={DEEP_LINK_ENC}" in body
    assert 'next=%2F"' not in body                  # deep link NOT collapsed to '/'
    assert "access_denied" in body                  # reason surfaced to the user
    assert state not in web_auth._PENDING           # pending login consumed


def test_callback_missing_state_bounded_error():
    """028 FR-004: a callback with no state/code at all gets the bounded
    'invalid callback' page — retry to '/', no auto-redirect of any kind."""
    resp = asyncio.run(web_auth.auth_callback(_FakeRequest(query_params={})))
    assert isinstance(resp, HTMLResponse)
    assert resp.status_code == 200
    body = resp.body.decode("utf-8")
    assert "invalid callback" in body
    assert "/auth/login?next=%2F" in body
    assert "http-equiv" not in body.lower()
    assert "<script" not in body.lower()


def test_callback_unknown_state_bounded_error():
    """028 FR-004: a code with an unknown/forged state (no _PENDING entry)
    is refused with the same bounded error page."""
    bogus_state = f"forged-{uuid.uuid4()}"
    req = _FakeRequest(query_params={"code": "authcode-2", "state": bogus_state})
    resp = asyncio.run(web_auth.auth_callback(req))
    assert isinstance(resp, HTMLResponse)
    assert resp.status_code == 200
    body = resp.body.decode("utf-8")
    assert "invalid callback" in body
    assert "/auth/login?next=%2F" in body


def test_callback_token_exchange_failure_preserves_next(monkeypatch, real_auth_env):
    """028 FR-003/FR-004: when the code→token exchange blows up, the error
    page still offers a retry that preserves the encoded deep link."""
    state = _seed_pending(DEEP_LINK)

    class _BoomClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, data=None):
            raise RuntimeError("token endpoint unreachable")

    monkeypatch.setattr(web_auth.httpx, "AsyncClient", _BoomClient)
    req = _FakeRequest(query_params={"code": "authcode-3", "state": state})
    resp = asyncio.run(web_auth.auth_callback(req))
    assert isinstance(resp, HTMLResponse)
    body = resp.body.decode("utf-8")
    assert "rejected the sign-in" in body
    assert f"/auth/login?next={DEEP_LINK_ENC}" in body
    assert state not in web_auth._PENDING


# ---------------------------------------------------------------------------
# /auth/callback — FR-005 role gate
# ---------------------------------------------------------------------------

def test_callback_no_access_role_refused(db, store, monkeypatch, real_auth_env):
    """028 FR-005: a token with neither 'user' nor 'admin' gets the bounded
    403 no-access page; no session is established anywhere; the refresh
    credential is revoked-or-queued; the failure is audited."""
    user_id = f"u-{uuid.uuid4()}"
    refresh = f"rt-{uuid.uuid4()}"
    state = _seed_pending(DEEP_LINK)
    token_response = {
        "access_token": _fake_jwt({"sub": user_id, "exp": int(time.time()) + 300,
                                   "realm_access": {"roles": ["offline_access"]},
                                   "resource_access": {"acct": {"roles": ["view-profile"]}}}),
        "refresh_token": refresh,
    }
    monkeypatch.setattr(web_auth.httpx, "AsyncClient", _token_client(token_response))

    revoke_attempts = []

    async def revoked(token, client_id=None):
        revoke_attempts.append(token)
        return True

    monkeypatch.setattr(web_auth, "_revoke_refresh_token", revoked)
    audits = _capture_audit(monkeypatch)

    sessions_before = set(web_auth._SESSIONS)
    req = _FakeRequest(query_params={"code": "authcode-4", "state": state})
    try:
        resp = asyncio.run(web_auth.auth_callback(req))

        assert resp.status_code == 403
        body = resp.body.decode("utf-8")
        assert "No access" in body
        assert "set-cookie" not in {k.lower() for k in resp.headers.keys()}

        # No session anywhere: cache unchanged, no durable row.
        assert set(web_auth._SESSIONS) == sessions_before
        assert _session_rows(db, user_id) == []

        # Refresh credential revoke-or-queue was attempted with OUR token.
        assert revoke_attempts == [refresh]

        # login_interactive audited as a failure.
        assert any(a["action"] == "login_interactive" and a["outcome"] == "failure"
                   and a["sub"] == user_id for a in audits)
    finally:
        store.delete_for_user(user_id)
        _purge_queue(db, user_id)
        web_auth._PENDING.pop(state, None)


def test_callback_user_role_passes_gate(db, store, monkeypatch, real_auth_env):
    """028 FR-005 (positive): realm_access.roles=['user'] is enough — the
    callback establishes a session (cache + durable row) and 303s onward."""
    user_id = f"u-{uuid.uuid4()}"
    state = _seed_pending("/")
    token_response = {
        "access_token": _fake_jwt({"sub": user_id, "exp": int(time.time()) + 300,
                                   "realm_access": {"roles": ["user"]}}),
        "refresh_token": f"rt-{uuid.uuid4()}",
    }
    monkeypatch.setattr(web_auth.httpx, "AsyncClient", _token_client(token_response))
    audits = _capture_audit(monkeypatch)

    req = _FakeRequest(query_params={"code": "authcode-5", "state": state})
    new_sids = []
    try:
        resp = asyncio.run(web_auth.auth_callback(req))
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
        new_sids = [s for s, v in web_auth._SESSIONS.items() if v.get("sub") == user_id]
        assert len(new_sids) == 1
        assert len(_session_rows(db, user_id)) == 1
        assert any(a["action"] == "login_interactive" and a["outcome"] == "success"
                   for a in audits)
    finally:
        for s in new_sids:
            web_auth._SESSIONS.pop(s, None)
        store.delete_for_user(user_id)
        web_auth._PENDING.pop(state, None)


# ---------------------------------------------------------------------------
# /auth/login — FR-004 IdP pre-flight
# ---------------------------------------------------------------------------

def test_auth_login_idp_unreachable_returns_503_with_retry(monkeypatch, real_auth_env):
    """028 FR-004: an unreachable IdP yields the bounded 503 error page (not a
    raw redirect into a dead authorize URL) whose retry preserves next."""
    probes = []

    class _DownClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            probes.append(url)
            raise RuntimeError("connection refused")

    monkeypatch.setattr(web_auth.httpx, "AsyncClient", _DownClient)

    pending_before = set(web_auth._PENDING)
    req = _FakeRequest(query_params={"next": DEEP_LINK})
    resp = asyncio.run(web_auth.auth_login(req))

    assert isinstance(resp, HTMLResponse)
    assert resp.status_code == 503
    body = resp.body.decode("utf-8")
    assert "unreachable" in body
    assert f"/auth/login?next={DEEP_LINK_ENC}" in body      # retry keeps the deep link
    assert "http-equiv" not in body.lower()                  # bounded — no auto-retry
    assert "<script" not in body.lower()

    assert len(probes) == 1
    assert probes[0].endswith("/.well-known/openid-configuration")
    assert set(web_auth._PENDING) == pending_before          # no pending login minted


def test_auth_login_probe_success_cached_60s(monkeypatch, real_auth_env):
    """028 FR-004: a positive reachability probe is cached, so a second login
    within the 60s window goes straight to the authorize redirect without
    re-probing the IdP."""
    probe_count = {"n": 0}

    class _UpResponse:
        status_code = 200

    class _UpClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            probe_count["n"] += 1
            return _UpResponse()

    monkeypatch.setattr(web_auth.httpx, "AsyncClient", _UpClient)

    pending_before = set(web_auth._PENDING)
    try:
        resp1 = asyncio.run(web_auth.auth_login(_FakeRequest(query_params={"next": "/"})))
        resp2 = asyncio.run(web_auth.auth_login(_FakeRequest(query_params={"next": "/"})))

        assert probe_count["n"] == 1                          # second call hit the cache
        for resp in (resp1, resp2):
            assert resp.status_code in (302, 303, 307)
            location = resp.headers["location"]
            assert location.startswith(
                "http://keycloak.test/realms/astral/protocol/openid-connect/auth?")
            assert "code_challenge_method=S256" in location
        # Each login minted its own pending state.
        assert len(set(web_auth._PENDING) - pending_before) == 2
    finally:
        for s in set(web_auth._PENDING) - pending_before:
            web_auth._PENDING.pop(s, None)
