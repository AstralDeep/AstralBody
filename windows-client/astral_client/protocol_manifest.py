"""Frame classification for the desktop client (feature 044).

Every server->client WS frame type in the committed UI-protocol manifest
(``backend/shared/ui_protocol.json``) is classified here as either

* ``"handled"`` — the client routes it in ``MainWindow._on_message``; or
* ``"ignored"`` — a deliberate, logged drop (the frame carries nothing the
  desktop presents natively; the parity matrix records why).

There is no third state. ``tests/test_protocol_manifest.py`` asserts this table
covers the manifest exactly, so a new server frame type fails the build until it
is classified — never a silent drop (FR-001/FR-002/FR-023).
"""

from __future__ import annotations

HANDLED = "handled"
IGNORED = "ignored"

CLASSIFICATION: dict[str, str] = {
    # bootstrap
    "rote_config": IGNORED,           # natives are full-capability; profile unused
    "chrome_menu": HANDLED,
    "user_preferences": HANDLED,      # theme boot (044)
    "system_config": IGNORED,         # web dashboard payload; desktop uses agent_list
    "agent_list": HANDLED,
    "agent_registered": IGNORED,      # discovery refresh follows via agent_list
    # auth
    "auth_required": HANDLED,
    # canvas / SDUI
    "ui_render": HANDLED,
    "ui_update": IGNORED,             # legacy frame; server no longer targets natives
    "ui_upsert": HANDLED,
    "ui_append": IGNORED,             # legacy frame
    "ui_stream_data": HANDLED,
    # chrome
    "chrome_render": HANDLED,         # web HTML region push -> status notice only
    "chrome_surface": HANDLED,
    # chat lifecycle / progress
    "chat_status": HANDLED,
    "chat_step": HANDLED,
    "chat_created": HANDLED,
    "chat_loaded": HANDLED,
    "chat_deleted": IGNORED,          # cross-tab concern; desktop is single-window
    "history_list": HANDLED,
    "user_message_acked": HANDLED,
    "task_started": HANDLED,
    "task_completed": HANDLED,
    "tool_progress": HANDLED,
    "workspace_timeline_mode": HANDLED,
    "heartbeat": IGNORED,             # transport keepalive
    # streaming
    "stream_subscribed": HANDLED,
    "stream_unsubscribed": HANDLED,
    "stream_list": IGNORED,           # no desktop surface enumerates streams
    "stream_data": HANDLED,
    "stream_error": HANDLED,
    # workspace component verbs (web workspace acks; desktop canvas is ui_* driven)
    "component_saved": IGNORED,
    "component_save_error": IGNORED,
    "saved_components_list": IGNORED,
    "component_deleted": IGNORED,
    "combine_status": IGNORED,
    "combine_error": IGNORED,
    "components_combined": IGNORED,
    "components_condensed": IGNORED,
    # permissions (capability lives in the native Agents dialog via agent_list)
    "agent_permissions": IGNORED,
    "agent_permissions_updated": IGNORED,
    # llm (desktop uses the LLM settings surface round-trip)
    "llm_config_ack": IGNORED,
    "llm_usage_report": IGNORED,
    # audit (desktop fetches audit via REST)
    "audit_append": IGNORED,
    # creation (draft cards carry state in-chat)
    "agent_creation_progress": IGNORED,
    # scheduler notifications + errors (044)
    "notification": HANDLED,
    "error": HANDLED,
}


def is_handled(frame_type: str) -> bool:
    return CLASSIFICATION.get(frame_type) == HANDLED


def is_classified(frame_type: str) -> bool:
    return frame_type in CLASSIFICATION
