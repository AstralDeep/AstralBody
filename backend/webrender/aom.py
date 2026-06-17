"""AOM / semantic-tree renderer — 033 Wave-3 (C-D5).

ROTE has always collapsed the astralprims component graph to HTML (web) or SSML
(voice); this is a third, *structural* render target — the **AOM** (accessibility
object model). It serializes the component graph to a navigable role / name /
state tree (NOT markup) that VOICE navigation and assistive technology can walk
node-by-node: a card is a ``group``, a table reports its row/column counts, a
heading carries its ``level``, tabs expose one ``tab`` child per tab label.

This module is the cleanest "add a target = add a renderer" proof (Constitution
II / FR-011): a single ``register_target('aom', render_aom)`` call makes it live
with **no change to astralprims or agent code**. Pure, deterministic, bounded
(recursion capped), stdlib only, and the result is always JSON-serializable.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

# ── tuning ────────────────────────────────────────────────────────────────────
_MAX_DEPTH = 12          # recursion cap; deeper subtrees collapse to a "…" leaf
_NAME_CAP = 120          # accessible names trimmed to this many characters

# Keys that may carry a list of child components, in priority order.
_CHILD_KEYS = ("children", "content")

# Heading variants → ARIA heading level.
_HEADING_LEVELS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


# component type → an ARIA-ish role string.
_ROLE_MAP: Dict[str, str] = {
    "card": "group",
    "container": "group",
    "collapsible": "group",
    "grid": "group",
    "table": "table",
    "list": "list",
    "alert": "status",
    "button": "button",
    "input": "textbox",
    "image": "img",
    "metric": "figure",
    "text": "text",          # promoted to "heading" when variant is h1/h2/h3…
    "tabs": "tablist",
    "hero": "banner",
    "timeline": "list",
    "badge": "note",
}


def aom_enabled() -> bool:
    """Return whether the AOM render target is enabled via ``FF_AOM_RENDERER``."""
    return os.getenv("FF_AOM_RENDERER", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _type_of(component: Dict[str, Any]) -> str:
    """The component's normalized (lowercased, trimmed) ``type`` string."""
    return str(component.get("type", "") or "").strip().lower()


def _heading_level(component: Dict[str, Any]) -> int | None:
    """The heading level for a text component, or ``None`` if it is not a heading."""
    variant = str(component.get("variant", "") or "").strip().lower()
    return _HEADING_LEVELS.get(variant)


def _role(component: Dict[str, Any]) -> str:
    """Map a component to its ARIA-ish role string (``generic`` when unknown)."""
    t = _type_of(component)
    if t == "text" and _heading_level(component) is not None:
        return "heading"
    return _ROLE_MAP.get(t, "generic")


def _short(value: Any) -> str:
    """A trimmed, single-line plain string for ``value`` (never None/HTML markup)."""
    text = "" if value is None else str(value)
    text = " ".join(text.split())  # collapse whitespace / newlines to single spaces
    if len(text) > _NAME_CAP:
        text = text[: _NAME_CAP - 1].rstrip() + "…"
    return text


def semantic_name(component: Any) -> str:
    """Compute the accessible name of a component as a plain string.

    Precedence: ``title`` → ``label`` → a short ``text``/``content``/``value``
    string → the component ``type``. The result is whitespace-collapsed and
    trimmed to ~120 characters; it never contains HTML.
    """
    if not isinstance(component, dict):
        return ""
    for key in ("title", "label"):
        value = component.get(key)
        if value not in (None, ""):
            return _short(value)
    for key in ("text", "content", "value"):
        value = component.get(key)
        if isinstance(value, (str, int, float, bool)) and str(value) != "":
            return _short(value)
    return _short(_type_of(component) or "")


