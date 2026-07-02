"""Feature 044 (FR-005/SC-004) — POST /api/auth/logout: native sign-out parity.

Covers: allowlist validation, revoked/queued outcomes with the originating
client_id, the public-client revocation payload (no secret for native client
ids), the retrier honoring the stored client_id, and the idempotent
auth_revocation_queue.client_id migration against the live Postgres.
"""
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator import web_auth
from orchestrator.auth import auth_router, get_current_user_payload


def _client(monkeypatch, payload=None):
    monkeypatch.setenv("KEYCLOAK_ALLOWED_AZP", "astral-desktop,astral-mobile")
    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_current_user_payload] = lambda: (
        payload or {"sub": "u-044", "preferred_username": "u-044"})
    return TestClient(app)


def test_logout_revokes_with_originating_client_id(monkeypatch):
    calls = {}

    async def fake_revoke(refresh_token, client_id=None):
        calls["args"] = (refresh_token, client_id)
        return True

    monkeypatch.setattr(web_auth, "_revoke_refresh_token", fake_revoke)
    c = _client(monkeypatch)
    r = c.post("/api/auth/logout",
               json={"refresh_token": "rt-1", "client_id": "astral-desktop"})
    assert r.status_code == 200
    assert r.json()["outcome"] == "revoked" and r.json()["revoked"] is True
    assert calls["args"] == ("rt-1", "astral-desktop")


def test_logout_queues_when_idp_unreachable(monkeypatch):
    async def fake_revoke(refresh_token, client_id=None):
        return False

    enq = {}

    class FakeStore:
        def enqueue_revocation(self, user_id, refresh_token, client_id=None):
            enq.update(user_id=user_id, refresh_token=refresh_token, client_id=client_id)

    monkeypatch.setattr(web_auth, "_revoke_refresh_token", fake_revoke)
    monkeypatch.setattr(web_auth, "_get_store", lambda: FakeStore())
    c = _client(monkeypatch)
    r = c.post("/api/auth/logout",
               json={"refresh_token": "rt-2", "client_id": "astral-mobile"})
    assert r.status_code == 200
    assert r.json()["outcome"] == "queued" and r.json()["queued"] is True
    assert enq == {"user_id": "u-044", "refresh_token": "rt-2", "client_id": "astral-mobile"}


@pytest.mark.parametrize("body", [
    {},                                                       # nothing
    {"refresh_token": "rt"},                                  # no client_id
    {"refresh_token": "rt", "client_id": "evil-client"},      # not allow-listed
    {"client_id": "astral-desktop"},                          # no refresh token
])
def test_logout_rejects_bad_bodies(monkeypatch, body):
    c = _client(monkeypatch)
    assert c.post("/api/auth/logout", json=body).status_code == 400


def test_logout_refuses_the_confidential_web_client(monkeypatch):
    """Security: the native endpoint must NOT accept the web client id — that
    would apply the server's confidential secret to a caller-supplied token
    (a revocation oracle). The web app uses the cookie-bound /auth/logout."""
    monkeypatch.setenv("VITE_KEYCLOAK_CLIENT_ID", "astral-frontend")

    called = {"revoke": False}

    async def fake_revoke(refresh_token, client_id=None):
        called["revoke"] = True
        return True

    monkeypatch.setattr(web_auth, "_revoke_refresh_token", fake_revoke)
    c = _client(monkeypatch)  # sets KEYCLOAK_ALLOWED_AZP=astral-desktop,astral-mobile
    r = c.post("/api/auth/logout",
               json={"refresh_token": "victim-web-rt", "client_id": "astral-frontend"})
    assert r.status_code == 400
    assert called["revoke"] is False  # never reached the secret-backed revoke


def test_revocation_post_omits_secret_for_native_public_clients(monkeypatch):
    """Keycloak public clients (astral-desktop/mobile) must not receive the web
    client's secret; the web client keeps sending it."""
    monkeypatch.setenv("VITE_KEYCLOAK_AUTHORITY", "https://kc.example/realms/Astral")
    monkeypatch.setenv("VITE_KEYCLOAK_CLIENT_ID", "astral-frontend")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "s3cr3t")

    posts = []

    class FakeResp:
        status_code = 200

    class FakeAsyncClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, data=None):
            posts.append((url, dict(data or {})))
            return FakeResp()

    monkeypatch.setattr(web_auth.httpx, "AsyncClient", FakeAsyncClient)
    loop = asyncio.new_event_loop()

    assert loop.run_until_complete(
        web_auth._revoke_refresh_token("rt", client_id="astral-desktop")) is True
    assert posts[-1][1]["client_id"] == "astral-desktop"
    assert "client_secret" not in posts[-1][1]

    assert loop.run_until_complete(web_auth._revoke_refresh_token("rt")) is True
    assert posts[-1][1]["client_id"] == "astral-frontend"
    assert posts[-1][1]["client_secret"] == "s3cr3t"


def test_retrier_uses_stored_client_id(monkeypatch):
    seen = []

    async def fake_revoke(refresh_token, client_id=None):
        seen.append((refresh_token, client_id))
        return True

    class FakeStore:
        def pending_revocations(self, limit=20):
            return [
                {"id": 1, "user_id": "u", "refresh_token": "rt-native",
                 "attempts": 0, "enqueued_at": 0, "client_id": "astral-mobile"},
                {"id": 2, "user_id": "u", "refresh_token": "rt-web",
                 "attempts": 0, "enqueued_at": 0, "client_id": None},
            ]

        def resolve_revocation(self, qid):
            pass

        def bump_revocation_attempt(self, qid):
            pass

    monkeypatch.setattr(web_auth, "_revoke_refresh_token", fake_revoke)
    monkeypatch.setattr(web_auth, "_get_store", lambda: FakeStore())
    resolved = asyncio.new_event_loop().run_until_complete(
        web_auth.process_revocation_queue_once())
    assert resolved == 2
    assert ("rt-native", "astral-mobile") in seen
    assert ("rt-web", None) in seen  # NULL → falls back to the web client id


def test_migration_added_client_id_column():
    """The idempotent _init_db delta must exist on the live schema."""
    from shared.database import Database
    db = Database()
    row = db.fetch_one(
        "SELECT column_name, is_nullable FROM information_schema.columns "
        "WHERE table_name = 'auth_revocation_queue' AND column_name = 'client_id'")
    assert row, "auth_revocation_queue.client_id missing — _init_db delta not applied"
    assert row["is_nullable"] == "YES"  # NULL-compatible with pre-044 rows


def test_client_local_manifest_untouched():
    """The endpoint is REST — the WS accept_actions manifest must not grow."""
    from pathlib import Path
    manifest = json.loads((Path(__file__).resolve().parents[1] / "shared" /
                           "ui_protocol.json").read_text(encoding="utf-8"))
    assert "native_logout" not in manifest["accept_actions"]
