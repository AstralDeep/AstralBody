"""Feature 055 (US1, T014) — first-turn loading contract on the desktop.

The uniform rule: welcome components arrive with `id` AND `component_id` set
to the same `wel_`-prefixed value; at turn start the client purges every
component whose (component_id ?? id) starts with `wel_` and arms the loading
skeleton — on the TYPED composer path (`_send`, previously skeleton-less) as
well as the example-card path (`_emit` chat_message). Mid-turn an empty full
render keeps the loading state (never the idle "interface appears here"
hint); out-of-turn empty renders remain authoritative clears that resolve to
the hint. When the server flag is off the welcome arrives id-less, nothing
matches `wel_` and the purge is a byte-equivalent no-op.
"""
import os

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ASTRAL_WIN_AGENT"] = "0"  # don't spawn the client-hosted tools agent

from astral_client import app as appmod  # noqa: E402
from astral_client.app import Canvas, MainWindow  # noqa: E402
from astral_client.renderer import RenderContext  # noqa: E402


def _ctx():
    return RenderContext(emit=lambda *a: None, download=lambda *a: None)


def _card(cid):
    return {"type": "card", "component_id": cid, "content": []}


def _welcome():
    # Both identity fields set to the same wel_ value (wire-contract §1).
    return [
        {"type": "hero", "id": "wel_hero", "component_id": "wel_hero"},
        {"type": "card", "id": "wel_ex_weather", "component_id": "wel_ex_weather"},
        {"type": "text", "id": "wel_hint", "component_id": "wel_hint"},
    ]


class _FakeClient:
    """Stands in for OrchestratorClient — records sends, never touches a socket."""
    def __init__(self, *a, **k):
        self.sent = []
        self.chats = []

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
        self.chats.append((a, k))


@pytest.fixture
def win(qapp, monkeypatch):
    monkeypatch.setattr(appmod, "OrchestratorClient", _FakeClient)
    monkeypatch.setattr(MainWindow, "_start_integrity_check", lambda self: None)
    monkeypatch.setattr(MainWindow, "_init_workspace", lambda self: None)
    w = MainWindow("ws://127.0.0.1:9/ws", "dev-token")
    yield w
    w.close()


# --- typed composer send arms the same loading state as _emit ----------------

def test_typed_send_arms_skeleton(win):
    win._input.setText("hello")
    win._send()
    assert win.client.chats, "typed send never reached the transport"
    assert win.canvas._skeleton is not None
    assert win.canvas.turn_active is True


def test_typed_send_purges_welcome(win):
    win.canvas.set_components(_welcome())
    win._input.setText("what's the weather")
    win._send()
    assert win.canvas._last_components == []
    assert not any(k.startswith("wel_") for k in win.canvas._by_id)
    # loading state, not the idle hint, fills the emptied canvas
    assert win.canvas._skeleton is not None
    assert win.canvas._empty is None


def test_emit_chat_message_purges_welcome(win):
    win.canvas.set_components(_welcome())
    win._emit("chat_message", {"message": "roll 2d6"})
    assert win.canvas._last_components == []
    assert win.canvas._skeleton is not None
    assert win.canvas._empty is None


def test_purge_keeps_non_welcome_components(win):
    win.canvas.set_components([_card("A")] + _welcome())
    win._input.setText("again")
    win._send()
    assert list(win.canvas._by_id) == ["A"]
    assert win.canvas._last_components == [_card("A")]


def test_timeline_mode_suppresses_arming_and_purge(win):
    win.canvas.set_components(_welcome())
    win._timeline_mode = True
    win._input.setText("hi")
    win._send()
    assert win.canvas._skeleton is None          # same suppression _emit uses
    assert len(win.canvas._last_components) == 3  # historical view untouched


# --- flag-off byte equivalence: id-less welcome → purge is a no-op -----------

def test_purge_is_noop_for_idless_welcome(qapp):
    c = Canvas(_ctx())
    idless = [{"type": "hero"}, {"type": "card", "content": []}]
    c.set_components(idless)
    before = c._last_components
    c.purge_welcome()
    assert c._last_components is before  # untouched — no re-render at all


# --- mid-turn empty render keeps the loading state ---------------------------

def test_empty_render_mid_turn_keeps_skeleton_no_hint(qapp):
    c = Canvas(_ctx())
    c.set_components([_card("A")])
    c.turn_active = True
    c.show_skeleton()
    c.set_components([])                 # e.g. a legacy turn-start blanking frame
    assert c._skeleton is not None       # loading state survives
    assert c._empty is None              # never the idle hint mid-turn
    assert c._by_id == {}                # the clear itself still applied


def test_empty_render_mid_turn_on_empty_canvas_keeps_skeleton(qapp):
    # Early-exit path: canvas already empty (hint dropped by the armed
    # skeleton), the empty render must not tear the loading state down.
    c = Canvas(_ctx())
    c.turn_active = True
    c.show_skeleton()
    c.set_components([])
    assert c._skeleton is not None
    assert c._empty is None


# --- out-of-turn empty render remains an authoritative clear -----------------

def test_empty_render_out_of_turn_clears_and_shows_hint(qapp):
    c = Canvas(_ctx())
    c.set_components([_card("A")])
    assert c.turn_active is False
    c.set_components([])
    assert c._by_id == {}
    assert c._empty is not None          # idle hint back, exactly as today
    assert c._skeleton is None


# --- turn-end resolution -----------------------------------------------------

def test_done_resolves_text_only_turn_to_hint(win):
    # Welcome purged at send, turn produced no canvas output: done must
    # resolve the skeleton AND restore the idle hint (the server no longer
    # sends the turn-start empty render that used to leave it behind).
    win.canvas.set_components(_welcome())
    win._input.setText("just say hi")
    win._send()
    assert win.canvas._skeleton is not None
    win._on_message({"type": "chat_status", "status": "done"})
    assert win._turn_active is False
    assert win.canvas.turn_active is False
    assert win.canvas._skeleton is None
    assert win.canvas._empty is not None


def test_done_after_content_keeps_canvas_no_hint(win):
    win._input.setText("build a table")
    win._send()
    win.canvas.set_components([_card("A")])  # first content of the turn
    assert win.canvas._skeleton is None
    win._on_message({"type": "chat_status", "status": "done"})
    assert "A" in win.canvas._by_id
    assert win.canvas._empty is None
