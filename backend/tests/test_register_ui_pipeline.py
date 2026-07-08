"""Feature 052 (T027) — register_ui handshake pipeline against the live DB.

Drives a real register_ui through Orchestrator.handle_ui_message on an
in-process VirtualWebSocket (mock-auth dev token): the welcome canvas and
dashboard both arrive, rote_config still precedes the dashboard frame, and
the off-critical-path writes (profile save, the two login audit events in
order) still complete (FR-012 — reads parallelized, writes backgrounded,
audit completeness preserved).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "http://fake.api")
os.environ.setdefault("LLM_MODEL", "test-model")

pytestmark = pytest.mark.asyncio


def _fresh_socket():
    """A VirtualWebSocket capturing every frame the handshake sends."""
    from orchestrator.async_tasks import BackgroundTask, VirtualWebSocket
    task = BackgroundTask(task_id=uuid.uuid4().hex, chat_id="", user_id="")
    return VirtualWebSocket(task)


async def _drain_background_tasks():
    """Give the handshake's create_task work (profile/audit) time to finish."""
    for _ in range(20):
        await asyncio.sleep(0.02)


@pytest.fixture()
def orch(monkeypatch):
    """A real Orchestrator under mock auth (dev-token => test_user)."""
    monkeypatch.setenv("VITE_USE_MOCK_AUTH", "true")
    from orchestrator.orchestrator import Orchestrator
    try:
        return Orchestrator()
    except Exception as exc:
        pytest.skip(f"orchestrator/database unavailable: {exc}")


async def test_register_ui_delivers_welcome_and_dashboard(orch):
    """The handshake still delivers rote_config, system_config and welcome."""
    ws = _fresh_socket()
    orch._registered_events[id(ws)] = asyncio.Event()
    await orch.handle_ui_message(ws, json.dumps(
        {"type": "register_ui", "token": "dev-token", "device": {}}))
    await _drain_background_tasks()

    frame_types = [f.get("type") for f in ws.task.outputs]
    assert "rote_config" in frame_types
    assert "system_config" in frame_types, "dashboard must still arrive"
    renders = [f for f in ws.task.outputs
               if f.get("type") == "ui_render" and f.get("target") != "chat"]
    assert renders, "welcome canvas ui_render must arrive"
    assert orch._registered_events[id(ws)].is_set()
    assert orch._ws_welcome.get(id(ws)) is True

    # rote_config still precedes the dashboard payload — native clients learn
    # their device profile before any adapted content lands.
    assert frame_types.index("rote_config") < frame_types.index("system_config")


async def test_register_ui_audit_events_recorded_in_order(orch, monkeypatch):
    """ws_register then login_interactive/session_resumed, off-path but complete."""
    from audit import hooks as audit_hooks
    recorded = []

    async def _capture(*, claims, action, description, **kw):
        recorded.append(action)

    monkeypatch.setattr(audit_hooks, "record_auth_event", _capture)
    ws = _fresh_socket()
    orch._registered_events[id(ws)] = asyncio.Event()
    await orch.handle_ui_message(ws, json.dumps(
        {"type": "register_ui", "token": "dev-token", "device": {}, "resumed": False}))
    await _drain_background_tasks()

    assert "ws_register" in recorded
    assert "login_interactive" in recorded
    assert recorded.index("ws_register") < recorded.index("login_interactive")


async def test_register_ui_persists_user_profile(orch):
    """The backgrounded profile save still upserts the JWT user row."""
    ws = _fresh_socket()
    orch._registered_events[id(ws)] = asyncio.Event()
    await orch.handle_ui_message(ws, json.dumps(
        {"type": "register_ui", "token": "dev-token", "device": {}}))
    await _drain_background_tasks()

    row = await orch.history.db.afetch_one(
        "SELECT id FROM users WHERE id = ?", ("test_user",))
    assert row is not None, "profile save must still complete (audit-complete writes)"
