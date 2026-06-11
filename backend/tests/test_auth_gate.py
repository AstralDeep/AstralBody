"""Feature 028 (workspace-auth-revival) — auth gate unit tests.

Covers the headlessly-testable Part-A surfaces: the open-redirect guard
``_validate_next`` (research D1), the ``shell_gate`` redirect decision for
``GET /`` (FR-001/FR-003), the bounded ``/auth/error`` page (FR-004), and
mock-mode role derivation (FR-005). Style mirrors
tests/test_auth_server_oidc.py — sessions are seeded into the in-memory
``web_auth._SESSIONS`` cache so no IdP round-trip or Postgres row is needed.
"""
import time
import uuid
from urllib.parse import quote

from orchestrator import web_auth


class _FakeURL:
    def __init__(self, path="/", query=""):
        self.path = path
        self.query = query


class _FakeRequest:
    """Minimal request stand-in: shell_gate reads .url.path / .url.query and
    .cookies; session helpers read only .cookies."""

    def __init__(self, cookies=None, path="/", query="", base_url="http://localhost:8001/"):
        self.cookies = cookies or {}
        self.url = _FakeURL(path, query)
        self.base_url = base_url


# ---------------------------------------------------------------------------
# _validate_next — open-redirect guard (research D1, supports FR-003)
# ---------------------------------------------------------------------------

def test_validate_next_allows_root():
    """028 FR-003 / research D1: '/' is a valid same-origin destination."""
    assert web_auth._validate_next("/") == "/"


def test_validate_next_allows_relative_path_with_query():
    """028 FR-003 / research D1: relative path + query survives intact
    (deep links must never be silently dropped)."""
    assert web_auth._validate_next("/x?y=1") == "/x?y=1"


def test_validate_next_rejects_protocol_relative_url():
    """028 research D1: '//evil.com' (protocol-relative) falls back to '/'."""
    assert web_auth._validate_next("//evil.com") == "/"


def test_validate_next_rejects_absolute_url():
    """028 research D1: absolute external URLs fall back to '/'."""
    assert web_auth._validate_next("https://evil.com") == "/"


def test_validate_next_rejects_javascript_scheme():
    """028 research D1: javascript: pseudo-scheme falls back to '/'."""
    assert web_auth._validate_next("javascript:alert(1)") == "/"


def test_validate_next_rejects_backslash_forms():
    """028 research D1: backslash variants (browser path normalization
    tricks) all fall back to '/'."""
    assert web_auth._validate_next("/\\evil.com") == "/"
    assert web_auth._validate_next("\\/evil.com") == "/"
    assert web_auth._validate_next("\\\\evil.com") == "/"
    assert web_auth._validate_next("/\\/evil.com") == "/"


def test_validate_next_rejects_colon_in_path():
    """028 research D1: a colon in the path segment (scheme smuggling like
    '/https://evil.com' style) falls back to '/'; colons after '?' are fine."""
    assert web_auth._validate_next("/https://evil.com") == "/"
    assert web_auth._validate_next("/chat?at=10:30") == "/chat?at=10:30"


def test_validate_next_empty_falls_back_to_root():
    """028 research D1: empty / None / whitespace next falls back to '/'."""
    assert web_auth._validate_next("") == "/"
    assert web_auth._validate_next(None) == "/"
    assert web_auth._validate_next("   ") == "/"


# ---------------------------------------------------------------------------
# shell_gate — GET / redirect decision (FR-001..FR-003)
# ---------------------------------------------------------------------------

def test_shell_gate_mock_mode_never_gates(monkeypatch):
    """028 FR-001 (dev posture): mock auth mode serves the shell ungated."""
    monkeypatch.setenv("VITE_USE_MOCK_AUTH", "true")
    assert web_auth.shell_gate(_FakeRequest()) is None


