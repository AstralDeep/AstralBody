"""Gated open-ended / generative primitives — 033 Wave-1 (C-N2).

Lets the model compose a NOVEL widget beyond the closed astralprims palette —
but safely, by expressing it as a **constrained grammar** (a small set of
compositional building blocks) that a deterministic **post-validator** checks
and an **escape-by-default** renderer materializes. The model never emits raw
HTML; it emits a typed tree of allowed nodes, every text leaf is HTML-escaped,
styling is fixed CSS classes (no model-supplied inline style/script), and the
tree is bounded in size and depth. A genuinely new *named* primitive still rides
the draft→self-test→admin-approval rail; this module is the safety floor under
that — an unapproved generative spec renders only from the safe grammar.

Pure, stdlib only (``html.escape``). **No new dependency.** Flag
``FF_GENERATIVE_PRIMITIVES`` (default OFF). Fail-safe: an invalid spec renders a
plain notice, never the unvalidated content.
"""
from __future__ import annotations

import html
import os
from typing import Any, Dict, List, Tuple

#: The constrained grammar — the only node types the model may compose.
_CONTAINERS = {"col", "row", "group"}
_LEAVES = {"text", "label", "value", "badge", "bar", "divider", "spacer"}
_ALLOWED_TYPES = _CONTAINERS | _LEAVES

#: Bounded enums for the few styling knobs (model can't supply free-form style).
_VARIANTS = {"default", "muted", "strong", "success", "warning", "danger", "info"}

#: Structural bounds (a generative widget is a small composition, not a document).
_MAX_NODES = 120
_MAX_DEPTH = 6
_MAX_CHILDREN = 24
_MAX_TEXT = 2000


def generative_enabled() -> bool:
    """FF_GENERATIVE_PRIMITIVES feature flag (default OFF; feature 033 C-N2)."""
    return os.getenv("FF_GENERATIVE_PRIMITIVES", "false").strip().lower() in (
        "1", "true", "yes", "on")


def validate(spec: Any) -> Tuple[bool, List[str]]:
    """Validate a generative spec against the constrained grammar. Returns
    ``(ok, errors)``; ``ok`` iff the whole tree is composed only of allowed
    node types within the structural bounds with well-typed fields."""
    errors: List[str] = []
    count = [0]

    def walk(node: Any, depth: int) -> None:
        if len(errors) > 20:
            return
        if depth > _MAX_DEPTH:
            errors.append(f"max depth {_MAX_DEPTH} exceeded")
            return
        if not isinstance(node, dict):
            errors.append(f"node is not an object: {type(node).__name__}")
            return
        count[0] += 1
        if count[0] > _MAX_NODES:
            errors.append(f"max node count {_MAX_NODES} exceeded")
            return
        t = node.get("t")
        if t not in _ALLOWED_TYPES:
            errors.append(f"disallowed node type: {t!r}")
            return
        variant = node.get("variant")
        if variant is not None and variant not in _VARIANTS:
            errors.append(f"disallowed variant: {variant!r}")
        for field in ("text", "label", "value"):
            v = node.get(field)
            if isinstance(v, str) and len(v) > _MAX_TEXT:
                errors.append(f"{field} exceeds {_MAX_TEXT} chars")
        if t == "bar":
            bv = node.get("value")
            if not isinstance(bv, (int, float)) or isinstance(bv, bool) or not (0 <= bv <= 1):
                errors.append("bar.value must be a number in [0,1]")
        if t in _CONTAINERS:
            children = node.get("children")
            if not isinstance(children, list):
                errors.append(f"{t} requires a children list")
            elif len(children) > _MAX_CHILDREN:
                errors.append(f"{t} exceeds {_MAX_CHILDREN} children")
            else:
                for ch in children:
                    walk(ch, depth + 1)

    walk(spec, 0)
    return (not errors), errors


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _render_node(node: Dict[str, Any]) -> str:
    t = node.get("t")
    variant = node.get("variant") if node.get("variant") in _VARIANTS else "default"
    vclass = f" gen-{_esc(variant)}"
    if t == "divider":
        return '<hr class="gen-divider"/>'
    if t == "spacer":
        return '<div class="gen-spacer"></div>'
    if t in ("text", "label", "value", "badge"):
        text = _esc(node.get("text") or node.get("label") or node.get("value") or "")
        cls = {"text": "gen-text", "label": "gen-label", "value": "gen-value",
               "badge": "gen-badge"}[t]
        return f'<span class="{cls}{vclass}">{text}</span>'
    if t == "bar":
        pct = max(0.0, min(1.0, float(node.get("value", 0)))) * 100
        return (f'<div class="gen-bar{vclass}"><div class="gen-bar-fill" '
                f'style="width:{pct:.1f}%"></div></div>')
    if t in _CONTAINERS:
        inner = "".join(_render_node(ch) for ch in node.get("children", [])
                        if isinstance(ch, dict))
        return f'<div class="gen-{_esc(t)}{vclass}">{inner}</div>'
    return ""


def render(spec: Any) -> str:
    """Render a generative spec to safe HTML (escape-by-default, fixed classes).
    An invalid spec yields a plain fail-safe notice — never the raw content."""
    ok, errors = validate(spec)
    if not ok:
        return ('<div class="gen-invalid">This generated widget could not be '
                f'safely displayed ({_esc(errors[0])}).</div>')
    return f'<div class="astral-generative">{_render_node(spec)}</div>'
