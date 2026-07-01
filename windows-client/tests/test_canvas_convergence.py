"""Feature 044 (T024) — identity-reconciled canvas.

A full canvas-target `ui_render` (`Canvas.set_components`) reconciles BY
component identity instead of a blind drop-and-rebuild, so a component the new
set still contains is never lost (the clobber bug). `apply_ops` keyed
upsert/remove and the streaming seq-dedupe are confirmed intact.

Canvas is constructed directly with a RenderContext — no MainWindow needed.
"""
import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from astral_client.app import Canvas  # noqa: E402
from astral_client.renderer import RenderContext  # noqa: E402
from astral_client.streaming import stream_frame_to_ops, stream_node_id  # noqa: E402


def _ctx():
    return RenderContext(emit=lambda *a: None, download=lambda *a: None)


def _card(cid):
    return {"type": "card", "component_id": cid, "content": []}


def test_identity_preserved_across_full_renders(qapp):
    c = Canvas(_ctx())
    c.set_components([_card("A"), _card("B")])
    wa = c._by_id["A"]
    # a second full render that still includes A keeps A's exact widget
    c.set_components([_card("A"), _card("C")])
    assert "A" in c._by_id and c._by_id["A"] is wa  # identity preserved
    assert "C" in c._by_id
    assert "B" not in c._by_id                       # dropped id removed


def test_clobber_sequence_upsert_then_full_render(qapp):
    """The known clobber: a ui_upsert adds A, then a full render of A+B must keep
    A rather than throwing it away and rebuilding."""
    c = Canvas(_ctx())
    c.apply_ops([{"op": "upsert", "component_id": "A",
                  "component": {"type": "text", "content": "hi"}}])
    wa = c._by_id["A"]
    c.set_components([_card("A"), _card("B")])
    assert "A" in c._by_id and "B" in c._by_id
    assert c._by_id["A"] is wa   # A survived, not clobbered


def test_full_render_removes_absent_id(qapp):
    c = Canvas(_ctx())
    c.set_components([_card("A")])
    assert "A" in c._by_id
    c.set_components([_card("B")])
    assert "A" not in c._by_id and "B" in c._by_id


def test_unkeyed_components_rebuild_positionally(qapp):
    c = Canvas(_ctx())
    c.set_components([{"type": "text", "content": "one"},
                      {"type": "text", "content": "two"}])
    assert c._by_id == {}                 # unkeyed -> not identity-tracked
    assert c._lay.count() - 1 == 2        # both present (minus the trailing stretch)
    c.set_components([{"type": "text", "content": "solo"}])
    assert c._lay.count() - 1 == 1        # positional rebuild


def test_apply_ops_upsert_and_remove(qapp):
    c = Canvas(_ctx())
    c.apply_ops([{"op": "upsert", "component_id": "X",
                  "component": {"type": "text", "content": "x"}}])
    assert "X" in c._by_id
    c.apply_ops([{"op": "remove", "component_id": "X"}])
    assert "X" not in c._by_id


def test_apply_ops_upsert_replaces_in_place(qapp):
    c = Canvas(_ctx())
    c.apply_ops([{"op": "upsert", "component_id": "X",
                  "component": {"type": "text", "content": "v1"}}])
    w1 = c._by_id["X"]
    idx = c._lay.indexOf(w1)
    c.apply_ops([{"op": "upsert", "component_id": "X",
                  "component": {"type": "text", "content": "v2"}}])
    w2 = c._by_id["X"]
    assert w2 is not w1                    # a fresh widget with new content
    assert c._lay.indexOf(w2) == idx       # replaced in the same slot


def test_stream_seq_dedupe_drops_dup_and_stale(qapp):
    """The _on_stream_data path uses stream_frame_to_ops with a shared seq_state
    so out-of-order / duplicate frames are dropped (canvas not double-updated)."""
    seq: dict = {}
    frame = {"type": "ui_stream_data", "stream_id": "s1", "seq": 2,
             "components": [{"type": "text", "content": "v2"}]}
    ops = stream_frame_to_ops(frame, active_chat=None, seq_state=seq)
    assert ops and ops[0]["component_id"] == stream_node_id("s1")
    # duplicate seq -> dropped
    assert stream_frame_to_ops(dict(frame), active_chat=None, seq_state=seq) == []
    # stale (lower) seq -> dropped
    stale = dict(frame)
    stale["seq"] = 1
    assert stream_frame_to_ops(stale, active_chat=None, seq_state=seq) == []
