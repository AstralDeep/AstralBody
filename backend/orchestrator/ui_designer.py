"""Feature 029 — the adaptive UI designer (contracts/ui-designer-llm.md).

After a chat round produces two or more rich components, one LLM pass designs
an *arrangement*: a layout tree built ONLY from existing astralprims types
whose leaves REFERENCE the round's workspace components by ``component_id``
(``{"type": "ref", "component_id": ...}``). Tool-produced content is never
rewritten, merged, or dropped — identities, in-place refresh, pagination and
supersede semantics survive intact (the hybrid model the spec mandates).
The designer may add its own "garnish" (headline metrics, narrative text,
grouping containers) with deterministic ``dg_*`` ids so re-designs update
rather than duplicate.

Failure semantics are strictly fail-open: any error, timeout, refusal or
invalid output makes the caller fall back to the legacy flat append. The
validation pipeline never raises past :func:`design_round` — it returns
``None`` and logs a structured fallback reason instead.

The module is LLM-agnostic: callers inject ``llm_call`` (an async callable
``messages -> content str | None``) so credential resolution stays with the
orchestrator (feature-006 client factory, websocket-scoped).
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger("orchestrator.ui_designer")

#: Rounds below this component count render directly (no designer latency).
MIN_DESIGN_COMPONENTS = 2

#: Designer time budget default; operator override via UI_DESIGNER_TIMEOUT_SECONDS.
DEFAULT_TIMEOUT_SECONDS = 8.0

REF_TYPE = "ref"
GARNISH_ID_PREFIX = "dg_"

#: Container keys the validator/materializer walk (matches the orchestrator's
#: ``_validate_component_tree`` traversal plus tabs items).
_CHILD_KEYS = ("children", "content")

#: Bounds keeping the prompt affordable on big rounds.
_MAX_REQUEST_CHARS = 1000
_MAX_COMPONENT_EXCERPT_CHARS = 1500
_MAX_CANVAS_LINES = 30


def designer_enabled() -> bool:
    """FF_UI_DESIGNER feature flag (default ON; FR-029)."""
    return os.getenv("FF_UI_DESIGNER", "true").strip().lower() not in ("0", "false", "no", "off")


def designer_timeout_seconds() -> float:
    """Operator-configurable design budget (FR-023)."""
    raw = os.getenv("UI_DESIGNER_TIMEOUT_SECONDS", "")
    try:
        value = float(raw)
        return value if value > 0 else DEFAULT_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS


def should_design(round_components: Sequence[Dict[str, Any]], *, timeline_mode: bool = False) -> bool:
    """Invocation predicate: flag ∧ ≥2 rich components ∧ not viewing history."""
    if timeline_mode or not designer_enabled():
        return False
    rich = [c for c in round_components if isinstance(c, dict) and c.get("type")]
    return len(rich) >= MIN_DESIGN_COMPONENTS


# ───────────────────────────── prompt ────────────────────────────────────────

_LAYOUT_GUIDANCE = """LAYOUT VOCABULARY (compose freely from these astralprims types):
- {"type": "ref", "component_id": "<id>"} — places one of the round's components. THE ONLY way to include tool output.
- "grid": {"type": "grid", "columns": 2, "children": [...]} — side-by-side groups (2-3 columns max).
- "card": {"type": "card", "title": "...", "content": [...]} — titled grouping with an accent bar.
- "tabs": {"type": "tabs", "tabs": [{"label": "...", "content": [...]}]} — alternate views of related detail.
- "collapsible": {"type": "collapsible", "title": "...", "content": [...], "default_open": false} — secondary detail.
- "text": {"type": "text", "content": "...", "variant": "h2|h3|body|caption|markdown"} — short connective narrative.
- "metric": {"type": "metric", "title": "...", "value": "...", "subtitle": "...", "variant": "default|success|warning|error"} — headline takeaway.
- "alert", "divider", "list", "progress" — as in the standard palette.

