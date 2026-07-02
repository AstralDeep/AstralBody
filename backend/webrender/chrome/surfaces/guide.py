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
import html as _html
import json
import re

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


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def _html_to_text(body_html: str) -> str:
    """Best-effort plain text from a guide section's HTML (native has no HTML).

    Block ends become paragraph breaks and ``<li>`` becomes a bullet, then tags
    are stripped and entities unescaped. First-pass port — richer structure can
    follow if ``guide_content`` gains a structured representation.
    """
    s = re.sub(r"(?i)<li[^>]*>", "\n• ", body_html or "")
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|li|h[1-6]|section|article|ul|ol)>", "\n\n", s)
    s = _html.unescape(_TAG_RE.sub("", s))
    lines = [_WS_RE.sub(" ", ln).strip() for ln in s.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


async def components(orch, user_id, roles, params):
    """Feature 043 — the User-guide surface as native SDUI components.

    A TOC of ``chrome_open`` buttons (re-open with a ``section`` param, exactly
    like the web) + the selected section's title and body (HTML flattened to
    text paragraphs). Admin-only sections are filtered exactly as ``render()``.
    """
    from webrender.chrome.surfaces import _sdui
    sections = _visible_sections(roles)
    requested = str((params or {}).get("section") or "")
    selected = next((s for s in sections if s["slug"] == requested), sections[0])
    toc = [
        _sdui.button(
            s["title"], "chrome_open",
            {"surface": "guide", "params": {"section": s["slug"]}},
            variant="primary" if s["slug"] == selected["slug"] else "secondary")
        for s in sections
    ]
    paras = [p for p in _html_to_text(selected["body_html"]).split("\n\n") if p.strip()]
    # CONTENT FIRST, TOC after: on a native (phone-height) surface the 13+
    # section buttons pushed the section body far below the fold, so tapping a
    # section looked like a dead button — the newly delivered content was
    # invisible. Leading with the selected section's title + body (the client
    # scrolls each delivery to the top) makes every TOC tap visibly navigate;
    # the web modal keeps its own layout (render() is unchanged).
    out = [_sdui.text(selected["title"], "h2")]
    out.extend(_sdui.text(p, "body") for p in (paras or ["…"]))
    out.append(_sdui.text("Sections", "h3"))
    out.append(_sdui.container(toc, direction="column"))
    return out
