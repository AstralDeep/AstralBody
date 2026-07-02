"""Feature 044 (T023, US2) — canvas full-render guarantee.

Locks the 029 designer contract that a **canvas-target** ``ui_render`` always
carries the COMPLETE set of live components — every keyed component either
materialized inside its designed arrangement or appended flat — so a full
re-render never silently drops an earlier keyed component (the disappearing-UI
class of defect the native clients were vulnerable to).

The guarantee lives in ``Orchestrator._canvas_components`` (what
``_push_canvas`` and the designer's delivery path both send). DB-free: a fake
workspace feeds ``_canvas_components``/``_push_canvas`` (bound as unbound
methods), exercising the REAL ``ui_designer.materialize`` +
``workspace.iter_layout_refs`` logic.

Investigation result (documented by these tests): the guarantee ALREADY holds.
``_canvas_components`` builds ``by_id`` from every live row, materializes the
claimed refs inside each layout, and appends every UNCLAIMED component flat in
shared position order; ``materialize`` only drops refs to *vanished*
components, and unclaimed components are always re-appended — so no live keyed
component can be lost. No server-side fix was required.
"""
from __future__ import annotations

import types
from typing import Any, Dict, List

import pytest

from orchestrator.orchestrator import Orchestrator


# --------------------------------------------------------------------------- fakes

def _comp(cid: str, pos: int) -> Dict[str, Any]:
    return {"component_id": cid, "position": pos,
            "component_data": {"type": "metric", "title": cid, "value": pos,
                               "component_id": cid}}


class FakeWorkspace:
    """Feeds _canvas_components: rows (id/position/component_data) + layouts."""

    def __init__(self, rows: List[Dict[str, Any]], layouts: List[Dict[str, Any]]):
        self._rows = rows
        self._layouts = layouts

    def live_layouts(self, chat_id, user_id):
        return [dict(x) for x in self._layouts]

    def live_rows(self, chat_id, user_id):
        # Deep-ish copy so the method under test can mutate freely.
        return [{"component_id": r["component_id"], "position": r["position"],
                 "component_data": dict(r["component_data"])} for r in self._rows]

    def live_components(self, chat_id, user_id):
        return [dict(r["component_data"]) for r in
                sorted(self._rows, key=lambda r: r["position"])]


def _orch(workspace: FakeWorkspace) -> Any:
    orch = types.SimpleNamespace(workspace=workspace)
    orch._canvas_components = types.MethodType(Orchestrator._canvas_components, orch)
    orch._push_canvas = types.MethodType(Orchestrator._push_canvas, orch)
    return orch


def _collect_ids(nodes: List[Dict[str, Any]]) -> set:
    """Every component_id anywhere in a component list (top-level + nested)."""
    found = set()

    def walk(node: Any):
        if isinstance(node, list):
            for x in node:
                walk(x)
            return
        if not isinstance(node, dict):
            return
        cid = node.get("component_id")
        if cid:
            found.add(cid)
        for key in ("children", "content"):
            walk(node.get(key) or [])
        for tab in (node.get("tabs") or []):
            if isinstance(tab, dict):
                walk(tab.get("content") or [])

    walk(nodes)
    return found


def _grid_layout(*cids: str) -> List[Dict[str, Any]]:
    return [{"type": "grid", "columns": 2,
             "children": [{"type": "ref", "component_id": c} for c in cids]}]


# --------------------------------------------------------------------------- tests

def test_flat_canvas_returns_all_components_when_no_layouts():
    ws = FakeWorkspace(rows=[_comp("c1", 0), _comp("c2", 1), _comp("c3", 2)], layouts=[])
    out = _orch(ws)._canvas_components("chat", "user")
    assert out == ws.live_components("chat", "user")
    assert _collect_ids(out) == {"c1", "c2", "c3"}


def test_designed_canvas_keeps_every_keyed_component():
    """A layout that claims a SUBSET still yields every live component:
    claimed ones materialized inside the arrangement, the rest flat."""
    ws = FakeWorkspace(
        rows=[_comp("c1", 0), _comp("c2", 1), _comp("c3", 2)],
        layouts=[{"layout": _grid_layout("c1", "c2"), "position": 0,
                  "layout_key": "chat|turn1"}],
    )
    out = _orch(ws)._canvas_components("chat", "user")
    # No keyed component is dropped.
    assert _collect_ids(out) == {"c1", "c2", "c3"}
    # Top level = the designed grid + the one unclaimed component (not the 3 flat).
    assert len(out) == 2
    grid = next(n for n in out if n.get("type") == "grid")
    assert _collect_ids([grid]) == {"c1", "c2"}, "claimed refs materialized in place"
    # The unclaimed one rides flat at top level exactly once (not duplicated).
    flat_ids = [n.get("component_id") for n in out if n.get("type") != "grid"]
    assert flat_ids == ["c3"]


def test_stale_layout_ref_never_drops_a_live_component():
    """A layout ref to a vanished component drops silently, but every LIVE
    keyed component still appears (claimed → materialized, else flat)."""
    ws = FakeWorkspace(
        rows=[_comp("c1", 0), _comp("c2", 1), _comp("c3", 2)],
        layouts=[{"layout": _grid_layout("c1", "GONE"), "position": 0,
                  "layout_key": "chat|turn1"}],
    )
    out = _orch(ws)._canvas_components("chat", "user")
    assert _collect_ids(out) == {"c1", "c2", "c3"}, "no live component lost to a stale ref"
    assert "GONE" not in _collect_ids(out)


@pytest.mark.asyncio
async def test_push_canvas_sends_the_full_canvas_to_matching_sockets():
    """_push_canvas fans the COMPLETE canvas out to exactly the sockets on this
    user+chat, and each render carries the full materialized component set."""
    ws_state = FakeWorkspace(
        rows=[_comp("c1", 0), _comp("c2", 1), _comp("c3", 2)],
        layouts=[{"layout": _grid_layout("c1", "c2"), "position": 0,
                  "layout_key": "chat|turn1"}],
    )
    orch = _orch(ws_state)
    sends: List[Any] = []

    async def _capture_send(sock, components, target="canvas"):
        sends.append((sock, list(components), target))

    orch.send_ui_render = _capture_send
    sock_match = object()      # right user + right chat
    sock_other_chat = object()  # right user, wrong chat
    sock_other_user = object()  # wrong user
    orch.ui_clients = [sock_match, sock_other_chat, sock_other_user]
    orch._get_user_id = lambda s: "user" if s is not sock_other_user else "other"
    orch._ws_active_chat = {id(sock_match): "chat", id(sock_other_chat): "elsewhere"}

    await orch._push_canvas("chat", "user")

    assert len(sends) == 1, "only the matching socket receives the canvas"
    sock, comps, target = sends[0]
    assert sock is sock_match and target == "canvas"
    # The pushed canvas is the COMPLETE materialized set — no keyed drop.
    assert _collect_ids(comps) == {"c1", "c2", "c3"}
    assert comps == orch._canvas_components("chat", "user")
