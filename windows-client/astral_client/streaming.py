"""Client-side consumption of the orchestrator's **push** streaming protocol.

The orchestrator streams live tool output as ``ui_stream_data`` frames (Feature
001-tool-stream-ui; renumbered 040 era). Each frame carries a *dual shape*: an
``html`` projection for the web shell, and a structured ``components`` list
(ROTE-adapted SDUI dicts) for non-web targets — see the protocol note in
``backend/shared/protocol.py``. This native client renders the **structured**
``components`` and ignores ``html`` (there is no embedded web view).

This module is pure (no Qt): it translates a stream frame into canvas ops that
``Canvas.apply_ops`` already knows how to apply — an in-place upsert keyed by a
synthetic ``stream-<stream_id>`` component id (mirroring the web client's
``"stream-"+stream_id`` node), or by the frame's ``component_id`` when the
stream is bridged to a workspace identity (feature 055, ``FF_STREAM_ARTIFACTS``).
It owns the per-stream monotonic ``seq`` dedupe, the ``session_id`` filter,
terminal final/forget, and error rendering, so the behaviour is unit-testable
without constructing the GUI.

Wire reference (push fan-out, ``stream_manager`` + ``orchestrator``):
  ui_stream_data: {stream_id, session_id, seq, components[], html?, raw?,
                   terminal, error?, component_id?}
  stream_subscribed: {stream_id, tool_name, agent_id, session_id, max_fps,
                      min_fps, attached, component_id?}
  stream_error: {request_action, session_id, payload:{stream_id?, tool_name?,
                 code, message}}
The legacy *poll* system reuses the ``stream_*`` namespace with a flatter shape
(``stream_data`` keyed by ``tool_name``, no ``seq``/``terminal``); the helpers
here degrade to that shape gracefully but the desktop targets the push system.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

#: Canvas component-id prefix for a live stream's node (mirrors the web client).
STREAM_NODE_PREFIX = "stream-"


def stream_node_id(stream_id: str) -> str:
    """The canvas component id under which a stream renders in place."""
    return f"{STREAM_NODE_PREFIX}{stream_id}"


def _node_key(frame: dict) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(canvas_component_id, dedupe_key)`` for a stream frame.

    Push frames key on ``stream_id``; legacy poll frames (no ``stream_id``) key
    on ``tool_name``. Returns ``(None, None)`` for an unaddressable frame.

    A push frame carrying ``component_id`` (055 stream→workspace bridge) keys
    the canvas node by that identity instead — never a ``stream-<stream_id>``
    node — so the terminal persist ``ui_upsert`` under the same identity
    replaces the streamed content in place (no double render). The dedupe key
    stays ``stream_id``.
    """
    sid = frame.get("stream_id")
    if sid:
        cid = frame.get("component_id")
        return (str(cid) if cid else stream_node_id(str(sid))), str(sid)
    tool = frame.get("tool_name")
    if tool:
        return f"{STREAM_NODE_PREFIX}tool-{tool}", f"tool:{tool}"
    return None, None


def _error_component(err: dict) -> dict:
    """An ``alert`` SDUI dict for an in-frame stream error. A retryable error is
    a (recoverable) warning; anything else is a hard failure."""
    retryable = bool(err.get("retryable"))
    text = err.get("message") or err.get("code") or "stream error"
    return {
        "type": "alert",
        "variant": "warning" if retryable else "error",
        "title": "Live update interrupted" if retryable else "Live update failed",
        "message": str(text),
    }


def stream_frame_to_ops(
    frame: dict, *, active_chat: Optional[str], seq_state: Dict[str, int]
) -> List[dict]:
    """Translate one ``ui_stream_data`` (or legacy ``stream_data``) frame into
    canvas ops. Returns ``[]`` when the frame is dropped (unaddressable, for
    another chat, or stale) or carries nothing renderable.

    ``seq_state`` (stream-key -> last seq) is updated in place for monotonic
    per-stream dedupe. The structured ``components`` are rendered; ``html`` is
    ignored. A terminal frame renders its final payload (if any) and forgets the
    stream.
    """
    node, key = _node_key(frame)
    if not node:
        return []

    # Frames are chat-scoped: ignore one addressed to a different conversation.
    session = frame.get("session_id")
    if session and active_chat and session != active_chat:
        return []

    # Monotonic per-stream dedupe (drop stale/duplicate frames).
    seq = frame.get("seq")
    if isinstance(seq, int) and key is not None:
        last = seq_state.get(key)
        if last is not None and seq <= last:
            return []
        seq_state[key] = seq

    if frame.get("terminal") and key is not None:
        seq_state.pop(key, None)  # final frame: forget the stream

    err = frame.get("error")
    if isinstance(err, dict) and err:
        return [{"op": "upsert", "component_id": node, "component": _error_component(err)}]

    comps = [c for c in (frame.get("components") or []) if isinstance(c, dict)]
    if not comps:
        return []  # e.g. a bare terminal frame: leave the last node in place
    body = comps[0] if len(comps) == 1 else {"type": "container", "content": comps}
    return [{"op": "upsert", "component_id": node, "component": body}]


def subscribe_ack_ops(frame: dict) -> List[dict]:
    """A lightweight placeholder shown on ``stream_subscribed`` so the canvas
    reflects activity before the first data frame arrives (replaced in place by
    the first ``ui_stream_data`` for the same node)."""
    node, _ = _node_key(frame)
    if not node:
        return []
    tool = frame.get("tool_name") or "tool"
    return [{
        "op": "upsert",
        "component_id": node,
        "component": {"type": "text", "content": f"Streaming {tool}…"},
    }]


def stream_error_ops(frame: dict) -> List[dict]:
    """Translate a standalone ``stream_error`` control message into an alert op
    under the relevant stream node. Handles both the push shape
    (``payload.{stream_id,tool_name,code,message}``) and the legacy flat shape
    (``tool_name`` + string ``error``). Returns ``[]`` when no node can be
    resolved (the caller surfaces such errors as a status line instead)."""
    payload = frame.get("payload") or {}
    node, _ = _node_key({
        "stream_id": payload.get("stream_id"),
        "tool_name": payload.get("tool_name") or frame.get("tool_name"),
    })
    if not node:
        return []
    text = payload.get("message") or payload.get("code") or frame.get("error") or "stream error"
    return [{
        "op": "upsert",
        "component_id": node,
        "component": {"type": "alert", "variant": "error", "title": "Stream error", "message": str(text)},
    }]
