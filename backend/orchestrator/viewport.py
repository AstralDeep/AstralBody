"""Live viewport/orientation re-adaptation.

When a client reports a viewport/orientation change, ROTE already re-derives the
device profile and the ``update_device`` handler re-adapts the current canvas.
A full re-adaptation re-renders the WHOLE canvas (a full ``ui_render``), which
flashes every component and loses scroll position even when only a couple
actually adapt differently.

This computes a targeted update: render each canvas component under the old and
the new profile and emit a ``ui_upsert`` op for ONLY the components whose
rendered fragment actually changed. A rotate that bumps ``max_grid_columns``
re-pushes the grids; the untouched text/cards stay put.

Pure + deterministic — the diff takes two render callables so it is testable
without the renderer. Flag ``FF_LIVE_VIEWPORT`` (default OFF) gates the dispatch
hook; off keeps the full re-render. Additive + fail-open: any error in the diff
falls back to the full render.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Tuple

#: A render callable: component dict → (adapted_component, html) for a fixed
#: device profile (the caller binds the old / new profile).
RenderFn = Callable[[Dict[str, Any]], Tuple[Any, Any]]


def viewport_enabled() -> bool:
    """FF_LIVE_VIEWPORT feature flag (default OFF)."""
    return os.getenv("FF_LIVE_VIEWPORT", "false").strip().lower() in ("1", "true", "yes", "on")


def targeted_ops(components: List[Dict[str, Any]],
                 render_old: RenderFn, render_new: RenderFn) -> List[Dict[str, Any]]:
    """The ``ui_upsert`` ops for only the components whose rendered fragment
    differs between the old and new profile.

    Each component must carry a ``component_id`` (canvas identity); one without
    is skipped (it has no stable anchor to upsert). A render that raises for a
    component skips it rather than aborting the whole diff. Returns ops in the
    input order so the push is deterministic."""
    ops: List[Dict[str, Any]] = []
    for comp in (components or []):
        cid = comp.get("component_id") if isinstance(comp, dict) else None
        if not cid:
            continue
        try:
            _, old_html = render_old(comp)
            adapted, new_html = render_new(comp)
        except Exception:
            continue
        if old_html != new_html:
            ops.append({"op": "upsert", "component_id": cid,
                        "component": adapted, "html": new_html})
    return ops