def test_shell_gate_unauthenticated_redirects_preserving_deep_link(monkeypatch):
    """028 FR-001 + FR-003: real mode with no session cookie redirects to
    /auth/login with the original path+query (chat deep link) URL-encoded in
    ?next= so the destination is never dropped."""
    monkeypatch.setenv("VITE_USE_MOCK_AUTH", "false")
    chat_id = str(uuid.uuid4())
    req = _FakeRequest(path="/", query=f"chat={chat_id}")
    target = web_auth.shell_gate(req)
    assert target == "/auth/login?next=" + quote(f"/?chat={chat_id}", safe="")
    assert target.startswith("/auth/login?next=%2F")
    # The deep-link query must be encoded inside next, not a bare second param.
    assert f"chat={chat_id}" not in target.split("next=", 1)[0]


def test_shell_gate_unauthenticated_plain_root(monkeypatch):
    """028 FR-001: no cookie + no query gates to /auth/login?next=%2F."""
    monkeypatch.setenv("VITE_USE_MOCK_AUTH", "false")
    assert web_auth.shell_gate(_FakeRequest(path="/")) == "/auth/login?next=%2F"


def test_shell_gate_valid_session_passes(monkeypatch):
    """028 FR-001: a live signed-cookie session is let through (returns None)."""
    monkeypatch.setenv("VITE_USE_MOCK_AUTH", "false")
    sid = f"sess-{uuid.uuid4()}"
    web_auth._SESSIONS[sid] = {
        "access_token": "tok-abc",
        "refresh_token": "r",
        "sub": f"user-{uuid.uuid4()}",
        "created_at": time.time(),
    }
    try:
        req = _FakeRequest(cookies={web_auth.COOKIE_NAME: web_auth._sign(sid)},
                           path="/", query="chat=123")
        assert web_auth.shell_gate(req) is None
    finally:
        web_auth._SESSIONS.pop(sid, None)


def test_shell_gate_tampered_cookie_gates(monkeypatch):
    """028 FR-001: a forged/tampered cookie does not pass the gate."""
    monkeypatch.setenv("VITE_USE_MOCK_AUTH", "false")
    sid = f"sess-{uuid.uuid4()}"
    web_auth._SESSIONS[sid] = {
        "access_token": "tok-abc", "refresh_token": "r",
        "sub": f"user-{uuid.uuid4()}", "created_at": time.time(),
    }
    try:
        req = _FakeRequest(cookies={web_auth.COOKIE_NAME: web_auth._sign(sid) + "x"})
        assert web_auth.shell_gate(req) == "/auth/login?next=%2F"
    finally:
        web_auth._SESSIONS.pop(sid, None)


# ---------------------------------------------------------------------------
# /auth/error page (FR-004)
# ---------------------------------------------------------------------------

def test_error_page_bounded_with_retry_and_no_auto_redirect():
    """028 FR-004: the sign-in error page shows the (HTML-escaped) reason,
    offers a /auth/login?next= retry link, and never auto-redirects — no
    meta refresh and no script — so redirect loops are impossible."""
    reason = 'IdP said <no> & "denied"'
    resp = web_auth._error_page("/chat?x=1", reason)
    body = resp.body.decode("utf-8")
    assert resp.status_code == 200
    # Reason rendered escaped, never raw.
    assert "IdP said &lt;no&gt; &amp; &quot;denied&quot;" in body
    assert "<no>" not in body
    # Retry path preserves the validated next destination.
    assert '/auth/login?next=%2Fchat%3Fx%3D1' in body
    # Bounded: no auto-redirect of any kind.
    assert "http-equiv" not in body.lower()
    assert "<script" not in body.lower()


def test_error_page_sanitizes_malicious_next():
    """028 FR-004 + research D1: an attacker-controlled next on the error
    page is re-validated, so the retry link can only point at /auth/login
    with a same-origin destination."""
    resp = web_auth._error_page("https://evil.com", "boom")
    body = resp.body.decode("utf-8")
    assert '/auth/login?next=%2F"' in body
    assert "evil.com" not in body


# ---------------------------------------------------------------------------
# session_roles (FR-005)
# ---------------------------------------------------------------------------

def test_session_roles_mock_mode(monkeypatch):
    """028 FR-005: mock auth still mirrors the WS/REST mock principal —
    shell-render gating sees ['admin', 'user']."""
    monkeypatch.setenv("VITE_USE_MOCK_AUTH", "true")
    assert web_auth.session_roles(_FakeRequest()) == ["admin", "user"]
