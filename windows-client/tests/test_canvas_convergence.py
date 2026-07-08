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
    """The known clobber: a ui_upsert adds A, then a full render re-delivering
    the SAME A (+ B) must keep A rather than throwing it away and rebuilding."""
    c = Canvas(_ctx())
    c.apply_ops([{"op": "upsert", "component_id": "A", "component": _card("A")}])
    wa = c._by_id["A"]
    c.set_components([_card("A"), _card("B")])
    assert "A" in c._by_id and "B" in c._by_id
    assert c._by_id["A"] is wa   # A survived, not clobbered


def test_out_of_turn_render_updates_a_matching_id_in_place(qapp):
    """Mirrors the Android twin (CanvasClobberTest
    'out_of_turn_render_updates_a_matching_id_in_place'): the same id delivered
    as a card then as an ALERT across two full renders must show the alert —
    id-only reuse would keep the stale card widget (timeline snapshots,
    combine/condense re-deliver ids with changed content)."""
    from PySide6.QtWidgets import QLabel

    c = Canvas(_ctx())
    c.set_components([{"type": "card", "component_id": "A",
                       "title": "Live data", "content": []}])
    w1 = c._by_id["A"]
    c.set_components([{"type": "alert", "component_id": "A",
                       "variant": "info", "message": "SNAPSHOT"}])
    w2 = c._by_id["A"]
    assert w2 is not w1                      # changed content -> fresh widget
    texts = [(lab.text() or "") for lab in w2.findChildren(QLabel)]
    assert any("SNAPSHOT" in t for t in texts)
    assert not any("Live data" in t for t in texts)


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


def test_restyle_rerenders_retained_components(qapp):
    """M5: a live theme change restyles the canvas by re-rendering the retained
    component list (inline-styled SDUI content is styled at render time, so it
    needs a rebuild — global QSS alone won't update it)."""
    c = Canvas(_ctx())
    c.set_components([_card("A"), _card("B")])
    wa = c._by_id["A"]
    c.restyle()
    assert set(c._by_id) == {"A", "B"}       # same identities present
    assert c._by_id["A"] is not wa           # fresh widgets (new palette applied)
    assert c._lay.count() - 1 == 2           # both re-inserted (minus the stretch)


def test_restyle_empty_canvas_is_safe(qapp):
    c = Canvas(_ctx())
    c.restyle()                              # nothing rendered yet — must not raise
    assert c._by_id == {}


def test_duplicate_id_in_one_payload_not_inserted_twice(qapp):
    """Minor: two components sharing a component_id in one payload must not reuse
    (or re-insert) the same widget object twice; the duplicate renders fresh."""
    c = Canvas(_ctx())
    c.set_components([_card("A")])
    # a full render whose payload repeats id "A" (malformed but must be tolerated)
    c.set_components([_card("A"), _card("A"), _card("B")])
    assert set(c._by_id) == {"A", "B"}
    # three components placed (both A widgets + B), each a distinct widget object
    widgets = [c._lay.itemAt(i).widget() for i in range(c._lay.count() - 1)]
    assert len(widgets) == 3
    assert len(set(id(w) for w in widgets)) == 3   # no widget added twice


def test_unchanged_full_render_early_exits(qapp):
    """A full render whose payload is the same object as (or == equal to) the
    last one skips reconciliation entirely — even UNKEYED widgets survive,
    which reconciliation would have rebuilt."""
    c = Canvas(_ctx())
    comps = [{"type": "text", "content": "one"}, _card("A")]
    c.set_components(comps)
    unkeyed_before = c._lay.itemAt(0).widget()
    wa = c._by_id["A"]
    c.set_components(comps)  # same object
    assert c._lay.itemAt(0).widget() is unkeyed_before
    c.set_components([{"type": "text", "content": "one"}, _card("A")])  # == equal
    assert c._lay.itemAt(0).widget() is unkeyed_before
    assert c._by_id["A"] is wa


def test_equal_render_after_upsert_still_reconciles(qapp):
    """apply_ops diverges the canvas from the last full-render payload, so an
    equal-looking full render must NOT early-exit — the upserted component has
    to be removed by reconciliation."""
    c = Canvas(_ctx())
    c.set_components([_card("A")])
    c.apply_ops([{"op": "upsert", "component_id": "B", "component": _card("B")}])
    assert "B" in c._by_id
    c.set_components([_card("A")])
    assert "B" not in c._by_id
    assert c._lay.count() - 1 == 1


def test_early_exit_still_clears_skeleton(qapp):
    c = Canvas(_ctx())
    c.set_components([_card("A")])
    c.show_skeleton()
    c.set_components([_card("A")])  # unchanged payload — early exit path
    assert c._skeleton is None


def test_restyle_bypasses_early_exit(qapp):
    """restyle() re-renders the SAME retained list — the early exit must not
    swallow it (the full rebuild is intentional: inline CSS is palette-stale)."""
    c = Canvas(_ctx())
    c.set_components([_card("A")])
    wa = c._by_id["A"]
    c.restyle()
    assert c._by_id["A"] is not wa


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
