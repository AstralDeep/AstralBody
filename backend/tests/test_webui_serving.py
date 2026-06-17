"""Feature 026 — headless integration check of the web-UI serving layer.

The full interactive real-browser parity pass (T030) needs a live stack + browser
and runs separately. This test verifies, headlessly via FastAPI's TestClient, the
HTTP serving the orchestrator wires up: the shell route (with token injection) and
the StaticFiles mount that serve `client.js` / `astral.css` from `backend/webrender/static`.
It builds a minimal app mirroring the orchestrator's mount (orchestrator.py:5347+),
so it exercises the real shell template + static assets without booting the DB.
"""
import os

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

WEBRENDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webrender")
SHELL = os.path.join(WEBRENDER, "templates", "shell.html")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("VITE_USE_MOCK_AUTH", "true")  # so the shell gets 'dev-token'
    from orchestrator.web_auth import session_token

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    async def shell(request: Request):
        html = open(SHELL, encoding="utf-8").read()
        return HTMLResponse(html.replace("%%ASTRAL_TOKEN%%", session_token(request) or ""))

    app.mount("/static", StaticFiles(directory=os.path.join(WEBRENDER, "static")), name="static")
    return TestClient(app)


def test_shell_served_with_token(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    # The served UI is branded "AstralDeep" (shell <title>, favicon, topbar logo);
    # "AstralBody" is the product/repo name and never appears in the shell. This
    # assertion previously checked the stale product name and failed post-rebrand.
    assert "AstralDeep" in body
    assert "/static/client.js" in body and "/static/astral.css" in body
    assert '<link rel="icon" type="image/png" href="/static/img/astra-fav.png">' in body
    assert "%%ASTRAL_TOKEN%%" not in body          # placeholder replaced
    assert 'window.__ASTRAL_TOKEN__ = "dev-token"' in body  # mock token injected, JS var name intact


def test_brand_image_assets_served(client):
    for path in ("/static/img/AstralDeep.png", "/static/img/astra-fav.png"):
        resp = client.get(path)
        assert resp.status_code == 200, f"missing asset: {path}"
        assert resp.headers["content-type"] == "image/png"
        assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"  # real PNG payload


def test_client_js_served(client):
    resp = client.get("/static/client.js")
    assert resp.status_code == 200
    assert "register_ui" in resp.text and "ui_stream_data" in resp.text


def test_astral_css_served(client):
    resp = client.get("/static/astral.css")
    assert resp.status_code == 200
    assert "--astral-primary" in resp.text


def test_vendor_assets_present():
    # self-hosted (no external CDN at runtime)
    assert os.path.getsize(os.path.join(WEBRENDER, "static", "vendor", "tailwind.js")) > 10000
    assert os.path.getsize(os.path.join(WEBRENDER, "static", "vendor", "plotly.min.js")) > 100000
