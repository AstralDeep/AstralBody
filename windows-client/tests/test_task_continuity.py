"""Feature 055 — cross-device background-task continuity on the desktop.

A job started on ONE device must surface live on every other device: a
``task_completed``/``notification`` for the OPEN chat re-issues ``load_chat``
(narrative + canvas refresh without user action); for ANOTHER chat the banner
becomes a tap-to-open toast; ``task_started`` elsewhere is an unobtrusive
status notice. Reconnect re-registers with the active chat id as
``session_id`` (the server resumes the fan + replays task state) and reloads
the previously open chat.
"""
import os

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ASTRAL_WIN_AGENT"] = "0"  # don't spawn the client-hosted tools agent

from astral_client import app as appmod  # noqa: E402
from astral_client.app import MainWindow, frame_chat_id  # noqa: E402
from astral_client.protocol import OrchestratorClient  # noqa: E402


class _FakeClient:
    """Stands in for OrchestratorClient — records sends, never touches a socket."""
    def __init__(self, *a, **k):
        self.sent = []
        self.session_id = "win-client"

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
    monkeypatch.setattr(MainWindow, "_init_workspace", lambda self: None)
    w = MainWindow("ws://127.0.0.1:9/ws", "dev-token")
    yield w
    w.close()


def _sent_load_chats(win):
    return [p for a, p in win.client.sent if a == "load_chat"]


# --- frame_chat_id: both wire shapes (pure) -----------------------------------

def test_frame_chat_id_reads_payload_then_top_level():
    assert frame_chat_id({"payload": {"chat_id": "c1"}}) == "c1"
    assert frame_chat_id({"chat_id": "c2"}) == "c2"  # scheduler notification
    assert frame_chat_id({"payload": {"chat_id": "c1"}, "chat_id": "c2"}) == "c1"
    assert frame_chat_id({"payload": {}}) is None
    assert frame_chat_id({}) is None


# --- task_completed: open chat refreshes, other chat taps-to-open --------------

def test_task_completed_for_open_chat_reloads_it(win):
    win.active_chat = "c1"
    win._on_message({"type": "task_completed",
                     "payload": {"task_id": "t1", "chat_id": "c1", "status": "completed"}})
    assert _sent_load_chats(win) == [{"chat_id": "c1"}]
    assert not win._banner.isHidden()
    assert win._banner_chat is None  # click just dismisses


def test_task_completed_for_other_chat_is_tap_to_open(win):
    win.active_chat = "c1"
    win._on_message({"type": "task_completed",
                     "payload": {"task_id": "t1", "chat_id": "c2", "status": "completed"}})
    assert _sent_load_chats(win) == []  # never hijacks the open canvas
    assert not win._banner.isHidden()
    assert win._banner_chat == "c2"
    win._on_banner_clicked()
    assert _sent_load_chats(win) == [{"chat_id": "c2"}]
    assert win._banner.isHidden()
    assert win._banner_chat is None


def test_task_completed_without_chat_keeps_legacy_banner(win):
    win.active_chat = "c1"
    win._on_message({"type": "task_completed", "payload": {"task_id": "t1"}})
    assert _sent_load_chats(win) == []
    assert not win._banner.isHidden()
    assert win._banner_chat is None


# --- notification: same routing, top-level chat_id ------------------------------

def test_notification_for_open_chat_reloads_it(win):
    win.active_chat = "c1"
    win._on_message({"type": "notification", "level": "info", "chat_id": "c1",
                     "title": "Report ready", "body": "Nightly digest finished."})
    assert _sent_load_chats(win) == [{"chat_id": "c1"}]
    assert "Report ready" in win._banner.text()


def test_notification_for_other_chat_click_opens_it(win):
    win.active_chat = "c1"
    win._on_message({"type": "notification", "level": "info", "chat_id": "c2",
                     "title": "Report ready", "body": "Done."})
    assert _sent_load_chats(win) == []
    assert win._banner_chat == "c2"
    win._on_banner_clicked()
    assert _sent_load_chats(win) == [{"chat_id": "c2"}]


def test_notification_without_chat_click_just_dismisses(win):
    win._on_message({"type": "notification", "level": "error", "body": "boom"})
    assert win._banner_chat is None
    win._on_banner_clicked()
    assert _sent_load_chats(win) == []
    assert win._banner.isHidden()


def test_plain_banner_clears_stale_tap_target(win):
    win.active_chat = "c1"
    win._on_message({"type": "task_completed",
                     "payload": {"task_id": "t1", "chat_id": "c2"}})
    assert win._banner_chat == "c2"
    win._show_banner("Component saved")  # any ordinary notice
    assert win._banner_chat is None


# --- task_started: elsewhere = status notice, here = banner ---------------------

def test_task_started_in_other_chat_is_status_notice_not_banner(win):
    win.active_chat = "c1"
    win._on_message({"type": "task_started",
                     "payload": {"task_id": "t1", "chat_id": "c2", "status": "queued"}})
    assert win._banner.isHidden()
    assert "another chat" in win.topbar._mark.toolTip().lower()


def test_task_started_in_open_chat_keeps_banner(win):
    win.active_chat = "c1"
    win._on_message({"type": "task_started",
                     "payload": {"task_id": "t1", "chat_id": "c1", "status": "queued"}})
    assert not win._banner.isHidden()
    assert "background" in win._banner.text().lower()


def test_task_started_without_chat_keeps_banner(win):
    win._on_message({"type": "task_started", "payload": {"task_id": "t1"}})
    assert not win._banner.isHidden()


# --- reconnect: re-register resumes the open chat -------------------------------

def test_reconnect_reissues_load_chat_for_open_chat(win):
    win.active_chat = "c1"
    win._on_status("connected")
    assert {"chat_id": "c1"} in _sent_load_chats(win)


def test_first_connect_without_chat_sends_no_load_chat(win):
    win._on_status("connected")
    assert _sent_load_chats(win) == []


def test_active_chat_drives_transport_session_id(win):
    win._on_message({"type": "chat_loaded", "chat": {"id": "c9", "messages": []}})
    assert win.client.session_id == "c9"
    win._on_message({"type": "chat_created", "payload": {"chat_id": "c10"}})
    assert win.client.session_id == "c10"
    win._new_chat()
    assert win.client.session_id == "win-client"


def test_register_frame_carries_session_id(qapp):
    c = OrchestratorClient("ws://127.0.0.1:9/ws", "tok")
    frame = c._register_frame()
    assert frame["type"] == "register_ui"
    assert frame["session_id"] == "win-client"
    c.session_id = "chat-42"
    assert c._register_frame()["session_id"] == "chat-42"


def test_register_frame_declares_host_capability(qapp):
    """058: the desktop client hosts BYO agents, so it must declare itself
    host-capable at register_ui — else the first bundle delivery finds no host
    (mark-by-demonstration is chicken-and-egg)."""
    c = OrchestratorClient("ws://127.0.0.1:9/ws", "tok")
    frame = c._register_frame()
    assert frame["agent_host"] is True
    assert "agent_host" in frame["capabilities"]
    assert frame["host_session_id"] == c.host_session_id and c.host_session_id
    # stable across reconnects (re-register must not mint a new id)
    assert c._register_frame()["host_session_id"] == frame["host_session_id"]
