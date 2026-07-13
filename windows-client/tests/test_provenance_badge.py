"""Feature 055 (US4, T036) — native provenance badge.

The server stamps every delivered component dict with
``provenance: "grounded"|"estimated"|"generated"`` (wire-contract §6); the
desktop renders a compact right-aligned badge in the component chrome for
TOP-LEVEL canvas components only. Absent/unknown values (pre-055 servers,
FF_COMPONENT_REFINE off) render nothing — byte-identical widgets.
"""
import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QLabel  # noqa: E402

from astral_client import theme as T  # noqa: E402
from astral_client.app import Canvas  # noqa: E402
from astral_client.renderer import RenderContext, provenance_badge, render  # noqa: E402


def _ctx():
    return RenderContext(emit=lambda *a: None)


def _badge_of(widget):
    return widget.findChild(QLabel, "provenance_badge")


def _card(provenance=None, cid="wc_1"):
    comp = {"type": "card", "component_id": cid, "title": "C", "content": []}
    if provenance is not None:
        comp["provenance"] = provenance
    return comp


# --- the badge itself ---------------------------------------------------------

@pytest.mark.parametrize("kind,text", [
    ("grounded", "tool data"),
    ("estimated", "estimated"),
    ("generated", "AI-generated"),
])
def test_badge_kinds_render_with_label_and_property(qapp, kind, text):
    b = provenance_badge({"type": "card", "provenance": kind})
    assert b is not None
    assert text in b.text()
    assert b.property("provenance") == kind


def test_badge_colors_match_theme_conventions(qapp):
    grounded = provenance_badge({"type": "card", "provenance": "grounded"})
    estimated = provenance_badge({"type": "card", "provenance": "estimated"})
    generated = provenance_badge({"type": "card", "provenance": "generated"})
    assert T.VARIANT_COLORS["success"][0] in grounded.styleSheet()
    assert T.VARIANT_COLORS["warning"][0] in estimated.styleSheet()
    assert T.MUTED in generated.styleSheet()


@pytest.mark.parametrize("comp", [
    {"type": "card"},                                  # field absent
    {"type": "card", "provenance": "verified"},        # outside the vocabulary
    {"type": "card", "provenance": ""},
    {"type": "card", "provenance": None},
    {"type": "divider", "provenance": "grounded"},     # decorative skip set
    {"type": "skeleton", "provenance": "generated"},
    "not-a-dict",
])
def test_badge_absent_or_unknown_renders_nothing(qapp, comp):
    assert provenance_badge(comp) is None


# --- render() chrome wiring ---------------------------------------------------

def test_top_level_render_carries_badge(qapp):
    w = render(_card("grounded"), _ctx(), top_level=True)
    b = _badge_of(w)
    assert b is not None and "tool data" in b.text()
    # The wrapper keeps the workspace identity for canvas reconciliation.
    assert w.property("component_id") == "wc_1"


def test_top_level_render_without_field_is_unwrapped(qapp):
    from PySide6.QtWidgets import QFrame
    w = render(_card(), _ctx(), top_level=True)
    assert isinstance(w, QFrame)  # the card frame itself, no chrome wrapper
    assert _badge_of(w) is None


def test_nested_children_never_grow_badges(qapp):
    # _tag_source stamps nested children too — only the top level is badged.
    comp = _card("grounded")
    comp["content"] = [
        {"type": "text", "content": "child", "provenance": "grounded"},
        {"type": "alert", "message": "m", "provenance": "generated"},
    ]
    w = render(comp, _ctx(), top_level=True)
    badges = w.findChildren(QLabel, "provenance_badge")
    assert len(badges) == 1


def test_default_render_ignores_provenance(qapp):
    # Non-canvas call sites (surfaces, nested renders) pass no top_level flag.
    w = render(_card("grounded"), _ctx())
    assert _badge_of(w) is None


# --- through the canvas -------------------------------------------------------

def test_canvas_full_render_badges_components(qapp):
    c = Canvas(_ctx())
    c.set_components([_card("grounded", "wc_a"), _card(None, "wc_b")])
    assert _badge_of(c._by_id["wc_a"]) is not None
    assert _badge_of(c._by_id["wc_b"]) is None


def test_canvas_upsert_badges_component(qapp):
    c = Canvas(_ctx())
    c.apply_ops([{"op": "upsert", "component_id": "wc_a",
                  "component": _card("estimated", "wc_a")}])
    b = _badge_of(c._by_id["wc_a"])
    assert b is not None and b.property("provenance") == "estimated"
