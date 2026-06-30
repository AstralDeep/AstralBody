"""Native app-chrome helpers for the Windows client.

The orchestrator pushes app-chrome (settings, agent management, modals — Feature
027) to the **web** shell as server-rendered HTML via ``chrome_render``
({region, html, mode}). This client is 100% native (no embedded web view), so it
never injects that HTML. Instead the desktop reimplements chrome as Qt widgets
(the Agents and History dialogs today) driven by the orchestrator's *data*
actions/REST — NOT the HTML chrome protocol:

  agents          -> discover_agents / set_agent_permissions / enable_recommended_agents (WS)
  history / chat  -> get_history / load_chat (WS)
  llm             -> llm_config_set / llm_config_clear (WS) + /api/llm/* (REST)
  audit           -> /api/audit (REST) + audit_append (push)
  personalization -> /api/personalization, /api/memory, /api/skills, /api/schedule, /api/dreaming (REST)
  theme           -> save_theme (WS) + user_preferences (push)
  attachments     -> /api/attachments (REST)
  drafts          -> draft_approve/refine/discard, revision_apply/discard (WS)

This module currently provides the ``chrome_render`` safety-net (so a pushed
modal is acknowledged rather than silently dropped) and is the home for the
native data-driven surface builders as they land. Pure (no Qt) so it stays
unit-testable.
"""
from __future__ import annotations

from typing import Optional


def chrome_render_notice(frame: dict) -> Optional[str]:
    """Decide how to handle a server-pushed ``chrome_render`` frame natively.

    Returns a short status string to surface (so the frame is acknowledged
    rather than silently dropped), or ``None`` to ignore it:

    - ``region != "modal"`` -> ignore (the topbar is rendered once at page load
      on the web and is never pushed in production).
    - empty ``html`` -> ignore (an empty modal body is the *close* signal).
    - a modal with HTML body -> a notice, since this native client cannot render
      the web shell's HTML; the data-driven native surfaces are the parity path.
    """
    if (frame.get("region") or "modal") != "modal":
        return None
    if not str(frame.get("html") or "").strip():
        return None
    return "This settings panel isn't available in the desktop app yet"
