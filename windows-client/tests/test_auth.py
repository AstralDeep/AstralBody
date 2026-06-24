"""Desktop OIDC helpers — PKCE encoding, silent refresh, and the auth-resolution
policy (explicit token wins; no authority ⇒ dev-token)."""
from __future__ import annotations

import hashlib
import io
import json
import types

import pytest

from astral_client import auth


def test_b64u_is_url_safe_and_unpadded():
    out = auth._b64u(b"\x00\x01\x02\xff\xfe")
    assert "=" not in out and "+" not in out and "/" not in out


def test_pkce_challenge_derivation():
    verifier = auth._b64u(b"x" * 32)
    challenge = auth._b64u(hashlib.sha256(verifier.encode("ascii")).digest())
    assert challenge and "=" not in challenge


def test_session_refresh(monkeypatch):
    def fake_urlopen(req, timeout=None):
        return io.BytesIO(json.dumps({"access_token": "NEW", "refresh_token": "R2"}).encode())
    monkeypatch.setattr(auth, "urlopen", fake_urlopen)
    s = auth.Session(access_token="OLD", refresh_token="R1",
                     token_url="http://127.0.0.1:8001/auth/token", client_id="astral-frontend")
    assert s.refresh() == "NEW"
    assert s.access_token == "NEW" and s.refresh_token == "R2"


def test_session_refresh_without_token_is_none():
    s = auth.Session(access_token="OLD", refresh_token=None,
                     token_url="http://127.0.0.1:8001/auth/token", client_id="astral-frontend")
    assert s.refresh() is None


def test_resolve_auth_explicit_token_wins():
    pytest.importorskip("PySide6")  # astral_client.app imports Qt
    from astral_client.app import resolve_auth
    args = types.SimpleNamespace(token="dev-token", authority="", client_id="astral-desktop")
    assert resolve_auth(args) == ("dev-token", None)


def test_resolve_auth_defaults_to_devtoken_without_authority():
    pytest.importorskip("PySide6")  # astral_client.app imports Qt
    from astral_client.app import resolve_auth
    args = types.SimpleNamespace(token="", authority="", client_id="astral-desktop")
    assert resolve_auth(args) == ("dev-token", None)


# --- oidc_login token-exchange mode selection -------------------------------- #

_DISCO = {
    "authorization_endpoint": "https://kc.example/realms/R/protocol/openid-connect/auth",
    "token_endpoint": "https://kc.example/realms/R/protocol/openid-connect/token",
}


def _run_oidc_login(monkeypatch, **kwargs):
    """Drive oidc_login end-to-end with the network + browser mocked: the fake
    browser fires the loopback callback so the real PKCE/loopback machinery runs,
    and _post_form is captured instead of hitting a token endpoint."""
    import threading
    from urllib.parse import parse_qs, urlparse
    from urllib.request import urlopen as real_urlopen

    monkeypatch.setattr(auth, "urlopen",
                        lambda *a, **k: io.BytesIO(json.dumps(_DISCO).encode()))
    captured = {}

    def fake_post_form(url, fields, timeout=20):
        captured["url"] = url
        captured["fields"] = fields
        return {"access_token": "AT", "refresh_token": "RT"}

    monkeypatch.setattr(auth, "_post_form", fake_post_form)

    def fake_browser_open(url):
        q = parse_qs(urlparse(url).query)
        redirect_uri, state = q["redirect_uri"][0], q["state"][0]
        threading.Thread(
            target=lambda: real_urlopen(f"{redirect_uri}?code=FAKE&state={state}", timeout=5).read(),
            daemon=True,
        ).start()

    monkeypatch.setattr(auth.webbrowser, "open", fake_browser_open)
    session = auth.oidc_login("https://kc.example/realms/R", **kwargs)
    return session, captured


def test_oidc_login_direct_uses_keycloak_token_endpoint(monkeypatch):
    session, captured = _run_oidc_login(monkeypatch, client_id="astral-desktop")
    assert session.token_url == _DISCO["token_endpoint"]
    assert captured["url"] == _DISCO["token_endpoint"]
    assert session.client_id == "astral-desktop"
    assert session.access_token == "AT" and session.refresh_token == "RT"
    # Public client: no secret is ever sent by the desktop.
    assert "client_secret" not in captured["fields"]
    assert captured["fields"]["code_verifier"]  # PKCE proof present


def test_oidc_login_bff_mode_uses_proxy(monkeypatch):
    session, captured = _run_oidc_login(
        monkeypatch, client_id="astral-frontend", bff_base="http://127.0.0.1:8001")
    assert session.token_url == "http://127.0.0.1:8001/auth/token"
    assert captured["url"] == "http://127.0.0.1:8001/auth/token"
    assert session.client_id == "astral-frontend"
