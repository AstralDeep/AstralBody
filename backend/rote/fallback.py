"""Capability fallback ladder — 033 Wave-3 (C-D1).

A renderer target publishes the set of primitive types it can render; ROTE then
substitutes any *unsupported* type down a fixed degradation ladder
(timeline→list, chart→table→text, …) so the SDUI contract degrades gracefully
on a constrained or brand-new target instead of emitting an "unsupported
component" placeholder. ``text`` is assumed universally renderable and is the
terminal of every ladder.

This module is the pure contract: the ladder and :func:`first_supported`. The
structural conversion + recursion lives in ``ComponentAdapter`` (it reuses the
existing text extraction). No new dependency.
"""
from __future__ import annotations

from typing import AbstractSet, Tuple

#: Per-primitive ordered substitution candidates (best-fidelity first). Every
#: chain bottoms out at ``text``, which is assumed always supported.
FALLBACK_LADDER = {
    "timeline": ("list", "text"),
    "bar_chart": ("table", "list", "text"),
    "line_chart": ("table", "list", "text"),
    "pie_chart": ("table", "list", "text"),
    "plotly_chart": ("table", "list", "text"),
    "table": ("list", "text"),
    "keyvalue": ("table", "list", "text"),
    "metric": ("text",),
    "hero": ("text",),
    "rating": ("text",),
    "badge": ("text",),
    "alert": ("text",),
    "list": ("text",),
    "code": ("text",),
    "grid": ("container", "list", "text"),
    "tabs": ("container", "list", "text"),
    "collapsible": ("container", "card", "text"),
    "card": ("container", "text"),
    "container": ("text",),
    "divider": ("text",),
    "image": ("text",),
    "skeleton": ("text",),
}

#: Terminal fallback — assumed renderable everywhere.
TERMINAL = "text"


def first_supported(ctype: str, supported: AbstractSet[str]) -> str:
    """The type ``ctype`` should render AS, given the target's ``supported``
    set: ``ctype`` itself when supported, else the first ladder step that is
    supported, else :data:`TERMINAL` (``text``). Pure + total."""
    c = (ctype or "").strip().lower()
    if not supported or c in supported:
        return c or TERMINAL
    for cand in FALLBACK_LADDER.get(c, (TERMINAL,)):
        if cand in supported:
            return cand
    return TERMINAL


def ladder_for(ctype: str) -> Tuple[str, ...]:
    """The (read-only) degradation chain for a primitive type."""
    return FALLBACK_LADDER.get((ctype or "").strip().lower(), (TERMINAL,))
