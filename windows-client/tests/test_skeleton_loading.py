"""Query-start canvas skeleton (cross-client parity with Android's
SkeletonCanvas / the web client's #astral-canvas-skeleton).

`Canvas.show_skeleton()` appends a loading placeholder when a chat turn is
sent; the FIRST canvas content of the turn removes it (`set_components` for a
full render, `apply_ops` for upserts — streaming routes through apply_ops
too), and `hide_skeleton()` clears it when a turn ends with no canvas output
(text-only answers, errors, cancellation).
"""
import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from astral_client.app import Canvas  # noqa: E402
from astral_client.renderer import RenderContext, render  # noqa: E402


def _ctx():
    return RenderContext(emit=lambda *a: None, download=lambda *a: None)


def _card(cid):
    return {"type": "card", "component_id": cid, "content": []}


def test_show_skeleton_appends_placeholder(qapp):
    c = Canvas(_ctx())
    assert c._skeleton is None
    c.show_skeleton()
    assert c._skeleton is not None
    assert c._lay.indexOf(c._skeleton) != -1  # actually in the layout
    # idempotent — a second show never stacks a second placeholder
    first = c._skeleton
    c.show_skeleton()
    assert c._skeleton is first


def test_full_render_clears_skeleton(qapp):
    c = Canvas(_ctx())
    c.show_skeleton()
    c.set_components([_card("A")])
    assert c._skeleton is None
    assert "A" in c._by_id


def test_upsert_clears_skeleton(qapp):
    c = Canvas(_ctx())
    c.show_skeleton()
    c.apply_ops([{"op": "upsert", "component_id": "A", "component": _card("A")}])
    assert c._skeleton is None
    assert "A" in c._by_id


def test_empty_ops_keep_skeleton(qapp):
    # A no-op upsert (e.g. a frame for another chat filtered upstream) is not
    # canvas content — the loading state stays until real content or turn end.
    c = Canvas(_ctx())
    c.show_skeleton()
    c.apply_ops([])
    assert c._skeleton is not None


def test_hide_skeleton_is_idempotent(qapp):
    c = Canvas(_ctx())
    c.hide_skeleton()  # never shown — must not raise
    c.show_skeleton()
    c.hide_skeleton()
    assert c._skeleton is None
    c.hide_skeleton()


def test_skeleton_appends_below_existing_components(qapp):
    # A follow-up query must not disturb the persistent workspace — the
    # placeholder sits under the existing components.
    c = Canvas(_ctx())
    c.set_components([_card("A")])
    c.show_skeleton()
    assert c._lay.indexOf(c._skeleton) > c._lay.indexOf(c._by_id["A"])


def test_skeleton_card_variant_renders_blocks(qapp):
    w = render({"type": "skeleton", "variant": "card", "count": 3}, _ctx())
    assert w.layout().count() == 3
    bar = w.layout().itemAt(0).widget()
    assert bar.height() >= 40 or bar.minimumHeight() >= 40  # chunky card block