DESIGN RULES:
1. Reference EVERY round component exactly once via a "ref" node. Never copy, rewrite, or summarize their internal data — place them.
2. Lead with the most important thing: a headline metric or a one-line takeaway when the data supports one.
3. Group related components side-by-side in grids (max 3 columns); push raw/secondary detail into collapsibles or tabs.
4. Give every card/tabs/collapsible a meaningful title — small screens flatten layouts to titles and text.
5. Garnish must be brief and grounded ONLY in the component digests shown; never invent numbers or facts.
6. Output ONLY JSON: {"layout": [ ...nodes... ]}. No markdown fences, no commentary.
7. If the components genuinely cannot be improved by arrangement, reply exactly: ERROR: <brief reason>."""


def _component_digest(comp: Dict[str, Any]) -> str:
    """One prompt entry per round component: identity, provenance, excerpt."""
    cid = comp.get("component_id", "?")
    public = {k: v for k, v in comp.items() if not str(k).startswith("_")}
    excerpt = json.dumps(public, default=str)
    if len(excerpt) > _MAX_COMPONENT_EXCERPT_CHARS:
        excerpt = excerpt[:_MAX_COMPONENT_EXCERPT_CHARS] + "…(truncated)"
    return (
        f"- component_id: {cid} | type: {comp.get('type', '?')} | "
        f"title: {comp.get('title') or '—'} | tool: {comp.get('_source_tool', '?')}"
        f" (agent {comp.get('_source_agent', '?')})\n  data: {excerpt}"
    )


def build_design_messages(
    user_request: str,
    round_components: Sequence[Dict[str, Any]],
    canvas_rows: Sequence[Dict[str, Any]],
    allowed_types: Set[str],
) -> List[Dict[str, str]]:
    """Build the chat-completion messages for one design pass."""
    request = (user_request or "").strip()
    if len(request) > _MAX_REQUEST_CHARS:
        request = request[:_MAX_REQUEST_CHARS] + "…"

    digests = "\n".join(_component_digest(c) for c in round_components if isinstance(c, dict))

    canvas_lines = []
    round_ids = {c.get("component_id") for c in round_components if isinstance(c, dict)}
    for row in list(canvas_rows or [])[:_MAX_CANVAS_LINES]:
        cid = row.get("component_id")
        if not cid or cid in round_ids:
            continue
        canvas_lines.append(
            f"- component_id: {cid} | title: {row.get('title') or '—'} | type: {row.get('component_type', '?')}"
        )
    canvas_block = (
        "\nALREADY ON THE CANVAS (context only — do NOT reference unless the user asked to rearrange them):\n"
        + "\n".join(canvas_lines) + "\n"
    ) if canvas_lines else ""

    palette = ", ".join(sorted(allowed_types))
    user_prompt = f"""USER REQUEST FOR THIS ROUND:
{request or '(not provided)'}

THIS ROUND'S COMPONENTS (place each exactly once via a ref node):
{digests}
{canvas_block}
FULL ALLOWED TYPE PALETTE: {palette}

{_LAYOUT_GUIDANCE}"""

    return [
        {
            "role": "system",
            "content": (
                "You are an expert interface designer for a server-driven UI. "
                "You arrange pre-built components into one cohesive, scannable round of UI. "
                "Output ONLY valid JSON or an ERROR message."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]


# ─────────────────────────── parse / validate ────────────────────────────────

class DesignRejected(Exception):
    """Raised internally when a design response cannot be used (reason carried)."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason


def parse_design_response(content: str) -> List[Any]:
    """Extract the layout node list from raw LLM output.

    Mirrors the proven fence-strip + regex extraction the combine/condense
    path uses. Raises :class:`DesignRejected` with a structured reason.
    """
    text = (content or "").strip()
    if not text:
        raise DesignRejected("empty")
    if text.upper().startswith("ERROR"):
        detail = text.split(":", 1)[1].strip() if ":" in text else text
        raise DesignRejected("refusal", detail)
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if not match:
            raise DesignRejected("parse", "no JSON found in design response")
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as e:
            raise DesignRejected("parse", str(e))
    if isinstance(data, dict):
        layout = data.get("layout")
    else:
        layout = data
    if not isinstance(layout, list) or not layout:
        raise DesignRejected("invalid", "missing or empty 'layout' array")
    return layout


def _coerce_node(node: Any) -> Optional[Dict[str, Any]]:
    """Strings become text nodes (LLMs love bare strings); non-dicts drop."""
    if isinstance(node, dict):
        return node
    if isinstance(node, str) and node.strip():
        return {"type": "text", "content": node, "variant": "body"}
    return None


