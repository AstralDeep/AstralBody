"""Feature 027 — T016: Theme surface structural/behavioral tests.

Runs without Postgres: a minimal fake ``orch`` exposes only
``orch.history.db.{get,set}_user_preferences`` (the only internals the
surface touches — same calls as the ``save_theme`` WS handler).
"""
import asyncio

from webrender.chrome.surfaces import theme as theme_surface


class FakeDB:
    """In-memory stand-in for the user_preferences DB helpers."""

    def __init__(self, prefs=None, fail_on_set=False):
        self.prefs = dict(prefs or {})
        self.fail_on_set = fail_on_set
        self.set_calls = []

    def get_user_preferences(self, user_id):
        return dict(self.prefs)

    def set_user_preferences(self, user_id, preferences):
        if self.fail_on_set:
            raise RuntimeError("db down")
        self.set_calls.append((user_id, preferences))
        self.prefs = {**self.prefs, **preferences}  # same top-level merge as shared.database


class FakeHistory:
    def __init__(self, db):
        self.db = db


class FakeOrch:
    def __init__(self, prefs=None, fail_on_set=False):
        self.history = FakeHistory(FakeDB(prefs, fail_on_set))


def render(orch, params=None):
    return asyncio.run(theme_surface.render(orch, "user-1", ["user"], params or {}))


def handle(orch, payload):
    return asyncio.run(theme_surface.HANDLERS["chrome_theme_preset"](
        orch, None, "user-1", ["user"], payload))


# ---------------------------------------------------------------------------
# Module contract
# ---------------------------------------------------------------------------

def test_module_contract():
    assert theme_surface.TITLE == "Theme"
    assert not getattr(theme_surface, "ADMIN_ONLY", False)
    assert set(theme_surface.HANDLERS) == {"chrome_theme_preset"}


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def test_render_has_all_preset_cards_with_action_and_swatches():
    html = render(FakeOrch())
    assert html.count('data-ui-action="chrome_theme_preset"') == 5
    for name in ("midnight", "daylight", "ocean", "sunset", "forest"):
        assert f"&quot;preset&quot;: &quot;{name}&quot;" in html, f"missing payload for {name}"
        assert name.capitalize() in html
    # swatch strips carry the server-side hex map (spot-check per preset)
    for hexval in ("#0F1221", "#F8FAFC", "#0EA5E9", "#F97316", "#22C55E"):
        assert f"background:{hexval}" in html


def test_render_embeds_seven_color_pickers_with_midnight_defaults():
    html = render(FakeOrch())
    assert html.count("astral-color-picker") == 7
    for key in ("bg", "surface", "primary", "secondary", "text", "muted", "accent"):
        assert f'data-color-key="{key}"' in html
    assert 'value="#0F1221"' in html  # bg default (midnight)
    assert 'value="#06B6D4"' in html  # accent default (midnight)
    assert "Current theme: default (Midnight)." in html


def test_render_reflects_persisted_preset():
    html = render(FakeOrch(prefs={"theme": {"preset": "ocean"}}))
    assert "Current theme: Ocean preset (saved)." in html
    assert 'aria-pressed="true"' in html and html.count('aria-pressed="true"') == 1
    assert ">Active</span>" in html
    assert 'value="#0C1222"' in html  # pickers show the ocean palette
    assert 'value="#2DD4BF"' in html


def test_render_overlays_single_custom_color_on_defaults():
    html = render(FakeOrch(prefs={"theme": {"color_key": "primary", "color_value": "#ABCDEF"}}))
    assert 'value="#ABCDEF"' in html
    assert 'value="#0F1221"' in html  # other keys keep midnight defaults
    assert "custom colors" in html
    assert 'aria-pressed="true"' not in html  # no preset active


def test_render_overlays_colors_map_and_ignores_invalid_hex():
    prefs = {"theme": {"colors": {"bg": "112233", "accent": "<script>alert(1)</script>"}}}
    html = render(FakeOrch(prefs=prefs))
    assert 'value="#112233"' in html  # normalized with leading '#'
    assert "<script>" not in html  # invalid hex dropped, nothing unescaped
    assert 'value="#06B6D4"' in html  # accent fell back to default


def test_render_tolerates_db_failure_and_bad_theme_shape():
    class BoomDB(FakeDB):
        def get_user_preferences(self, user_id):
            raise RuntimeError("db down")

    orch = FakeOrch()
    orch.history.db = BoomDB()
    html = render(orch)  # must not raise — defaults shown
    assert "Current theme: default (Midnight)." in html

    html2 = render(FakeOrch(prefs={"theme": "not-a-dict"}))
    assert "Current theme: default (Midnight)." in html2


# ---------------------------------------------------------------------------
# chrome_theme_preset handler
# ---------------------------------------------------------------------------

def test_preset_save_persists_like_save_theme_and_applies_instantly():
    orch = FakeOrch()
    surface, params, notice = handle(orch, {"preset": "ocean"})
    assert surface == "theme" and params == {}
    assert orch.history.db.set_calls == [("user-1", {"theme": {"preset": "ocean"}})]
    # success notice (explicit-save contract) ...
    assert "astral-chrome-notice" in notice and "Ocean theme saved." in notice
    # ... plus a rendered theme_apply block so processSideEffects sets CSS vars
    assert "astral-theme-apply" in notice
    assert "&quot;preset&quot;: &quot;ocean&quot;" in notice
    assert "Theme applied" in notice


def test_unknown_preset_is_error_notice_without_save():
    orch = FakeOrch()
    surface, params, notice = handle(orch, {"preset": "<neon>"})
    assert surface == "theme"
    assert orch.history.db.set_calls == []
    assert "bg-red-500/10" in notice
    assert "&lt;neon&gt;" in notice and "<neon>" not in notice  # escaped
    assert "astral-theme-apply" not in notice


def test_missing_preset_is_error_notice():
    orch = FakeOrch()
    surface, _params, notice = handle(orch, {})
    assert surface == "theme"
    assert "Unknown theme preset" in notice
    assert orch.history.db.set_calls == []


def test_db_failure_returns_error_notice_not_exception():
    orch = FakeOrch(fail_on_set=True)
    surface, _params, notice = handle(orch, {"preset": "forest"})
    assert surface == "theme"
    assert "Failed to save theme" in notice and "bg-red-500/10" in notice
    assert "astral-theme-apply" not in notice
