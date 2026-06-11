"""Feature 027 — T018: ``guide`` surface (User guide) structure and gating.

Structural invariants (not byte-exact): module contract, full section
inventory ported from the former React UserGuidePanel, TOC navigation via
``chrome_open``, default/fallback section selection, admin-only section
gating, and escape-by-default content (no DB required — the guide is
static content, so ``orch`` is never touched).
"""
import asyncio
import inspect

from webrender.chrome import guide_content
from webrender.chrome.surfaces import guide

EXPECTED_SLUGS = [
    "intro", "signing-in", "dashboard", "chat", "attachments", "voice",
    "agents", "components", "feedback", "audit", "tutorial", "tooltips",
    "preferences", "device", "privacy", "admin",
]


def _render(roles=("user",), params=None):
    """Run the async surface render with a None orch (static content)."""
    return asyncio.run(guide.render(None, "user-1", list(roles), params or {}))


# ── module contract ─────────────────────────────────────────────────────────

def test_module_contract():
    assert guide.TITLE == "User guide"
    assert not getattr(guide, "ADMIN_ONLY", False)
    assert inspect.iscoroutinefunction(guide.render)
    # Navigation rides chrome_open via the dispatcher — no surface handlers.
    assert not getattr(guide, "HANDLERS", {})


# ── guide_content inventory ─────────────────────────────────────────────────

def test_sections_cover_full_react_panel_inventory_in_order():
    slugs = [s["slug"] for s in guide_content.SECTIONS]
    assert slugs == EXPECTED_SLUGS


def test_sections_are_well_formed():
    seen = set()
    for s in guide_content.SECTIONS:
        assert s["slug"] and isinstance(s["slug"], str)
        assert s["title"] and isinstance(s["title"], str)
        assert s["body_html"] and isinstance(s["body_html"], str)
        assert "<h1" in s["body_html"], f"section {s['slug']} missing heading"
        assert s["slug"] not in seen, f"duplicate slug {s['slug']}"
        seen.add(s["slug"])


def test_only_admin_section_is_admin_only():
    flags = {s["slug"]: bool(s.get("admin_only")) for s in guide_content.SECTIONS}
    assert flags.pop("admin") is True
    assert not any(flags.values())


def test_body_html_escapes_text_literals():
    """Escape-by-default: ampersands/quotes in literals come out entity-encoded."""
    by_slug = {s["slug"]: s["body_html"] for s in guide_content.SECTIONS}
    assert "Combine &amp; condense" in by_slug["components"]
    assert "&quot;summarise this PDF&quot;" in by_slug["chat"]
    # apostrophes pass through esc() (html.escape quote=True → &#x27;)
    assert "you&#x27;ll" in by_slug["intro"]
    assert "<script" not in "".join(by_slug.values())


# ── render: TOC + selection ─────────────────────────────────────────────────

def test_default_render_selects_first_section_and_lists_full_toc():
    html = _render()
    assert "Welcome to AstralBody" in html  # first section article
    assert 'aria-label="User guide sections"' in html
    assert 'data-ui-action="chrome_open"' in html
    for slug in EXPECTED_SLUGS[:-1]:  # admin entry gated for plain users
        assert f"&quot;section&quot;: &quot;{slug}&quot;" in html, f"TOC missing {slug}"
    assert "&quot;surface&quot;: &quot;guide&quot;" in html


def test_section_param_selects_article_and_marks_toc_active():
    html = _render(params={"section": "audit"})
    assert "Your audit log" in html
    assert "append-only and signed" in html
    assert "Welcome to AstralBody" not in html  # only the selected article renders
    assert 'aria-current="true"' in html
    # exactly one active TOC entry
    assert html.count('aria-current="true"') == 1


def test_unknown_section_falls_back_to_first():
    html = _render(params={"section": "definitely-not-a-section"})
    assert "Welcome to AstralBody" in html


def test_none_params_tolerated():
    html = asyncio.run(guide.render(None, "user-1", ["user"], None))
    assert "Welcome to AstralBody" in html


def test_every_visible_section_renders_when_requested():
    for s in guide_content.SECTIONS:
        html = _render(roles=("admin", "user"), params={"section": s["slug"]})
        assert s["body_html"] in html, f"section {s['slug']} did not render"


# ── admin gating ────────────────────────────────────────────────────────────

def test_admin_section_absent_for_non_admin():
    html = _render(roles=("user",))
    assert "For administrators" not in html
    assert "&quot;section&quot;: &quot;admin&quot;" not in html


def test_admin_section_request_by_non_admin_falls_back():
    html = _render(roles=("user",), params={"section": "admin"})
    assert "operator-only operations" not in html  # admin body marker
    assert "Welcome to AstralBody" in html


def test_admin_section_present_for_admin():
    html = _render(roles=("admin", "user"))
    assert "For administrators" in html  # TOC entry
    detail = _render(roles=("admin", "user"), params={"section": "admin"})
    assert "operator-only operations" in detail


# ── escaping in the rendered shell body ─────────────────────────────────────

def test_toc_titles_are_escaped():
    html = _render()
    assert "Attachments &amp; files" in html
    assert "Attachments & files</button>" not in html
