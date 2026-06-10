"""Feature 027 — ``guide`` settings surface (User guide).

Static reference content ported from the former React ``UserGuidePanel``
(see ``webrender/chrome/guide_content.py``). The surface renders a left
table of contents plus the selected section's article; section navigation
re-opens the same surface via ``chrome_open {surface: "guide", params:
{section}}`` so the dispatcher handles routing — no surface-local HANDLERS
are needed.

The admin-only section is filtered server-side from both the TOC and the
selectable bodies for non-admin sessions (FR-014 spirit; parity with the
panel's ``adminOnly`` gating).
"""
import json

from webrender.chrome import esc
from webrender.chrome.guide_content import SECTIONS

TITLE = "User guide"

_TOC_BASE_CLS = (
    "astral-guide-toc-item w-full text-left px-2 py-1.5 rounded-md text-xs "
    "focus:outline-none focus:bg-white/10"
)
_TOC_ACTIVE_CLS = "bg-astral-primary/15 text-astral-text"
_TOC_IDLE_CLS = "text-astral-muted hover:text-astral-text hover:bg-white/5"


def _visible_sections(roles):
    """Sections visible to this session (admin-only entries role-gated).

    Args:
        roles: Session roles (may be None).

    Returns:
        Ordered list of section dicts from ``guide_content.SECTIONS``.
    """
    is_admin = "admin" in (roles or [])
    return [s for s in SECTIONS if not s.get("admin_only") or is_admin]


def _toc_button(section, active: bool) -> str:
    """One TOC entry — a ``chrome_open`` button targeting this surface."""
    payload = json.dumps({"surface": "guide", "params": {"section": section["slug"]}})
    state_cls = _TOC_ACTIVE_CLS if active else _TOC_IDLE_CLS
    aria = ' aria-current="true"' if active else ""
    title = esc(section["title"])
    return (
        f'<button type="button" class="{_TOC_BASE_CLS} {state_cls}"{aria} '
        f"data-ui-action=\"chrome_open\" data-ui-payload='{esc(payload)}'>{title}</button>"
    )


async def render(orch, user_id, roles, params) -> str:
    """Render the User-guide body: left TOC + the selected section article.

    Args:
        orch: Orchestrator instance (unused — the guide is static content).
        user_id: Requesting user id (unused).
        roles: Session roles; gates the admin-only section.
        params: Optional ``{"section": slug}``; unknown/absent slugs fall
            back to the first visible section.

    Returns:
        Surface body HTML (the dispatcher wraps it in the modal shell).
    """
    sections = _visible_sections(roles)
    requested = str((params or {}).get("section") or "")
    selected = next((s for s in sections if s["slug"] == requested), sections[0])
    toc = "".join(_toc_button(s, s["slug"] == selected["slug"]) for s in sections)
    # body_html is trusted, already-escaped content from guide_content
    # (every text literal passed through esc() at module build time).
    body = selected["body_html"]
    return (
        '<div class="astral-guide flex flex-col sm:flex-row gap-4 items-start">'
        '<nav class="astral-guide-toc w-full sm:w-44 flex-shrink-0 space-y-0.5 '
        'sm:border-r sm:border-white/5 sm:pr-3" aria-label="User guide sections">'
        f"{toc}</nav>"
        f'<article class="astral-guide-article flex-1 min-w-0">{body}</article>'
        "</div>"
    )
