"""Tests for ``astral_client.rest`` (the audit REST helper).

Pure logic + an injected ``opener`` — no Qt, no network. Covers URL building,
response shaping, the Bearer header, and error mapping.
"""
import urllib.error

import pytest

from astral_client.rest import (
    EVENT_CLASSES,
    OUTCOMES,
    RestError,
    audit_url,
    chrome_menu_url,
    fetch_json,
    keycloak_logout,
    native_logout,
    parse_audit_response,
    parse_chrome_menu,
    upload_attachment,
)


# ── feature 044: server-revoking sign-out (FR-005) ──────────────────────────

class _FakeLogoutResp:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, *a):
        return b""


def test_native_logout_posts_bearer_and_body():
    seen = {}

    def opener(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["auth"] = req.get_header("Authorization")
        seen["body"] = req.data
        return _FakeLogoutResp(200)

    ok = native_logout("http://h:8001", "acc-tok", "rt-1", "astral-desktop", opener=opener)
    assert ok is True
    assert seen["url"] == "http://h:8001/api/auth/logout"
    assert seen["method"] == "POST"
    assert seen["auth"] == "Bearer acc-tok"
    import json as _j
    body = _j.loads(seen["body"])
    assert body == {"refresh_token": "rt-1", "client_id": "astral-desktop"}


def test_native_logout_false_on_error_status():
    def opener(req, timeout=None):
        return _FakeLogoutResp(500)

    assert native_logout("http://h:8001", "t", "rt", "astral-desktop", opener=opener) is False


def test_native_logout_false_on_transport_error():
    def opener(req, timeout=None):
        raise OSError("connection refused")

    assert native_logout("http://h:8001", "t", "rt", "astral-desktop", opener=opener) is False


def test_keycloak_logout_direct_fallback():
    seen = {}

    def opener(req, timeout=None):
        seen["url"] = req.full_url
        seen["body"] = req.data
        return _FakeLogoutResp(204)

    ok = keycloak_logout("https://iam.example/realms/Astral", "astral-desktop", "rt-9", opener=opener)
    assert ok is True
    assert seen["url"] == "https://iam.example/realms/Astral/protocol/openid-connect/logout"
    assert b"refresh_token=rt-9" in seen["body"] and b"client_id=astral-desktop" in seen["body"]


def test_keycloak_logout_noop_without_inputs():
    assert keycloak_logout("", "c", "rt") is False
    assert keycloak_logout("https://iam", "c", "") is False


# ── feature 042: chrome menu model (single server-owned source of truth) ──────

def test_chrome_menu_url():
    assert chrome_menu_url("http://h:8001/") == "http://h:8001/api/chrome/menu"


def test_parse_chrome_menu_full():
    model = {
        "version": 1,
        "topbar": [
            {"key": "brand", "kind": "brand"},
            {"key": "timeline", "kind": "action", "label": "Workspace timeline",
             "icon": "history", "action": {"surface": "workspace_timeline", "params": {}}},
            {"key": "settings", "kind": "menu", "label": "Settings", "icon": "gear"},
        ],
        "menu": [
            {"key": "account", "label": "Account", "items": [
                {"key": "agents", "label": "Agents & permissions", "surface": "agents", "params": {}},
                {"key": "audit", "label": "Audit log", "surface": "audit", "params": {}},
            ]},
            {"key": "admin", "label": "Admin tools", "admin_only": True, "items": [
                {"key": "tq", "label": "Tool quality", "surface": "admin_tools", "params": {"tab": "quality"}},
            ]},
        ],
        "signout": {"key": "signout", "label": "Sign out", "style": "danger", "action": "logout"},
    }
    parsed = parse_chrome_menu(model)
    assert [s["label"] for s in parsed["sections"]] == ["Account", "Admin tools"]
    assert [i["surface"] for i in parsed["sections"][0]["items"]] == ["agents", "audit"]
    assert parsed["sections"][0]["items"][0]["label"] == "Agents & permissions"
    assert parsed["sections"][1]["items"][0]["params"] == {"tab": "quality"}
    assert [a["surface"] for a in parsed["topbar_actions"]] == ["workspace_timeline"]
    assert parsed["signout"] == {"label": "Sign out", "action": "logout"}


def test_parse_chrome_menu_tolerates_empty_and_malformed():
    assert parse_chrome_menu({}) == {
        "sections": [], "topbar_actions": [],
        "signout": {"label": "Sign out", "action": "logout"},
    }
    assert parse_chrome_menu(None)["sections"] == []
    # items without a surface are dropped; a group with no valid items is dropped.
    m = {"menu": [
        {"label": "Empty", "items": [{"label": "nosurf"}]},
        {"label": "Ok", "items": [{"label": "A", "surface": "agents"}]},
    ]}
    assert [s["label"] for s in parse_chrome_menu(m)["sections"]] == ["Ok"]


def test_audit_url_minimal():
    assert audit_url("http://h:8001") == "http://h:8001/api/audit?limit=50"


def test_audit_url_strips_trailing_slash_and_encodes_filters():
    u = audit_url("http://h:8001/", limit=25, event_class="auth",
                  outcome="failure", q="login x", cursor="c1")
    assert u.startswith("http://h:8001/api/audit?")
    assert "limit=25" in u
    assert "event_class=auth" in u
    assert "outcome=failure" in u
    assert "q=login+x" in u   # urlencoded space
    assert "cursor=c1" in u


def test_audit_url_omits_empty_filters():
    assert audit_url("http://h:8001", event_class="", outcome="", q="", cursor="") \
        == "http://h:8001/api/audit?limit=50"


def test_parse_audit_response_rows_and_cursor():
    data = {
        "items": [{
            "event_id": "e1",
            "recorded_at": "2026-06-30T12:34:56.789012+00:00",
            "event_class": "auth",
            "action_type": "auth.ws_register",
            "outcome": "success",
            "description": "registered",
        }],
        "next_cursor": "NEXT",
    }
    rows, nxt = parse_audit_response(data)
    assert nxt == "NEXT"
    assert rows[0]["recorded_at"] == "2026-06-30 12:34:56"   # ISO -> display
    assert rows[0]["event_class"] == "auth"
    assert rows[0]["outcome"] == "success"
    assert rows[0]["action_type"] == "auth.ws_register"


def test_parse_audit_response_empty_and_missing_cursor():
    rows, nxt = parse_audit_response({"items": []})
    assert rows == [] and nxt is None


def test_parse_audit_response_defensive_against_bad_items():
    rows, _ = parse_audit_response({"items": [None, 7, {"event_id": "e"}]})
    assert len(rows) == 1
    assert rows[0]["event_class"] == ""   # missing key -> empty string
    assert rows[0]["recorded_at"] == "-"  # missing ts -> dash


class _FakeResp:
    def __init__(self, data: bytes):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n: int = -1) -> bytes:
        return self._data


