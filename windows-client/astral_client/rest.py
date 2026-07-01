"""Minimal authenticated REST client for native chrome surfaces.

The desktop is WebSocket-first, but a few native chrome surfaces (the audit-log
viewer today; attachments/personalization later) read their data from the
orchestrator's REST API rather than the HTML chrome protocol. This module is the
small, dependency-free (stdlib ``urllib``) GET helper plus pure URL-building and
response-shaping helpers, so the surface dialogs stay unit-testable without a
live server.

Auth is a Bearer JWT (the same token the WebSocket registered with); all reads
are scoped server-side to that user — the audit API never accepts a user id
parameter.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import List, Optional, Tuple
from urllib.parse import urlencode

# Valid audit outcomes (mirror backend/audit/schemas.py OUTCOMES).
OUTCOMES = ("in_progress", "success", "failure", "interrupted")

# Audit event classes for the filter dropdown (mirror backend/audit/schemas.py
# EVENT_CLASSES). Kept in sync by hand — drift is low-risk: a missing class just
# can't be filtered from the dropdown, and an unknown one is rejected server-side
# (400) and surfaced as an error rather than silently mis-scoping a read.
EVENT_CLASSES = (
    "auth", "conversation", "file", "settings", "agent_tool_call",
    "agent_ui_render", "agent_external_call", "audit_view",
    "component_feedback", "tool_quality", "proposal_review", "quarantine",
    "onboarding_started", "onboarding_completed", "onboarding_skipped",
    "onboarding_replayed", "tutorial_step_edited",
    "llm_config_change", "llm_unconfigured", "llm_call",
    "personalization", "memory", "skill", "schedule", "dreaming",
    "agent_lifecycle",
)


class RestError(Exception):
    """An HTTP/transport failure from a REST call (status 0 == transport error)."""

    def __init__(self, status: int, message: str):
        super().__init__(f"{status or 'network'}: {message}")
        self.status = status
        self.message = message


def audit_url(
    http_base: str,
    *,
    limit: int = 50,
    event_class: str = "",
    outcome: str = "",
    q: str = "",
    cursor: str = "",
) -> str:
    """Build the ``GET /api/audit`` URL, including only the active filters."""
    params: List[Tuple[str, str]] = [("limit", str(limit))]
    if event_class:
        params.append(("event_class", event_class))
    if outcome:
        params.append(("outcome", outcome))
    if q:
        params.append(("q", q))
    if cursor:
        params.append(("cursor", cursor))
    return f"{http_base.rstrip('/')}/api/audit?{urlencode(params)}"


def chrome_menu_url(http_base: str) -> str:
    """Build the ``GET /api/chrome/menu`` URL (REST fallback; the model also
    arrives over the ``chrome_menu`` WS frame after register)."""
    return f"{http_base.rstrip('/')}/api/chrome/menu"


def parse_chrome_menu(model: dict) -> dict:
    """Normalize a feature-042 chrome model into the structure the native top bar
    renders (single server-owned source of truth — Constitution XII):

    ``{"sections": [{"label", "items": [{"label", "surface", "params"}]}],
       "topbar_actions": [{"label", "surface", "icon"}],
       "signout": {"label", "action"}}``

    Pure + defensive so the desktop menu builder stays unit-testable and an older
    client tolerates an unknown/newer model rather than crashing.
    """
    model = model or {}
    sections: List[dict] = []
    for g in (model.get("menu") or []):
        items = [
            {"label": str(i.get("label") or ""), "surface": str(i.get("surface") or ""),
             "params": i.get("params") or {}}
            for i in (g.get("items") or [])
            if isinstance(i, dict) and i.get("surface")
        ]
        if items:
            sections.append({"label": str(g.get("label") or ""), "items": items})
    topbar_actions: List[dict] = []
    for c in (model.get("topbar") or []):
        if not isinstance(c, dict) or c.get("kind") != "action":
            continue
        surface = str((c.get("action") or {}).get("surface") or "")
        if surface:
            topbar_actions.append(
                {"label": str(c.get("label") or ""), "surface": surface, "icon": str(c.get("icon") or "")}
            )
    so = model.get("signout") or {}
    signout = {"label": str(so.get("label") or "Sign out"), "action": str(so.get("action") or "logout")}
    return {"sections": sections, "topbar_actions": topbar_actions, "signout": signout}


def _fmt_ts(value) -> str:
    """ISO-8601 timestamp -> ``YYYY-MM-DD HH:MM:SS`` for display (best-effort)."""
    if not value:
        return "-"
    s = str(value).replace("T", " ")
    return s[:19] if len(s) >= 19 else s


def parse_audit_response(data: dict) -> Tuple[List[dict], Optional[str]]:
    """Shape an ``AuditListResponse`` into ``(rows, next_cursor)``.

    Each row is a flat dict of the columns the viewer shows, defensive against
    missing keys / malformed items.
    """
    rows: List[dict] = []
    for it in (data.get("items") or []):
        if not isinstance(it, dict):
            continue
        rows.append({
            "event_id": str(it.get("event_id") or ""),
            "recorded_at": _fmt_ts(it.get("recorded_at")),
            "event_class": str(it.get("event_class") or ""),
            "action_type": str(it.get("action_type") or ""),
            "outcome": str(it.get("outcome") or ""),
            "description": str(it.get("description") or ""),
        })
    return rows, (data.get("next_cursor") or None)


def fetch_json(url: str, token: str, *, timeout: int = 20, opener=urllib.request.urlopen) -> dict:
    """Authenticated GET returning parsed JSON. Raises :class:`RestError` on any
    HTTP or transport error. ``opener`` is injectable for tests."""
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    })
    try:
        with opener(req, timeout=timeout) as r:
            raw = r.read(4 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        raise RestError(exc.code, exc.reason or "HTTP error")
    except Exception as exc:  # noqa: BLE001 — transport failure, surfaced to the UI
        raise RestError(0, str(exc))
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, TypeError) as exc:
        raise RestError(0, f"bad JSON: {exc}")


def fetch_bytes(url: str, token: str, *, timeout: int = 60, opener=urllib.request.urlopen) -> bytes:
    """Authenticated GET returning the raw response bytes (for file downloads,
    e.g. ``GET /api/download/{session}/{file}``). Raises :class:`RestError` on any
    HTTP or transport error. ``opener`` is injectable for tests."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with opener(req, timeout=timeout) as r:
            return r.read(64 * 1024 * 1024)  # 64 MB safety cap
    except urllib.error.HTTPError as exc:
        raise RestError(exc.code, exc.reason or "HTTP error")
    except Exception as exc:  # noqa: BLE001 — transport failure, surfaced to the UI
        raise RestError(0, str(exc))
