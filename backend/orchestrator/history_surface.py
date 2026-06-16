"""Feature 037 — server-driven chat-history surface components.

Builds the astralprims components for the recent-chats list and its loading
skeleton. The orchestrator delivers them via ``send_ui_render(target="history")``
so ROTE adapts them per device (browser/tablet/TV full list, mobile/watch
condensed, voice spoken) — the history surface is server-driven and
cross-platform, never a web-only client render.

Pure builders (no orchestrator/DB dependency) so they are unit-testable on
their own; the orchestrator only supplies the recent-chats rows.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from webrender.renderer import skeleton_component

#: Cap the rendered list; older chats stay reachable via search/scroll.
MAX_HISTORY_ITEMS = 20

_HEADING = {"type": "text", "content": "Recent chats", "variant": "h3"}


def history_skeleton_components(label: str = "Loading your chats…") -> List[Dict[str, Any]]:
    """The loading state: a heading + a chat-history skeleton (feature 037)."""
    return [dict(_HEADING), skeleton_component(variant="chat-history", count=6, label=label)]


def _chat_id(chat: Dict[str, Any]) -> Optional[str]:
    cid = chat.get("id") or chat.get("chat_id")
    return str(cid) if cid else None


def history_surface_components(chats: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The loaded state: a heading + one ``load_chat`` button per recent chat.

    A chat with no id is skipped (it cannot be opened). With no openable chats
    the surface shows an empty-state line rather than a bare heading.
    """
    items: List[Dict[str, Any]] = []
    for chat in list(chats or [])[:MAX_HISTORY_ITEMS]:
        if not isinstance(chat, dict):
            continue
        cid = _chat_id(chat)
        if not cid:
            continue
        title = str(chat.get("title") or "Untitled chat").strip() or "Untitled chat"
        items.append({
            "type": "button",
            "label": title,
            "variant": "ghost",
            "action": "load_chat",
            "payload": {"chat_id": cid},
        })
    if not items:
        return [{"type": "text", "content": "No conversations yet.", "variant": "caption"}]
    return [dict(_HEADING), {"type": "container", "children": items}]
