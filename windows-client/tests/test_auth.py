"""Desktop OIDC helpers — PKCE encoding, silent refresh, and the auth-resolution
policy (explicit token wins; no authority ⇒ dev-token)."""
from __future__ import annotations

import hashlib
import io
import json
import types

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
                     token_endpoint="http://kc/token", client_id="astral-desktop")
    assert s.refresh() == "NEW"
    assert s.access_token == "NEW" and s.refresh_token == "R2"


def test_session_refresh_without_token_is_none():
    s = auth.Session(access_token="OLD", refresh_token=None,
                     token_endpoint="http://kc/token", client_id="astral-desktop")
    assert s.refresh() is None


def test_resolve_auth_explicit_token_wins():
    from astral_client.app import resolve_auth
    args = types.SimpleNamespace(token="dev-token", authority="", client_id="astral-desktop")
    assert resolve_auth(args) == ("dev-token", None)


def test_resolve_auth_defaults_to_devtoken_without_authority():
    from astral_client.app import resolve_auth
    args = types.SimpleNamespace(token="", authority="", client_id="astral-desktop")
    assert resolve_auth(args) == ("dev-token", None)
