"""Unit tests for start.py's orchestrator readiness poll (feature 052, FR-029).

``_wait_for_orchestrator`` must proceed on the first healthy /healthz
response, stop early when the orchestrator process dies, and give up (but
never block startup) after the timeout. The module import itself is
side-effect free beyond dotenv loading, so importing it here is safe.
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import start  # noqa: E402


class _Proc:
    """Fake subprocess handle with a fixed poll() result."""

    def __init__(self, poll_result=None):
        self._poll_result = poll_result
        self.returncode = poll_result

    def poll(self):
        return self._poll_result


class _Resp:
    """Context-manager stand-in for urllib's HTTP response."""

    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_returns_true_on_first_healthy_response(monkeypatch):
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda url, timeout=0: _Resp(200))
    assert start._wait_for_orchestrator(8001, _Proc(None), timeout_s=5.0,
                                        interval_s=0.01) is True


def test_returns_false_when_process_exits_early(monkeypatch):
    def _refuse(url, timeout=0):
        raise ConnectionError("refused")

    monkeypatch.setattr(urllib.request, "urlopen", _refuse)
    assert start._wait_for_orchestrator(8001, _Proc(78), timeout_s=5.0,
                                        interval_s=0.01) is False


def test_returns_false_after_timeout_with_unreachable_endpoint(monkeypatch):
    def _refuse(url, timeout=0):
        raise ConnectionError("refused")

    monkeypatch.setattr(urllib.request, "urlopen", _refuse)
    assert start._wait_for_orchestrator(8001, _Proc(None), timeout_s=0.05,
                                        interval_s=0.01) is False


def test_non_200_response_keeps_polling_until_timeout(monkeypatch):
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda url, timeout=0: _Resp(503))
    assert start._wait_for_orchestrator(8001, _Proc(None), timeout_s=0.05,
                                        interval_s=0.01) is False


def test_polls_the_configured_port(monkeypatch):
    seen = {}

    def _capture(url, timeout=0):
        seen["url"] = url
        return _Resp(200)

    monkeypatch.setattr(urllib.request, "urlopen", _capture)
    assert start._wait_for_orchestrator(9123, _Proc(None), timeout_s=5.0,
                                        interval_s=0.01) is True
    assert seen["url"] == "http://localhost:9123/healthz"


def test_module_import_is_side_effect_free():
    assert callable(start.main)
    assert os.path.basename(start.__file__) == "start.py"
