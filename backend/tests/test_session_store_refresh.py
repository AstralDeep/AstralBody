"""Feature 028 — durable web-session store + silent refresh (FR-006..FR-009, D2/D3).

Exercises ``orchestrator.session_store.WebSessionStore`` against the live
Postgres (Fernet encryption at rest, anchor immutability, restart survival,
the 365-day hard cap, dev/prod keyless posture, the offline revocation queue)
and ``orchestrator.web_auth._refresh_session`` with a monkeypatched
``httpx.AsyncClient`` (token rotation, refused-refresh session kill, offline
tolerance). All rows use uuid4-unique ids so parallel runs never collide.
"""
import asyncio
import time
import uuid

import httpx
import pytest
from cryptography.fernet import Fernet

from orchestrator import web_auth
from orchestrator.session_store import SessionStoreError, WebSessionStore
from shared.database import Database


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db():
    """One Database per module (its __init__ replays the idempotent migrations)."""
    return Database()


@pytest.fixture
def fernet_key(monkeypatch):
    """Set WEB_SESSION_ENC_KEY BEFORE any store is constructed."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("WEB_SESSION_ENC_KEY", key)
    return key


@pytest.fixture
def keyed_store(db, fernet_key):
    return WebSessionStore(db=db)


@pytest.fixture
def auth_env(monkeypatch, db, fernet_key):
    """Clean web_auth state: fresh store, empty session cache, quiet audit,
    fake Keycloak config. Yields the injected WebSessionStore."""
    monkeypatch.setenv("VITE_USE_MOCK_AUTH", "false")
    web_auth.reset_store_for_tests()
    store = WebSessionStore(db=db)
    web_auth._STORE = store
    web_auth._SESSIONS.clear()

    async def _noop_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(web_auth, "_audit", _noop_audit)
    monkeypatch.setattr(
        web_auth, "_keycloak_config",
        lambda: ("http://idp.test/realms/astral", "astral-frontend", "csecret"),
    )
    yield store
    web_auth._SESSIONS.clear()
    web_auth.reset_store_for_tests()


def _ids():
    return f"sid-{uuid.uuid4()}", f"user-{uuid.uuid4()}"


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("POST", "http://idp.test/token")
            raise httpx.HTTPStatusError(
                f"{self.status_code}", request=req,
                response=httpx.Response(self.status_code, request=req),
            )

    def json(self):
        return self._payload


def _fake_async_client(post_result=None, post_exc=None):
    """Factory for an httpx.AsyncClient stand-in (async context manager)."""

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, data=None, **kwargs):
            if post_exc is not None:
                raise post_exc
            return post_result

    return _Client


def _seed_session(store, *, sid, user_id, access="at-old", refresh="rt-old",
                  hard_max=3600):
    store.create(sid, user_id=user_id, access_token=access,
                 refresh_token=refresh, hard_max_seconds=hard_max)


# ---------------------------------------------------------------------------
# WebSessionStore CRUD (FR-006/FR-007/FR-008, D3)
# ---------------------------------------------------------------------------

def test_create_get_roundtrip_encrypted_at_rest(keyed_store):
    """028 FR-006/FR-008 (D3): create -> get returns the decrypted tokens while
    the Postgres row holds only Fernet ciphertext."""
    sid, user_id = _ids()
    _seed_session(keyed_store, sid=sid, user_id=user_id,
                  access="at-secret", refresh="rt-secret")
    try:
        sess = keyed_store.get(sid)
        assert sess is not None
        assert sess["user_id"] == user_id
        assert sess["access_token"] == "at-secret"
        assert sess["refresh_token"] == "rt-secret"

        raw = keyed_store.db.fetch_one("SELECT * FROM web_session WHERE sid = ?", (sid,))
        assert raw is not None
        assert raw["access_token_enc"] != "at-secret"
        assert raw["refresh_token_enc"] != "rt-secret"
        # Fernet tokens are versioned urlsafe-base64 blobs starting with gAAAA.
        assert raw["access_token_enc"].startswith("gAAAA")
    finally:
        keyed_store.delete(sid)


def test_update_tokens_rotates_but_never_moves_anchor(keyed_store):
    """028 FR-007: update_tokens rotates both tokens and bumps last_refresh_at
    but NEVER changes interactive_anchor (016 FR-001 anchor immutability)."""
    sid, user_id = _ids()
    _seed_session(keyed_store, sid=sid, user_id=user_id)
    try:
        # Push the anchor visibly into the past so an accidental re-anchor
        # (anchor := now) would be detected even within the same second.
        old_anchor = int(time.time()) - 12345
        keyed_store.db.execute(
            "UPDATE web_session SET interactive_anchor = ? WHERE sid = ?",
            (old_anchor, sid),
        )

        keyed_store.update_tokens(sid, access_token="at-new", refresh_token="rt-new")

        raw = keyed_store.db.fetch_one("SELECT * FROM web_session WHERE sid = ?", (sid,))
        assert int(raw["interactive_anchor"]) == old_anchor   # anchor untouched
        assert int(raw["last_refresh_at"]) >= old_anchor + 12345

        # Cached view rotated too.
        sess = keyed_store.get(sid)
        assert sess["access_token"] == "at-new"
        assert sess["refresh_token"] == "rt-new"
    finally:
        keyed_store.delete(sid)


def test_delete_returns_row_and_removes_it(keyed_store):
    """028 FR-012 support: delete returns the (decrypted) row so the caller can
    revoke the refresh token, and the Postgres row is gone afterwards."""
    sid, user_id = _ids()
    _seed_session(keyed_store, sid=sid, user_id=user_id, refresh="rt-revoke-me")

    row = keyed_store.delete(sid)
    assert row is not None
    assert row["refresh_token"] == "rt-revoke-me"
    assert keyed_store.get(sid) is None
    assert keyed_store.db.fetch_one("SELECT 1 FROM web_session WHERE sid = ?", (sid,)) is None

    # Deleting an unknown sid is a no-op returning None.
    assert keyed_store.delete(f"sid-{uuid.uuid4()}") is None


def test_delete_for_user_wipes_all_sessions(keyed_store):
    """028 FR-014 (016 FR-008 user-switch revocation): delete_for_user removes
    every session of that user and reports the count."""
    user_id = f"user-{uuid.uuid4()}"
    sids = [f"sid-{uuid.uuid4()}" for _ in range(2)]
    for sid in sids:
        _seed_session(keyed_store, sid=sid, user_id=user_id)
    other_sid, other_user = _ids()
    _seed_session(keyed_store, sid=other_sid, user_id=other_user)
    try:
        assert keyed_store.delete_for_user(user_id) == 2
        for sid in sids:
            assert keyed_store.get(sid) is None
        # Unrelated user untouched.
        assert keyed_store.get(other_sid) is not None
    finally:
        keyed_store.delete(other_sid)


def test_restart_survival_fresh_store_instance(db, fernet_key):
    """028 FR-008: a session created by one store instance is readable by a NEW
    WebSessionStore (empty cache) — i.e. it survives a backend restart."""
    sid, user_id = _ids()
    store_a = WebSessionStore(db=db)
    _seed_session(store_a, sid=sid, user_id=user_id,
                  access="at-durable", refresh="rt-durable")
    try:
        store_b = WebSessionStore(db=db)   # fresh cache, same key env
        assert store_b._cache == {}
        sess = store_b.get(sid)
        assert sess is not None
        assert sess["user_id"] == user_id
        assert sess["access_token"] == "at-durable"
        assert sess["refresh_token"] == "rt-durable"
    finally:
        store_a.delete(sid)


def test_hard_cap_expired_session_is_deleted(db, keyed_store):
    """028 FR-006 (016 365-day cap, D2): a session at/past hard_expires_at is
    rejected by get() and deleted — on both the cache and DB read paths."""
    # Cache path: hard_max_seconds=0 expires immediately.
    sid, user_id = _ids()
    _seed_session(keyed_store, sid=sid, user_id=user_id, hard_max=0)
    assert keyed_store.get(sid) is None
    assert keyed_store.db.fetch_one("SELECT 1 FROM web_session WHERE sid = ?", (sid,)) is None

    # DB path: row with hard_expires_at in the past, read by a fresh store.
    sid2, user2 = _ids()
    _seed_session(keyed_store, sid=sid2, user_id=user2, hard_max=3600)
    keyed_store.db.execute(
        "UPDATE web_session SET hard_expires_at = ? WHERE sid = ?",
        (int(time.time()) - 60, sid2),
    )
    fresh = WebSessionStore(db=db)
    assert fresh.get(sid2) is None
    assert fresh.db.fetch_one("SELECT 1 FROM web_session WHERE sid = ?", (sid2,)) is None
    keyed_store._cache.pop(sid2, None)  # stale cache entry from the seeding store


def test_dev_mode_keyless_plaintext_roundtrip(monkeypatch, db):
    """028 FR-016 dev carve-out: with ASTRAL_ENV=development and no encryption
    keys the store constructs (plaintext at rest) and round-trips tokens."""
    monkeypatch.setenv("ASTRAL_ENV", "development")
    monkeypatch.delenv("WEB_SESSION_ENC_KEY", raising=False)
    monkeypatch.delenv("OFFLINE_GRANT_ENC_KEY", raising=False)

    store = WebSessionStore(db=db)
    assert store._fernet is None
    sid, user_id = _ids()
    _seed_session(store, sid=sid, user_id=user_id, access="at-plain", refresh="rt-plain")
    try:
        sess = store.get(sid)
        assert sess["access_token"] == "at-plain"
        raw = store.db.fetch_one("SELECT * FROM web_session WHERE sid = ?", (sid,))
        assert raw["access_token_enc"] == "at-plain"   # dev mode: stored as-is
    finally:
        store.delete(sid)


def test_production_keyless_fails_closed(monkeypatch, db):
    """028 FR-015/FR-016: outside explicit development mode the store refuses
    to construct without an encryption key (no plaintext tokens at rest)."""
    monkeypatch.delenv("ASTRAL_ENV", raising=False)
    monkeypatch.delenv("WEB_SESSION_ENC_KEY", raising=False)
    monkeypatch.delenv("OFFLINE_GRANT_ENC_KEY", raising=False)
    with pytest.raises(SessionStoreError):
        WebSessionStore(db=db)


def test_revocation_queue_lifecycle(keyed_store):
    """028 FR-013 (D5): enqueue_revocation persists the encrypted token;
    pending_revocations decrypts it; bump_revocation_attempt increments;
    resolve_revocation removes the entry. Empty tokens are never enqueued."""
    user_id = f"user-{uuid.uuid4()}"
    keyed_store.enqueue_revocation(user_id, "rt-queued")
    keyed_store.enqueue_revocation(user_id, "")   # no-op

    def _mine():
        return [r for r in keyed_store.pending_revocations(limit=500)
                if r["user_id"] == user_id]

    mine = _mine()
    assert len(mine) == 1
    item = mine[0]
    assert item["refresh_token"] == "rt-queued"
    assert item["attempts"] == 0
    raw = keyed_store.db.fetch_one(
        "SELECT refresh_token_enc FROM auth_revocation_queue WHERE id = ?", (item["id"],))
    assert raw["refresh_token_enc"] != "rt-queued"   # encrypted at rest

    keyed_store.bump_revocation_attempt(item["id"])
    assert _mine()[0]["attempts"] == 1

    keyed_store.resolve_revocation(item["id"])
    assert _mine() == []


# ---------------------------------------------------------------------------
# web_auth: store-backed resume + silent refresh (FR-006..FR-009, D2)
# ---------------------------------------------------------------------------

def test_session_by_sid_resumes_from_durable_store(auth_env):
    """028 FR-008: after the in-process cache is lost (restart), the session is
    rebuilt from the web_session row and flagged resumed=True."""
    store = auth_env
    sid, user_id = _ids()
    _seed_session(store, sid=sid, user_id=user_id, access="at-1", refresh="rt-1")
    store._cache.clear()           # simulate a fresh process
    try:
        assert sid not in web_auth._SESSIONS
        sess = web_auth._session_by_sid(sid)
        assert sess is not None
        assert sess["sub"] == user_id
        assert sess["access_token"] == "at-1"
        assert sess["resumed"] is True
        assert web_auth._SESSIONS[sid] is sess   # mirrored into the hot cache
    finally:
        web_auth._SESSIONS.pop(sid, None)
        store.delete(sid)


def test_refresh_session_success_rotates_tokens(auth_env, monkeypatch, db):
    """028 FR-006/FR-007 (D2): a 200 from the IdP rotates access+refresh tokens
    in the session dict AND the durable row, without moving the anchor."""
    store = auth_env
    sid, user_id = _ids()
    _seed_session(store, sid=sid, user_id=user_id, access="at-old", refresh="rt-old")
    anchor_before = int(store.db.fetch_one(
        "SELECT interactive_anchor FROM web_session WHERE sid = ?", (sid,))["interactive_anchor"])
    sess = web_auth._session_by_sid(sid)
    monkeypatch.setattr(
        web_auth.httpx, "AsyncClient",
        _fake_async_client(post_result=_FakeResponse(
            200, {"access_token": "at-new", "refresh_token": "rt-new"})),
    )
    try:
        out = asyncio.run(web_auth._refresh_session(sid, sess))
        assert out is sess
        assert sess["access_token"] == "at-new"
        assert sess["refresh_token"] == "rt-new"

        # Durable row rotated too; anchor untouched (FR-007).
        fresh = WebSessionStore(db=db)
        row = fresh.get(sid)
        assert row["access_token"] == "at-new"
        assert row["refresh_token"] == "rt-new"
        assert row["interactive_anchor"] == anchor_before
    finally:
        web_auth._SESSIONS.pop(sid, None)
        store.delete(sid)


def test_refresh_refused_kills_session(auth_env, monkeypatch):
    """028 FR-006 (D2): an HTTP-error refusal from the IdP (revoked/expired
    refresh token) kills the session — gone from _SESSIONS and the store."""
    store = auth_env
    sid, user_id = _ids()
    _seed_session(store, sid=sid, user_id=user_id)
    sess = web_auth._session_by_sid(sid)
    monkeypatch.setattr(
        web_auth.httpx, "AsyncClient",
        _fake_async_client(post_result=_FakeResponse(400, {"error": "invalid_grant"})),
    )
    out = asyncio.run(web_auth._refresh_session(sid, sess))
    assert out is None
    assert sid not in web_auth._SESSIONS
    assert store.get(sid) is None
    assert store.db.fetch_one("SELECT 1 FROM web_session WHERE sid = ?", (sid,)) is None


def test_refresh_network_error_keeps_session(auth_env, monkeypatch):
    """028 FR-009 (D2 offline tolerance): an unreachable IdP does NOT kill the
    session — the current tokens survive for the caller to try."""
    store = auth_env
    sid, user_id = _ids()
    _seed_session(store, sid=sid, user_id=user_id, access="at-keep", refresh="rt-keep")
    sess = web_auth._session_by_sid(sid)
    monkeypatch.setattr(
        web_auth.httpx, "AsyncClient",
        _fake_async_client(post_exc=httpx.ConnectError("idp unreachable")),
    )
    try:
        out = asyncio.run(web_auth._refresh_session(sid, sess))
        assert out is sess
        assert sess["access_token"] == "at-keep"
        assert sess["refresh_token"] == "rt-keep"
        assert sid in web_auth._SESSIONS
        assert store.db.fetch_one("SELECT 1 FROM web_session WHERE sid = ?", (sid,)) is not None
    finally:
        web_auth._SESSIONS.pop(sid, None)
        store.delete(sid)
