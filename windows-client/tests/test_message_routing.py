"""Feature 044 (US1) — desktop inbound routing, connection UX, sign-out ladder.

Constructs a MainWindow with the transport + integrity check stubbed so no real
socket/thread runs, then drives _on_message / _on_status directly and asserts
the visible banner + turn state (FR-002/FR-003/FR-006/SC-006).
"""
import os

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ASTRAL_WIN_AGENT"] = "0"  # don't spawn the client-hosted tools agent

from astral_client import app as appmod  # noqa: E402
from astral_client.app import MainWindow, normalize_error  # noqa: E402


class _FakeClient:
    """Stands in for OrchestratorClient — records sends, never touches a socket."""
    def __init__(self, *a, **k):
        self.sent = []
        self._sig = None

    class _Sig:
        def connect(self, *_a):
            pass

    message = _Sig()
    status = _Sig()

    def start(self):
        pass

    def stop(self):
        pass

    def send_event(self, action, payload, session_id=None):
        self.sent.append((action, payload))

    def send_chat(self, *a, **k):
        pass


@pytest.fixture
def win(qapp, monkeypatch):
    monkeypatch.setattr(appmod, "OrchestratorClient", _FakeClient)
    monkeypatch.setattr(MainWindow, "_start_integrity_check", lambda self: None)
    # These are message-routing tests, not workspace tests: stub the workspace
    # init so constructing the window doesn't mutate process env
    # (ASTRAL_WORKSPACE_DIR) and leak into the win_agent tool tests.
    monkeypatch.setattr(MainWindow, "_init_workspace", lambda self: None)
    w = MainWindow("ws://127.0.0.1:9/ws", "dev-token")
    yield w
    w.close()


# --- normalize_error: the three historical shapes (FR-002) ------------------

def test_normalize_error_shapes():
    assert normalize_error({"message": "boom"}) == "boom"
    assert normalize_error({"payload": {"message": "deep boom"}}) == "deep boom"
    assert normalize_error({"code": "llm_config_invalid", "message": "bad"}) == "bad (llm_config_invalid)"
    assert normalize_error({"code": "internal", "message": "x"}) == "x"  # internal code hidden
    assert "wrong" in normalize_error({}).lower()


# --- error frames are visible and resolve the turn (SC-006) -----------------

def test_error_frame_shows_banner_and_resolves_turn(win):
    win._turn_active = True
    win._on_message({"type": "error", "code": "internal", "message": "server fell over"})
    assert (not win._banner.isHidden())
    assert "server fell over" in win._banner.text()
    assert win._turn_active is False


def test_notification_frame_shows_banner(win):
    win._on_message({"type": "notification", "title": "Job done", "body": "report ready", "level": "info"})
    assert (not win._banner.isHidden())
    assert "Job done" in win._banner.text() and "report ready" in win._banner.text()


# --- unknown vs classified-ignored logging (FR-002) -------------------------

def test_unknown_frame_is_logged_not_crashing(win, caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="astral.client"):
        win._on_message({"type": "totally_new_server_frame"})
    assert any("unhandled frame type=totally_new_server_frame" in r.message for r in caplog.records)


def test_classified_ignore_is_info_not_warning(win, caplog):
    import logging
    with caplog.at_level(logging.INFO, logger="astral.client"):
        win._on_message({"type": "heartbeat"})  # classified "ignored"
    assert any("ignored frame type=heartbeat" in r.message for r in caplog.records)
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)


# --- progress signals reach a terminal state (FR-006) -----------------------

def test_progress_signals_and_terminal(win):
    win._on_message({"type": "user_message_acked"})
    assert win._turn_active is True
    win._on_message({"type": "chat_step", "step": {"name": "search", "status": "completed"}})
    win._on_message({"type": "tool_progress", "label": "fetching page 2"})
    win._on_message({"type": "task_started", "task_id": "t1"})
    assert (not win._banner.isHidden())
    win._on_message({"type": "task_completed", "task_id": "t1"})
    assert win._turn_active is False


# --- connection UX (FR-003) -------------------------------------------------

def test_reconnecting_status_shows_banner(win):
    win._connected_once = True
    win._on_status("reconnecting:3")
    assert (not win._banner.isHidden())
    assert "attempt 3" in win._banner.text()


def test_connected_hides_banner(win):
    win._on_status("reconnecting:1")
    assert (not win._banner.isHidden())
    win._on_status("connected")
    assert not (not win._banner.isHidden())


def test_send_dropped_is_visible(win):
    win._on_status("send_dropped:chat_message")
    assert (not win._banner.isHidden())
    assert "chat_message" in win._banner.text()


# --- dead-auth sign-in affordance (FR-004) ----------------------------------

def test_expired_dev_session_does_not_dead_end(win):
    # dev-token / no login params → explicit guidance, not a frozen caption
    win._auth_session = None
    win._login_params = {}
    win._on_status("auth_required:expired")
    assert (not win._banner.isHidden())
    assert "expired" in win._banner.text().lower()


# --- workspace timeline read-only banner (FR-007 seed) ----------------------

def test_timeline_mode_banner(win):
    win._on_message({"type": "workspace_timeline_mode", "active": True})
    assert win._timeline_mode is True
    assert (not win._banner.isHidden())
    win._on_message({"type": "workspace_timeline_mode", "active": False})
    assert win._timeline_mode is False
