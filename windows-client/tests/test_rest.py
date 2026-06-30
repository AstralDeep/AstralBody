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
    fetch_json,
    parse_audit_response,
)


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
