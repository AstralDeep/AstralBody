"""Feature 027 — T011: top bar + static settings menu structure and gating.

Structural invariants (not byte-exact): menu groups/entries per
contracts/settings-surfaces.md, admin DOM-absence (SC-005), ARIA menu
markup (FR-017), sign-out plain link, and modal/notice escaping.
"""
from webrender.chrome import chrome_error_block, notice_block, render_modal_shell, render_topbar


def test_topbar_has_brand_status_and_settings_trigger():
    html = render_topbar(roles=["user"])
    # Brand is the AstralDeep logo image (served from the static mount).
    assert 'src="/static/img/AstralDeep.png"' in html
    assert 'alt="AstralDeep"' in html
    assert 'data-tour-target="topbar.brand"' in html
    assert 'id="astral-status"' in html
    assert 'id="astral-settings-btn"' in html
    assert 'aria-haspopup="menu"' in html and 'aria-expanded="false"' in html
    assert 'id="astral-settings-menu"' in html and 'role="menu"' in html


def test_menu_contains_account_and_help_groups_for_everyone():
    html = render_topbar(roles=["user"])
    for label in ("Account", "Help"):
        assert label in html
    for entry in ("Agents &amp; permissions", "LLM settings", "Personalization",
                  "Audit log", "Theme", "Take the tour", "User guide", "Sign out"):
        assert entry in html, f"menu missing entry: {entry}"


def test_menu_entries_carry_chrome_open_actions():
    html = render_topbar(roles=["user"])
    assert 'data-ui-action="chrome_open"' in html
    for surface in ("agents", "llm", "personalization", "audit", "theme", "tour", "guide"):
        assert f'&quot;surface&quot;: &quot;{surface}&quot;' in html, f"missing surface payload: {surface}"


def test_workspace_timeline_promoted_to_topbar_icon():
    """Feature 045: the workspace timeline is a dedicated icon button next to
    Settings (one click back to an earlier canvas), not a Settings-menu entry."""
    html = render_topbar(roles=["user"])
    # The icon button is present, labelled, and tour-targetable.
    assert 'id="astral-timeline-btn"' in html
    assert 'aria-label="Workspace timeline"' in html
    assert 'data-tour-target="topbar.timeline"' in html
    # It fires the same chrome_open surface the menu entry used to.
    assert '&quot;surface&quot;: &quot;workspace_timeline&quot;' in html
    # It sits OUTSIDE (before) the Settings dropdown…
    assert html.index('id="astral-timeline-btn"') < html.index('id="astral-settings"')
    # …and is no longer an item inside the Settings menu.
    assert 'data-menu-key="timeline"' not in html


def test_sign_out_is_plain_link_outside_js():
    html = render_topbar(roles=["user"])
    assert 'href="/auth/logout"' in html and 'role="menuitem"' in html


def test_admin_group_present_for_admin():
    html = render_topbar(roles=["admin", "user"])
    assert "Admin tools" in html
    assert "Tool quality" in html and "Tutorial admin" in html
    assert "admin_tools" in html


def test_admin_group_dom_absent_for_non_admin():
    """SC-005: zero admin references in a non-admin's rendered output."""
    html = render_topbar(roles=["user"])
    for marker in ("Admin tools", "Tool quality", "Tutorial admin", "admin_tools"):
        assert marker not in html, f"admin marker leaked to non-admin DOM: {marker}"


def test_admin_group_dom_absent_for_empty_roles():
    html = render_topbar(roles=None)
    assert "Admin tools" not in html


def test_modal_shell_escapes_title():
    html = render_modal_shell("<script>alert(1)</script>", "<p>body</p>", "agents")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<p>body</p>" in html  # body is trusted, pre-rendered chrome output
    assert 'role="dialog"' in html and 'aria-modal="true"' in html
    assert "astral-modal-close" in html


def test_error_and_notice_blocks_escape_and_mark_roles():
    err = chrome_error_block("boom <img onerror=x>", retry_surface="agents")
    assert "<img" not in err and "&lt;img" in err
    assert 'data-ui-action="chrome_open"' in err  # retry affordance
    ok = notice_block("success", "saved <b>!</b>")
    assert "<b>" not in ok and "&lt;b&gt;" in ok
    assert 'role="status"' in ok
