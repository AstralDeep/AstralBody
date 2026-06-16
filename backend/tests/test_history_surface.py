"""Feature 037 — server-driven chat-history surface tests.

Covers the history component builders (skeleton + clickable recent-chats list),
their web rendering, and ROTE voice adaptation. Pure Python — no DB, no socket.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from orchestrator.history_surface import (  # noqa: E402
    history_skeleton_components,
    history_surface_components,
)
from rote.adapter import ComponentAdapter  # noqa: E402
from rote.capabilities import DeviceProfile  # noqa: E402
from webrender.renderer import render  # noqa: E402


def test_skeleton_components_have_heading_and_skeleton():
    comps = history_skeleton_components()
    assert comps[0]["type"] == "text" and comps[0]["content"] == "Recent chats"
    assert any(c["type"] == "skeleton" and c["variant"] == "chat-history" for c in comps)
    assert "astral-skeleton" in render(comps)


def test_surface_builds_load_chat_buttons():
    comps = history_surface_components([
        {"id": "c1", "title": "Trip to Rome"},
        {"id": "c2", "title": ""},                 # blank title → fallback
    ])
    container = next(c for c in comps if c["type"] == "container")
    btns = container["children"]
    assert [b["action"] for b in btns] == ["load_chat", "load_chat"]
    assert btns[0]["payload"] == {"chat_id": "c1"}
    assert btns[0]["label"] == "Trip to Rome"
    assert btns[1]["label"] == "Untitled chat"
    html = render(comps)
    assert "Trip to Rome" in html and "load_chat" in html


def test_surface_accepts_chat_id_key():
    comps = history_surface_components([{"chat_id": "x9", "title": "Alt key"}])
    container = next(c for c in comps if c["type"] == "container")
    assert container["children"][0]["payload"] == {"chat_id": "x9"}


def test_surface_empty_and_idless():
    assert history_surface_components([])[0]["content"] == "No conversations yet."
    # a chat with no id cannot be opened → skipped → empty state
    assert history_surface_components([{"title": "no id"}])[0]["content"] == "No conversations yet."


def test_voice_collapses_history_to_speech():
    out = ComponentAdapter.adapt(history_skeleton_components(),
                                 DeviceProfile.from_dict({"device_type": "voice"}))
    assert all(c["type"] == "text" for c in out)
    joined = " ".join(c["content"] for c in out)
    assert "Recent chats" in joined and "Loading" in joined


def test_voice_speaks_chat_titles():
    out = ComponentAdapter.adapt(
        history_surface_components([{"id": "c1", "title": "Budget review"}]),
        DeviceProfile.from_dict({"device_type": "voice"}))
    joined = " ".join(c.get("content", "") for c in out)
    assert "Budget review" in joined
