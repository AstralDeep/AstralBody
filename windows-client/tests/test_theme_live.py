"""Feature 044 (T049) — live theming.

The palette is mutable and the stylesheet rebuildable: `apply_theme` mutates the
active PALETTE from a preset / colors map / single channel, `build_stylesheet`
re-renders the QSS, and the `color_picker` primitive is interactive (emits
`save_theme` + applies locally). The five presets mirror the backend.
"""
import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import astral_client.theme as T  # noqa: E402
from astral_client import renderer as rmod  # noqa: E402
from astral_client.renderer import RenderContext, render  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_theme():
    """Snapshot + restore the module-level palette so a test's theme change does
    not leak into the shared qapp session."""
    snap = dict(T.PALETTE)
    yield
    T.PALETTE.clear()
    T.PALETTE.update(snap)
    T._derive()
    T.APP_STYLESHEET = T.build_stylesheet()


def test_build_stylesheet_nonempty_contains_palette():
    s = T.build_stylesheet()
    assert isinstance(s, str) and len(s) > 100
    assert T.PRIMARY in s          # palette colors appear in the QSS
    assert T.TEXT in s
    assert T.SURFACE_2 in s


def test_apply_preset_changes_palette_and_stylesheet():
    before = T.build_stylesheet()
    assert T.apply_theme("daylight") is True
    assert T.PALETTE["bg"] == T.PRESETS["daylight"]["bg"]
    assert T.PRIMARY == T.PRESETS["daylight"]["primary"]
    assert T.build_stylesheet() != before
    # idempotent — re-applying the same preset changes nothing
    assert T.apply_theme("daylight") is False


def test_apply_preset_via_dict():
    assert T.apply_theme({"preset": "ocean"}) is True
    assert T.PALETTE["primary"] == T.PRESETS["ocean"]["primary"]


def test_apply_colors_map():
    assert T.apply_theme({"colors": {"primary": "#123456", "text": "#ABCDEF"}}) is True
    assert T.PALETTE["primary"] == "#123456"
    assert T.PRIMARY == "#123456"
    assert "#123456" in T.build_stylesheet()


def test_apply_single_color_key():
    assert T.apply_theme({"color_key": "accent", "color_value": "#FF8800"}) is True
    assert T.PALETTE["accent"] == "#FF8800"
    assert T.ACCENT == "#FF8800"


def test_apply_string_preset_shorthand():
    assert T.apply_theme("sunset") is True
    assert T.PALETTE["bg"] == T.PRESETS["sunset"]["bg"]


def test_no_op_specs_return_false():
    assert T.apply_theme("does-not-exist") is False
    assert T.apply_theme({"color_key": "primary", "color_value": "nothex"}) is False
    assert T.apply_theme({}) is False
    assert T.apply_theme(None) is False


def test_five_presets_seven_channels():
    assert set(T.PRESETS) == {"midnight", "daylight", "ocean", "sunset", "forest"}
    for chans in T.PRESETS.values():
        assert set(chans) == {"bg", "surface", "primary", "secondary",
                              "text", "muted", "accent"}


def test_color_picker_renders(qapp):
    from PySide6.QtWidgets import QWidget

    w = render({"type": "color_picker", "color_key": "primary",
                "value": "#6366F1", "label": "Primary"},
               RenderContext(emit=lambda *a: None))
    assert isinstance(w, QWidget)


def test_color_picker_emits_save_theme_and_applies(qapp, monkeypatch):
    from PySide6.QtWidgets import QPushButton

    # Stub the modal colour chooser so the emit path is drivable headlessly.
    monkeypatch.setattr(rmod, "_choose_color", lambda *a, **k: "#FF8800")
    seen = []
    ctx = RenderContext(emit=lambda a, p: seen.append((a, p)))
    w = render({"type": "color_picker", "color_key": "accent",
                "value": "#06B6D4", "label": "Accent"}, ctx)
    w.findChild(QPushButton).click()
    assert seen[-1][0] == "save_theme"
    assert seen[-1][1]["theme"] == {"color_key": "accent", "color_value": "#FF8800"}
    # applied locally too
    assert T.PALETTE["accent"] == "#FF8800"


def test_color_picker_cancel_emits_nothing(qapp, monkeypatch):
    from PySide6.QtWidgets import QPushButton

    monkeypatch.setattr(rmod, "_choose_color", lambda *a, **k: None)  # cancelled
    seen = []
    w = render({"type": "color_picker", "color_key": "primary", "value": "#6366F1"},
               RenderContext(emit=lambda a, p: seen.append((a, p))))
    w.findChild(QPushButton).click()
    assert seen == []


def test_theme_apply_component_applies_live(qapp):
    render({"type": "theme_apply", "preset": "forest", "message": "applied"},
           RenderContext(emit=lambda *a: None))
    assert T.PALETTE["primary"] == T.PRESETS["forest"]["primary"]