def semantic_state(component: Any) -> Dict[str, Any]:
    """Compute a small state dict for a component (absent keys are omitted).

    Includes ``variant``/``value`` when present, ``selected``/``disabled`` when
    present, and ``level`` for headings (h1 → 1, h2 → 2, …).
    """
    state: Dict[str, Any] = {}
    if not isinstance(component, dict):
        return state
    if component.get("variant") not in (None, ""):
        state["variant"] = component["variant"]
    if component.get("value") not in (None, ""):
        state["value"] = component["value"]
    if "selected" in component:
        state["selected"] = component["selected"]
    if "disabled" in component:
        state["disabled"] = component["disabled"]
    level = _heading_level(component) if _type_of(component) == "text" else None
    if level is not None:
        state["level"] = level
    return state


def _child_components(component: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gather child component dicts from the ``children``/``content`` list keys."""
    kids: List[Dict[str, Any]] = []
    for key in _CHILD_KEYS:
        value = component.get(key)
        if isinstance(value, list):
            kids.extend(c for c in value if isinstance(c, dict))
    return kids


def _truncated_leaf() -> Dict[str, Any]:
    """The leaf node substituted when the recursion depth cap is exceeded."""
    return {"role": "generic", "name": "…", "state": {}, "children": []}


def _table_summary_child(component: Dict[str, Any]) -> Dict[str, Any]:
    """A single child node summarizing a table's row and column counts."""
    rows = component.get("rows")
    n_rows = len(rows) if isinstance(rows, list) else 0
    cols = component.get("columns")
    if not isinstance(cols, list):
        cols = component.get("headers")
    if isinstance(cols, list):
        n_cols = len(cols)
    elif isinstance(rows, list) and rows and isinstance(rows[0], list):
        n_cols = len(rows[0])
    else:
        n_cols = 0
    return {
        "role": "text",
        "name": _short(f"{n_rows} rows, {n_cols} columns"),
        "state": {},
        "children": [],
    }


def _tab_children(component: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One ``tab`` child per entry in a tabs component, named by its label."""
    out: List[Dict[str, Any]] = []
    for tab in component.get("tabs") or []:
        if isinstance(tab, dict):
            label = tab.get("label", tab.get("title"))
            out.append(
                {
                    "role": "tab",
                    "name": _short("" if label is None else label),
                    "state": {},
                    "children": [],
                }
            )
    return out


def to_semantic_node(component: Any, _depth: int = 0) -> Dict[str, Any]:
    """Recursively serialize a component to a ``{role, name, state, children}`` node.

    Children are drawn from ``children``/``content`` lists. A ``table`` collapses
    to a single summary child (row/column counts) rather than one node per row; a
    ``tabs`` component yields one ``tab`` child per tab. Recursion is capped at a
    depth of 12 — deeper subtrees become a ``generic`` ``"…"`` leaf. A non-dict
    input degrades to an empty ``generic`` node.
    """
    if not isinstance(component, dict):
        return {"role": "generic", "name": "", "state": {}, "children": []}
    if _depth >= _MAX_DEPTH:
        return _truncated_leaf()

    t = _type_of(component)
    if t == "table":
        children = [_table_summary_child(component)]
    elif t == "tabs":
        children = _tab_children(component)
    else:
        children = [
            to_semantic_node(child, _depth + 1)
            for child in _child_components(component)
        ]

    return {
        "role": _role(component),
        "name": semantic_name(component),
        "state": semantic_state(component),
        "children": children,
    }


def render_aom(components: List[Dict[str, Any]], device: Any = None) -> Dict[str, Any]:
    """Render a component list to a single navigable AOM document node.

    Returns ``{"role": "document", "name": ..., "children": [...]}`` where each
    child is the semantic node of a top-level component dict. ``device`` is
    accepted for signature parity with other render targets; when it is a plain
    string it names the document, otherwise the document is named ``"canvas"``.
    The returned structure is always JSON-serializable.
    """
    name = device if isinstance(device, str) and device else "canvas"
    children = [
        to_semantic_node(c) for c in (components or []) if isinstance(c, dict)
    ]
    return {"role": "document", "name": name, "children": children}
