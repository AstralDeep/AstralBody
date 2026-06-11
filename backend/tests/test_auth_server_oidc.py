"""Feature 026 — T019: server-side OIDC session helpers (FR-009).

Exercises the headlessly-testable parts of the server-side auth flow: signed
session cookies (tamper-evident), PKCE generation, the mock-auth dev token, the
365-day persistent-login hard cap, and session lookup. The full Keycloak code
exchange requires a live realm and is covered by the real-browser parity pass.
"""
import time


from orchestrator import web_auth


class _FakeRequest:
    def __init__(self, cookies=None, base_url="http://localhost:8001/"):
        self.cookies = cookies or {}
        self.base_url = base_url


def test_cookie_sign_unsign_roundtrip_and_tamper():
    signed = web_auth._sign("session-abc")
    assert web_auth._unsign(signed) == "session-abc"
    assert web_auth._unsign(signed + "x") is None        # tampered mac
    assert web_auth._unsign("nodot") is None
    assert web_auth._unsign("sid.deadbeef") is None        # forged mac


def test_pkce_pair_is_valid():
    verifier, challenge = web_auth._pkce_pair()
    assert len(verifier) >= 43 and len(challenge) >= 43    # RFC 7636 length floor
    assert verifier != challenge


def test_hard_cap_is_365_days():
    assert web_auth.HARD_MAX_SECONDS == 365 * 24 * 60 * 60


def test_mock_mode_returns_dev_token(monkeypatch):
    monkeypatch.setenv("VITE_USE_MOCK_AUTH", "true")
    assert web_auth.session_token(_FakeRequest()) == "dev-token"


def test_session_lookup_and_365_day_cap(monkeypatch):
    monkeypatch.setenv("VITE_USE_MOCK_AUTH", "false")
    # establish a session manually
    sid = "sess-1"
    web_auth._SESSIONS[sid] = {"access_token": "tok-123", "refresh_token": "r", "sub": "u1", "created_at": time.time()}
    cookie = web_auth._sign(sid)
    req = _FakeRequest(cookies={web_auth.COOKIE_NAME: cookie})
    sess = web_auth.get_session(req)
    assert sess and sess["access_token"] == "tok-123"
    assert web_auth.session_token(req) == "tok-123"

    # age the session past the 365-day cap -> cleared
    web_auth._SESSIONS[sid]["created_at"] = time.time() - web_auth.HARD_MAX_SECONDS - 10
    assert web_auth.get_session(req) is None
    assert sid not in web_auth._SESSIONS  # cleaned up
    web_auth._SESSIONS.pop(sid, None)


def test_no_cookie_no_session(monkeypatch):
    monkeypatch.setenv("VITE_USE_MOCK_AUTH", "false")
    assert web_auth.get_session(_FakeRequest()) is None
    assert web_auth.session_token(_FakeRequest()) == ""


def test_sub_from_jwt_best_effort():
    # unsigned best-effort decode (validation happens via JWKS at register_ui)
    import base64
    import json
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "user-9"}).encode()).rstrip(b"=").decode()
    fake_jwt = "h." + payload + ".sig"
    assert web_auth._sub_from_jwt(fake_jwt) == "user-9"
    assert web_auth._sub_from_jwt("garbage") == "anonymous"
