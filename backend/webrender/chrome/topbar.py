"""Feature 027 — top bar + static settings menu (server-rendered, role-gated).

Rendered into the shell at ``GET /`` so the menu is *static*: always present,
opens with zero server round-trip (spec A2/FR-012). Group/entry inventory per
contracts/settings-surfaces.md; the Admin tools group is rendered ONLY when
the session roles include ``admin`` — absent from the DOM for everyone else
(FR-014; UX-only gating, server-side checks stay authoritative). Entries
whose availability rule fails are omitted; empty groups hide their heading
(FR-019).

Menu markup follows the WAI-ARIA menu pattern (FR-017); the keyboard and
open/close behavior lives in ``webrender/static/client.js``.
"""
import json

from webrender import esc

_GEAR_SVG = (
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 '
    '0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 '
    '1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 '
    '1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 '
    '1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 '
    '0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 '
    '2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 '
    '0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 '
    '2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>'
)

# Feature 045 — "history" glyph (clock + counter-clockwise arrow) for the
# top-bar Workspace-timeline button: a recognizable "go back to an earlier
# version" affordance sitting right next to Settings.
_HISTORY_SVG = (
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>'
    '<path d="M3 3v5h5"/><path d="M12 7v5l4 2"/></svg>'
)

# chrome_open payload for the top-bar timeline button (the client injects the
# active chat id into params at click time — see client.js).
_TIMELINE_PAYLOAD = json.dumps({"surface": "workspace_timeline", "params": {}})


def _menu_entries(roles):
    """Grouped (label, entries) menu inventory, role/availability filtered.

    Each entry: (key, label, surface, params) — ``surface=None`` marks the
    sign-out link. Availability rules: all Account/Help entries are backed by
    unconditional backends; Admin tools requires the admin role (FR-014).
    """
    groups = [
        ("Account", [
            ("agents", "Agents & permissions", "agents", {}),
            ("llm", "LLM settings", "llm", {}),
            ("personalization", "Personalization", "personalization", {}),
            ("audit", "Audit log", "audit", {}),
            ("theme", "Theme", "theme", {}),
            # Feature 028's workspace timeline used to live here; feature 045
            # promoted it to a dedicated top-bar icon (see render_topbar) so
            # returning to an earlier canvas is one click, not buried in a menu.
        ]),
        ("Help", [
            ("tour", "Take the tour", "tour", {}),
            ("guide", "User guide", "guide", {}),
        ]),
    ]
    if "admin" in (roles or []):
        groups.append(("Admin tools", [
            ("tool-quality", "Tool quality", "admin_tools", {"tab": "quality"}),
            ("tutorial-admin", "Tutorial admin", "admin_tools", {"tab": "tutorial"}),
        ]))
    # FR-019: drop empty groups (defensive — none are empty today).
    return [(label, entries) for label, entries in groups if entries]


def _menu_html(roles):
    items = []
    for label, entries in _menu_entries(roles):
        items.append(
            f'<div class="px-3 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider '
            f'text-astral-muted" role="presentation">{esc(label)}</div>'
        )
        for key, text, surface, params in entries:
            payload = json.dumps({"surface": surface, "params": params})
            items.append(
                f'<button type="button" role="menuitem" tabindex="-1" '
                f'class="astral-menu-item w-full text-left px-3 py-2 text-sm text-astral-text '
                f'hover:bg-white/5 focus:bg-white/10 focus:outline-none rounded-lg" '
                f'data-menu-key="{esc(key)}" data-tour-target="sidebar.{esc(key)}" '
                f"data-ui-action=\"chrome_open\" data-ui-payload='{esc(payload)}'>{esc(text)}</button>"
            )
    # Session group — Sign out is a plain link so it works without JS
    # (feature 016 semantics live behind GET /auth/logout).
    items.append(
        '<div class="border-t border-white/5 mt-1 pt-1" role="presentation"></div>'
        '<a href="/auth/logout" role="menuitem" tabindex="-1" '
        'class="astral-menu-item block px-3 py-2 text-sm text-red-400 hover:bg-white/5 '
        'focus:bg-white/10 focus:outline-none rounded-lg" data-menu-key="signout">Sign out</a>'
    )
    return "".join(items)


def render_topbar(roles=None) -> str:
    """Inner HTML for ``<header id="astral-topbar">`` — brand, status, Settings.

    Targets the web client only. ``roles`` comes from the server session at
    shell-render time (mock auth ⇒ admin) — see ``web_auth.session_roles``.
    """
    return (
        '<div class="flex items-center justify-between px-4 py-3 w-full">'
        '<div class="flex items-center gap-2" data-tour-target="topbar.brand">'
        '<img src="/static/img/AstralDeep.png" alt="AstralDeep" '
        'class="h-8 w-auto select-none" draggable="false"></div>'
        '<div class="flex items-center gap-3">'
        '<span id="astral-status" class="text-xs text-astral-muted" role="status"></span>'
        # Feature 045 — Workspace-timeline icon next to Settings. Reuses the
        # generic `chrome_open` delegation (client.js injects the active chat
        # id into params at click time), so no new client wiring is needed.
        '<button type="button" id="astral-timeline-btn" data-tour-target="topbar.timeline" '
        'class="flex items-center justify-center p-1.5 rounded-lg text-astral-muted '
        'hover:text-astral-text hover:bg-white/5" aria-label="Workspace timeline" '
        'title="Workspace timeline — revisit an earlier version of this canvas" '
        'data-ui-action="chrome_open" '
        f"data-ui-payload='{esc(_TIMELINE_PAYLOAD)}'>{_HISTORY_SVG}</button>"
        '<div class="relative" id="astral-settings">'
        '<button type="button" id="astral-settings-btn" data-tour-target="topbar.settings" '
        'class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm text-astral-muted '
        'hover:text-astral-text hover:bg-white/5" aria-haspopup="menu" aria-expanded="false" '
        f'aria-controls="astral-settings-menu" aria-label="Settings">{_GEAR_SVG}'
        '<span class="hidden sm:inline">Settings</span></button>'
        '<div id="astral-settings-menu" role="menu" aria-label="Settings" hidden '
        'class="absolute right-0 mt-2 w-64 max-h-[70vh] overflow-y-auto rounded-xl border '
        'border-white/10 bg-astral-surface shadow-2xl p-1.5 z-50">'
        f"{_menu_html(roles)}</div></div></div></div>"
    )
