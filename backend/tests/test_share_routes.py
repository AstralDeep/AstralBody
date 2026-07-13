"""Feature 055 (US5, T044) — share REST routes.

``POST/GET /api/share``, ``DELETE /api/share/{id}`` and the PUBLIC
``GET /share/{token}`` behind ``FF_ARTIFACT_SHARING`` (default OFF,
fail-closed):

* flag off ⇒ every route 404s with FastAPI's route-absent body;
* mint returns ``{id, share_url, created_at, expires_at}`` exactly once —
  no separate token field, no token material in the owner listing;
* the public serve needs NO auth, returns the mint-time snapshot verbatim
  with the contract's noindex / no-store / no-referrer / CSP headers;
* revoke is owner-scoped, idempotent, and immediate (the next public open
  refuses with the uniform 404);
* the PHI gate refusal maps to 403 ``{error: "phi_blocked"}``.

Routes run over a real FastAPI app + TestClient against the REAL
``ShareGrantStore`` and live Postgres ``share_grant`` table (the store's
methods keep all DB work off the event loop, so LOOP_GUARD_ENFORCE=1 holds);
the orchestrator is mocked only as the snapshot source. Each test user is
uuid-unique and purges its own grant rows on teardown.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ["USE_MOCK_AUTH"] = "true"

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from orchestrator.api import share_router  # noqa: E402
from orchestrator.artifact_share import (  # noqa: E402
    ShareGrantStore,
    set_share_store,
)
from personalization.phi_gate import PHIGate, set_phi_gate  # noqa: E402
from shared.database import Database  # noqa: E402
from shared.feature_flags import flags  # noqa: E402


def _can_connect_to_db() -> bool:
    try:
        import psycopg2
        from shared.database import _build_database_url
        conn = psycopg2.connect(_build_database_url())
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _can_connect_to_db(),
    reason="Postgres unavailable in this environment",
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _CleanAnalyzer:
    def analyze(self, text, language, entities, score_threshold):
        return []


class _HitAnalyzer:
    def analyze(self, text, language, entities, score_threshold):
        return [{"entity_type": "PERSON"}]


CHAT_ID = "chat-share-routes"
COMPONENT = {
    "type": "card", "component_id": "wc_shared", "title": "Quarterly revenue",
    "content": "Up and to the right", "provenance": "grounded",
}


def _make_mock_token(payload: dict) -> str:
    import base64
    import json as _json
    body = base64.b64encode(_json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{body}.signature"


def _auth(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_make_mock_token({'sub': user_id})}"}


@pytest.fixture(scope="module")
def db():
    return Database()


@pytest.fixture()
def user(db):
    uid = f"pytest-shareroutes-{uuid.uuid4().hex[:12]}"
    yield uid
    db.execute("DELETE FROM share_grant WHERE user_id = ?", (uid,))


@pytest.fixture(autouse=True)
def real_store(db):
    set_share_store(ShareGrantStore(db))
    yield
    set_share_store(None)


@pytest.fixture(autouse=True)
def clean_phi_gate():
    set_phi_gate(PHIGate(analyzer=_CleanAnalyzer(), build_if_missing=False))
    yield
    set_phi_gate(None)


@pytest.fixture()
def sharing_on():
    prior = flags._flags.get("artifact_sharing")
    flags._flags["artifact_sharing"] = True
    yield
    flags._flags["artifact_sharing"] = prior


@pytest.fixture()
def orch():
    m = MagicMock()
    m.workspace = MagicMock()
    m.workspace.aget_by_component_id = AsyncMock(
        return_value={"chat_id": CHAT_ID, "component_id": "wc_shared",
                      "component_data": dict(COMPONENT)})
    m._canvas_components = MagicMock(return_value=[dict(COMPONENT)])
    return m


@pytest.fixture()
def client(orch):
    app = FastAPI()
    app.include_router(share_router)
    app.state.orchestrator = orch
    return TestClient(app)


def _mint(client, user_id, scope="component", **over):
    body = {"chat_id": CHAT_ID, "scope": scope}
    if scope == "component":
        body["component_id"] = "wc_shared"
    body.update(over)
    return client.post("/api/share", json=body, headers=_auth(user_id))


def _grant_rows(db, user_id):
    return db.fetch_all(
        "SELECT * FROM share_grant WHERE user_id = ? ORDER BY id ASC", (user_id,))


# ---------------------------------------------------------------------------
# Flag off — fail-closed 404 everywhere
# ---------------------------------------------------------------------------


def test_flag_off_all_routes_404(db, client, user):
    prior = flags._flags.get("artifact_sharing")
    flags._flags["artifact_sharing"] = False
    try:
        absent = {"detail": "Not Found"}
        r = _mint(client, user)
        assert (r.status_code, r.json()) == (404, absent)
        r = client.get("/api/share", headers=_auth(user))
        assert (r.status_code, r.json()) == (404, absent)
        r = client.delete("/api/share/1", headers=_auth(user))
        assert (r.status_code, r.json()) == (404, absent)
        r = client.get("/share/any-token-at-all")
        assert (r.status_code, r.json()) == (404, absent)
        assert _grant_rows(db, user) == []
    finally:
        flags._flags["artifact_sharing"] = prior


# ---------------------------------------------------------------------------
# Mint + public serve
# ---------------------------------------------------------------------------


def test_mint_returns_url_once_and_serves_unauthenticated(db, client, user, sharing_on):
    r = _mint(client, user)
    assert r.status_code == 201
    body = r.json()
    # The raw token appears exactly once, inside share_url — no token field.
    assert set(body) == {"id", "share_url", "created_at", "expires_at"}
    assert body["share_url"].startswith("/share/")

    # PUBLIC serve: no Authorization header at all.
    pub = client.get(body["share_url"])
    assert pub.status_code == 200
    assert pub.headers["content-type"].startswith("text/html")
    assert pub.text.startswith("<!DOCTYPE html>")
    assert "Quarterly revenue" in pub.text
    assert "<script" not in pub.text
    # Contract headers (rest-endpoints.md §GET /share/{token}).
    assert pub.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert pub.headers["Cache-Control"] == "no-store"
    assert pub.headers["Referrer-Policy"] == "no-referrer"
    assert pub.headers["Content-Security-Policy"] == \
        "default-src 'none'; style-src 'unsafe-inline'; img-src data:"

    row = _grant_rows(db, user)[0]
    assert row["open_count"] == 1
    assert row["scope"] == "component" and row["component_id"] == "wc_shared"


def test_serve_is_the_mint_time_snapshot_not_live(db, client, orch, user, sharing_on):
    r = _mint(client, user)
    # The workspace changes after mint — the link must keep serving the snapshot.
    orch.workspace.aget_by_component_id.return_value = None
    pub = client.get(r.json()["share_url"])
    assert pub.status_code == 200
    assert "Quarterly revenue" in pub.text


def test_canvas_scope_mint_and_serve(db, client, user, sharing_on):
    r = _mint(client, user, scope="canvas", component_id=None)
    assert r.status_code == 201
    pub = client.get(r.json()["share_url"])
    assert pub.status_code == 200
    assert "Quarterly revenue" in pub.text
    assert _grant_rows(db, user)[0]["scope"] == "canvas"


def test_unknown_token_uniform_404(client, user, sharing_on):
    r = client.get("/share/definitely-not-a-token")
    assert (r.status_code, r.json()) == (404, {"detail": "Not Found"})


# ---------------------------------------------------------------------------
# Revoke — immediate, owner-scoped, idempotent
# ---------------------------------------------------------------------------


def test_revoke_immediately_stops_public_serving(client, user, sharing_on):
    minted = _mint(client, user).json()
    assert client.get(minted["share_url"]).status_code == 200

    r = client.delete(f"/api/share/{minted['id']}", headers=_auth(user))
    assert r.status_code == 200
    # The very next public open refuses with the uniform body.
    pub = client.get(minted["share_url"])
    assert (pub.status_code, pub.json()) == (404, {"detail": "Not Found"})

    # Idempotent second revoke; unknown id → 404.
    assert client.delete(f"/api/share/{minted['id']}", headers=_auth(user)).status_code == 200
    assert client.delete("/api/share/999999999", headers=_auth(user)).status_code == 404


def test_stranger_cannot_revoke(db, client, user, sharing_on):
    minted = _mint(client, user).json()
    stranger = f"pytest-shareroutes-{uuid.uuid4().hex[:12]}"
    r = client.delete(f"/api/share/{minted['id']}", headers=_auth(stranger))
    assert r.status_code == 404
    assert client.get(minted["share_url"]).status_code == 200


# ---------------------------------------------------------------------------
# Owner listing
# ---------------------------------------------------------------------------


def test_list_owner_metadata_never_token_material(client, user, sharing_on):
    a = _mint(client, user).json()
    b = _mint(client, user, scope="canvas", component_id=None).json()

    r = client.get("/api/share", headers=_auth(user))
    assert r.status_code == 200
    shares = r.json()["shares"]
    assert [s["id"] for s in shares] == sorted([a["id"], b["id"]], reverse=True)
    for s in shares:
        assert "token_sha256" not in s
        assert "snapshot_html" not in s and "snapshot_json" not in s
    # Neither raw token ever appears in the listing payload.
    for minted in (a, b):
        assert minted["share_url"].split("/share/")[1] not in r.text


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_phi_refusal_is_403_phi_blocked(db, client, user, sharing_on):
    set_phi_gate(PHIGate(analyzer=_HitAnalyzer(), build_if_missing=False))
    r = _mint(client, user)
    assert r.status_code == 403
    assert r.json() == {"error": "phi_blocked"}
    assert _grant_rows(db, user) == []


def test_invalid_scope_and_missing_component_id_are_422(client, user, sharing_on):
    r = _mint(client, user, scope="everything")
    assert r.status_code == 422 and r.json()["error"] == "invalid_scope"
    r = _mint(client, user, component_id=None)
    assert r.status_code == 422 and r.json()["error"] == "invalid_request"


def test_component_not_found_is_404(client, orch, user, sharing_on):
    orch.workspace.aget_by_component_id.return_value = None
    assert _mint(client, user).status_code == 404


def test_empty_canvas_is_404(client, orch, user, sharing_on):
    orch._canvas_components.return_value = []
    assert _mint(client, user, scope="canvas", component_id=None).status_code == 404


def test_api_routes_require_auth(client, user, sharing_on):
    assert client.post("/api/share", json={"chat_id": CHAT_ID, "scope": "canvas"}).status_code == 401
    assert client.get("/api/share").status_code == 401
    assert client.delete("/api/share/1").status_code == 401