def validate_layout(
    layout: List[Any],
    allowed_ref_ids: Set[str],
    allowed_types: Set[str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Sanitize a parsed layout tree.

    - ``ref`` nodes: unknown ids dropped; duplicates keep the first occurrence.
    - other nodes: ``chart``→``plotly_chart``; unknown types rewritten to
      ``container`` (children preserved) — same posture as the existing
      ``_validate_component_tree``.
    Returns ``(clean_layout, referenced_ids_in_order)``.
    """
    seen_refs: List[str] = []

    def walk(node: Any) -> Optional[Dict[str, Any]]:
        node = _coerce_node(node)
        if node is None:
            return None
        node = dict(node)
        ntype = str(node.get("type", "")).strip().lower()
        if ntype == REF_TYPE:
            cid = str(node.get("component_id") or "")
            if not cid or cid not in allowed_ref_ids:
                logger.info("ui_designer: dropping ref to unknown component %r", cid)
                return None
            if cid in seen_refs:
                logger.info("ui_designer: dropping duplicate ref %r (first wins)", cid)
                return None
            seen_refs.append(cid)
            return {"type": REF_TYPE, "component_id": cid}
        if ntype == "chart":
            node["type"] = ntype = "plotly_chart"
        if ntype and ntype not in allowed_types:
            logger.info("ui_designer: rewriting unknown type %r -> container", ntype)
            node["type"] = "container"
        for key in _CHILD_KEYS:
            nested = node.get(key)
            if isinstance(nested, list):
                node[key] = [w for w in (walk(c) for c in nested) if w is not None]
        tabs = node.get("tabs")
        if isinstance(tabs, list):
            new_tabs = []
            for tab in tabs:
                if isinstance(tab, dict):
                    tab = dict(tab)
                    content = tab.get("content")
                    if isinstance(content, list):
                        tab["content"] = [w for w in (walk(c) for c in content) if w is not None]
                    new_tabs.append(tab)
            node["tabs"] = new_tabs
        return node

    clean = [w for w in (walk(n) for n in layout) if w is not None]
    return clean, seen_refs


def repair_layout(
    layout: List[Dict[str, Any]],
    referenced: Sequence[str],
    round_ids_in_order: Sequence[str],
) -> List[Dict[str, Any]]:
    """FR-018 omission repair: round components the design missed append flat."""
    missing = [cid for cid in round_ids_in_order if cid not in set(referenced)]
    if missing:
        logger.info("ui_designer: repairing layout — appending %d omitted component(s): %s",
                    len(missing), missing)
        layout = list(layout) + [{"type": REF_TYPE, "component_id": cid} for cid in missing]
    return layout


def stamp_garnish_ids(layout: List[Dict[str, Any]], chat_id: str, layout_key: str) -> List[Dict[str, Any]]:
    """Deterministic ids for top-level garnish nodes (FR-019).

    ``dg_<sha1(chat|layout_key|ordinal)[:12]>`` — stable across re-designs of
    the same round, so a regenerated arrangement updates the same DOM nodes.
    """
    stamped = []
    for ordinal, node in enumerate(layout):
        node = dict(node)
        if node.get("type") != REF_TYPE:
            gid = GARNISH_ID_PREFIX + hashlib.sha1(
                f"{chat_id}|{layout_key}|{ordinal}".encode()
            ).hexdigest()[:12]
            node["id"] = gid
            attrs = dict(node.get("attributes") or {})
            attrs["data-component-id"] = gid
            node["attributes"] = attrs
        stamped.append(node)
    return stamped


# ───────────────────────────── materialize ───────────────────────────────────

def materialize(
    layout: Sequence[Dict[str, Any]],
    components_by_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Substitute ``ref`` leaves with live component dicts (pre-ROTE).

    The result is an ordinary astralprims component list: ROTE adaptation,
    server HTML rendering and the web client need no knowledge of ``ref``.
    Nested refs get ``attributes["data-component-id"]`` so ``ui_upsert``
    morphs keep working inside arrangements; top-level refs rely on the
    existing ``render_component_fragment`` identity wrapper (no duplicate
    anchors). Refs to vanished components drop silently.
    """

    def walk(node: Any, depth: int) -> Optional[Dict[str, Any]]:
        if not isinstance(node, dict):
            return node if node else None
        if node.get("type") == REF_TYPE:
            cid = str(node.get("component_id") or "")
            comp = components_by_id.get(cid)
            if not isinstance(comp, dict):
                logger.info("ui_designer: ref %r has no live component — dropped", cid)
                return None
            comp = copy.deepcopy(comp)
            comp["component_id"] = cid
            if depth > 0:
                attrs = dict(comp.get("attributes") or {})
                attrs["data-component-id"] = cid
                comp["attributes"] = attrs
            return comp
        node = dict(node)
        for key in _CHILD_KEYS:
            nested = node.get(key)
            if isinstance(nested, list):
                node[key] = [w for w in (walk(c, depth + 1) for c in nested) if w is not None]
        tabs = node.get("tabs")
        if isinstance(tabs, list):
            new_tabs = []
            for tab in tabs:
                if isinstance(tab, dict):
                    tab = dict(tab)
                    content = tab.get("content")
                    if isinstance(content, list):
                        tab["content"] = [w for w in (walk(c, depth + 1) for c in content) if w is not None]
                new_tabs.append(tab)
            node["tabs"] = new_tabs
        return node

    return [w for w in (walk(n, 0) for n in (layout or [])) if w is not None]


# ───────────────────────────── driver ────────────────────────────────────────

async def design_round(
    *,
    user_request: str,
    round_components: Sequence[Dict[str, Any]],
    canvas_rows: Sequence[Dict[str, Any]],
    chat_id: str,
    layout_key: str,
    allowed_types: Set[str],
    llm_call: Callable[[List[Dict[str, str]]], Awaitable[Optional[str]]],
    timeout_s: Optional[float] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Run one design pass; return the validated arrangement or ``None``.

    ``None`` ALWAYS means "fall back to the legacy flat append" — every
    failure mode (LLM error, timeout, refusal, unparseable/invalid output)
    is logged with a structured reason and swallowed (FR-022 fail-open).
    """
    budget = timeout_s if timeout_s is not None else designer_timeout_seconds()
    round_ids = [c.get("component_id") for c in round_components
                 if isinstance(c, dict) and c.get("component_id")]
    canvas_ids = {r.get("component_id") for r in (canvas_rows or []) if r.get("component_id")}
    allowed_refs = set(round_ids) | canvas_ids

    logger.info("ui_designer.invoked chat=%s components=%d budget_s=%.1f",
                chat_id, len(round_ids), budget)
    started = time.monotonic()

    def _fallback(reason: str, detail: str = "") -> None:
        latency_ms = int((time.monotonic() - started) * 1000)
        logger.warning("ui_designer.fallback chat=%s reason=%s latency_ms=%d %s",
                       chat_id, reason, latency_ms, detail)

    try:
        messages = build_design_messages(user_request, round_components, canvas_rows, allowed_types)
        content = await asyncio.wait_for(llm_call(messages), timeout=budget)
    except asyncio.TimeoutError:
        _fallback("timeout", f"budget_s={budget}")
        return None
    except Exception as e:  # LLM/transport errors — fail open, never up.
        _fallback("llm_error", str(e))
        return None

    if not content:
        _fallback("llm_error", "empty response")
        return None

    try:
        layout = parse_design_response(content)
    except DesignRejected as e:
        _fallback(e.reason, str(e))
        return None

    layout, referenced = validate_layout(layout, allowed_refs, allowed_types)
    layout = repair_layout(layout, referenced, round_ids)
    if not layout:
        _fallback("invalid", "layout empty after validation")
        return None
    layout = stamp_garnish_ids(layout, chat_id, layout_key)

    garnish_count = sum(1 for n in layout if n.get("type") != REF_TYPE)
    latency_ms = int((time.monotonic() - started) * 1000)
    logger.info("ui_designer.designed chat=%s layout_key=%s refs=%d garnish=%d latency_ms=%d",
                chat_id, layout_key, len(set(iter_refs(layout))), garnish_count, latency_ms)
    return layout


def iter_refs(layout: Sequence[Dict[str, Any]]):
    """Yield referenced component ids (delegates to the workspace walker)."""
    from orchestrator.workspace import iter_layout_refs
    yield from iter_layout_refs(list(layout))
