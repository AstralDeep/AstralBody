"""Feature 039 (C-6): deployment config resolution for a bare-downloaded exe.

Precedence: env > persisted QSettings > first-run prompt. Without this a
double-clicked exe silently fell back to a dev token the real-auth orchestrator
rejects, so the app "did nothing".
"""
import os

import pytest

pytest.importorskip("PySide6")
from astral_client import app  # noqa: E402


class _FakeSettings:
    def __init__(self, d=None):
        self.d = dict(d or {})

    def value(self, key, default="", type=str):
        return self.d.get(key, default)

    def setValue(self, key, val):
        self.d[key] = val


class _Args:
    def __init__(self, token="", authority="", url="ws://127.0.0.1:8001/ws"):
        self.token = token
        self.authority = authority
        self.url = url


def _no_prompt(*_a):
    raise AssertionError("prompt should not be called")


def test_env_authority_wins(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_AUTHORITY", "https://kc/realms/A")
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    a = _Args()
    app._resolve_config(a, settings=_FakeSettings(), prompt=_no_prompt)
    assert a.authority == "https://kc/realms/A"


def test_qsettings_fallback(monkeypatch):
    monkeypatch.delenv("KEYCLOAK_AUTHORITY", raising=False)
    monkeypatch.delenv("ASTRAL_WS_URL", raising=False)
    a = _Args()
    s = _FakeSettings({"config/authority": "https://kc2/realms/B",
                       "config/ws_url": "ws://orch:8001/ws"})
    app._resolve_config(a, settings=s, prompt=_no_prompt)
    assert a.authority == "https://kc2/realms/B"
    assert a.url == "ws://orch:8001/ws"


def test_prompt_when_unconfigured_persists(monkeypatch):
    monkeypatch.delenv("KEYCLOAK_AUTHORITY", raising=False)
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    monkeypatch.delenv("ASTRAL_WS_URL", raising=False)
    a = _Args()
    s = _FakeSettings()
    seen = {}

    def fake_prompt(au, url, key):
        seen["called"] = (au, url, key)
        return ("https://kc3/realms/C", "ws://host:8001/ws", "sekret")

    try:
        app._resolve_config(a, settings=s, prompt=fake_prompt)
        assert seen.get("called")
        assert a.authority == "https://kc3/realms/C"
        assert a.url == "ws://host:8001/ws"
        assert os.environ.get("AGENT_API_KEY") == "sekret"
        assert s.d["config/authority"] == "https://kc3/realms/C"
        assert s.d["config/agent_key"] == "sekret"
    finally:
        os.environ.pop("AGENT_API_KEY", None)


def test_no_prompt_when_token_present(monkeypatch):
    monkeypatch.delenv("KEYCLOAK_AUTHORITY", raising=False)
    a = _Args(token="dev-token")
    app._resolve_config(a, settings=_FakeSettings(), prompt=_no_prompt)
    assert a.authority == ""  # stays empty; no prompt with an explicit token