def test_fetch_json_sends_bearer_and_parses():
    captured = {}

    def opener(req, timeout=None):
        captured["auth"] = req.get_header("Authorization")
        captured["url"] = req.full_url
        return _FakeResp(b'{"items": [], "next_cursor": null}')

    data = fetch_json("http://h/api/audit?limit=50", "TOK", opener=opener)
    assert data == {"items": [], "next_cursor": None}
    assert captured["auth"] == "Bearer TOK"
    assert captured["url"] == "http://h/api/audit?limit=50"


def test_fetch_json_http_error_becomes_resterror():
    def opener(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    with pytest.raises(RestError) as ei:
        fetch_json("http://h/api/audit", "TOK", opener=opener)
    assert ei.value.status == 401


def test_fetch_json_transport_error_becomes_resterror():
    def opener(req, timeout=None):
        raise OSError("connection refused")

    with pytest.raises(RestError) as ei:
        fetch_json("http://h/api/audit", "TOK", opener=opener)
    assert ei.value.status == 0


def test_event_classes_and_outcomes_exported():
    assert "auth" in EVENT_CLASSES and "agent_lifecycle" in EVENT_CLASSES
    assert OUTCOMES == ("in_progress", "success", "failure", "interrupted")


# ── feature 044: chat attachment upload (US4, T043) ──────────────────────────

def test_upload_attachment_multipart_bearer_and_parse():
    seen = {}

    def opener(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["auth"] = req.get_header("Authorization")
        seen["ctype"] = req.get_header("Content-type")  # urllib capitalizes the key
        seen["body"] = req.data
        return _FakeResp(
            b'{"attachment_id":"att-1","filename":"a.csv",'
            b'"category":"data","parser_status":"covered"}'
        )

    out = upload_attachment("http://h:8001", "TOK", "a.csv", "text/csv",
                            b"col\n1\n", opener=opener)
    assert out == {"attachment_id": "att-1", "filename": "a.csv",
                   "category": "data", "parser_status": "covered"}
    assert seen["url"] == "http://h:8001/api/upload"
    assert seen["method"] == "POST"
    assert seen["auth"] == "Bearer TOK"
    assert seen["ctype"].startswith("multipart/form-data; boundary=")
    assert b'name="file"; filename="a.csv"' in seen["body"]
    assert b"col\n1\n" in seen["body"]        # the file bytes are in the body


def test_upload_attachment_http_error_becomes_resterror():
    def opener(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 413, "Payload Too Large", {}, None)

    with pytest.raises(RestError) as ei:
        upload_attachment("http://h", "T", "f", "text/plain", b"x", opener=opener)
    assert ei.value.status == 413


def test_upload_attachment_transport_error_becomes_resterror():
    def opener(req, timeout=None):
        raise OSError("connection refused")

    with pytest.raises(RestError) as ei:
        upload_attachment("http://h", "T", "f", "text/plain", b"x", opener=opener)
    assert ei.value.status == 0
