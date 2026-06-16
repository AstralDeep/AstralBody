"""Feature 029 — the adaptive UI designer (contracts/ui-designer-llm.md).

After a chat round produces two or more rich components, the designer runs a
bounded multi-round LLM conversation that produces an *arrangement*: a layout
tree built ONLY from existing astralprims types whose leaves REFERENCE the
round's workspace components by ``component_id``
(``{"type": "ref", "component_id": ...}``). The first pass drafts the
arrangement; while rounds remain (``UI_DESIGNER_MAX_ROUNDS``, default 3) the
designer is shown its own current arrangement and asked to critique and
improve it — replying ``DONE`` ends the loop early, and any failed refinement
keeps the best arrangement so far. A first pass that produces unusable JSON
gets bounded format-retries with the failure reason fed back.

Tool-produced content is never rewritten, merged, or dropped — identities,
in-place refresh, pagination and supersede semantics survive intact (the
hybrid model the spec mandates). The designer may add its own "garnish"
(headline metrics, narrative text, grouping containers) with deterministic
``dg_*`` ids so re-designs update rather than duplicate.

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

#: Designer per-pass time budget default; operator override via UI_DESIGNER_TIMEOUT_SECONDS.
DEFAULT_TIMEOUT_SECONDS = 8.0

#: Max LLM passes per design (1 draft + refinements/format-retries);
#: operator override via UI_DESIGNER_MAX_ROUNDS. 1 == legacy single pass.
DEFAULT_MAX_ROUNDS = 3

REF_TYPE = "ref"
GARNISH_ID_PREFIX = "dg_"

#: Container keys the validator/materializer walk (matches the orchestrator's
#: ``_validate_component_tree`` traversal plus tabs items).
_CHILD_KEYS = ("children", "content")

#: Bounds keeping the prompt affordable on big rounds.
_MAX_REQUEST_CHARS = 1000
_MAX_COMPONENT_EXCERPT_CHARS = 1500
_MAX_CANVAS_LINES = 30
_MAX_SKETCH_LINES = 60
_MAX_LAYOUT_JSON_CHARS = 4000


def designer_enabled() -> bool:
    """FF_UI_DESIGNER feature flag (default ON; FR-029)."""
    return os.getenv("FF_UI_DESIGNER", "true").strip().lower() not in ("0", "false", "no", "off")


def designer_timeout_seconds() -> float:
    """Operator-configurable per-pass design budget (FR-023)."""
    raw = os.getenv("UI_DESIGNER_TIMEOUT_SECONDS", "")
    try:
        value = float(raw)
        return value if value > 0 else DEFAULT_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS


def designer_max_rounds() -> int:
    """Operator-configurable pass cap; total wall clock ≤ budget × rounds."""
    raw = os.getenv("UI_DESIGNER_MAX_ROUNDS", "")
    try:
        value = int(raw)
        return value if value >= 1 else DEFAULT_MAX_ROUNDS
    except (TypeError, ValueError):
        return DEFAULT_MAX_ROUNDS


def scorer_enabled() -> bool:
    """FF_UI_DESIGNER_SCORER feature flag (default ON; feature 033 C-U1).

    When on, :func:`design_round` returns the highest-`score_arrangement`
    arrangement among the LLM's draft + refinements ("LLM proposes, code
    decides") instead of merely the last one the conversation settled on.
    Strictly fail-open: any scoring error reverts to the legacy last-wins
    selection, so the flag never reduces reliability.
    """
    return os.getenv("FF_UI_DESIGNER_SCORER", "true").strip().lower() not in ("0", "false", "no", "off")


def should_design(round_components: Sequence[Dict[str, Any]], *, timeline_mode: bool = False) -> bool:
    """Invocation predicate: flag ∧ ≥2 rich components ∧ not viewing history."""
    if timeline_mode or not designer_enabled():
        return False
    rich = [c for c in round_components if isinstance(c, dict) and c.get("type")]
    return len(rich) >= MIN_DESIGN_COMPONENTS


# ───────────────────────────── prompt ────────────────────────────────────────

_LAYOUT_GUIDANCE = """LAYOUT VOCABULARY (compose freely from these astralprims types):
- {"type": "ref", "component_id": "<id>"} — places one of the round's components. THE ONLY way to include tool output.
- "hero": {"type": "hero", "title": "...", "subtitle": "...", "eyebrow": "...", "variant": "default|gradient|subtle", "badges": ["..."]} — ONE anchoring masthead at the top of dashboard/report rounds.
- "grid": {"type": "grid", "columns": 2, "children": [...]} — side-by-side groups (2-3 columns max).
- "card": {"type": "card", "title": "...", "content": [...]} — titled grouping with an accent bar.
- "tabs": {"type": "tabs", "tabs": [{"label": "...", "content": [...]}]} — alternate views of related detail.
- "collapsible": {"type": "collapsible", "title": "...", "content": [...], "default_open": false} — secondary detail.
- "text": {"type": "text", "content": "...", "variant": "h2|h3|body|caption|markdown"} — short connective narrative.
- "metric": {"type": "metric", "title": "...", "value": "...", "subtitle": "...", "variant": "default|success|warning|error"} — headline takeaway.
- "keyvalue": {"type": "keyvalue", "title": "...", "items": [{"label": "...", "value": "...", "hint": "..."}], "columns": 2} — compact fact sheet.
- "timeline": {"type": "timeline", "title": "...", "items": [{"time": "...", "title": "...", "description": "...", "variant": "default|success|warning|error|info"}]} — schedules and event sequences.
- "badge": {"type": "badge", "label": "...", "variant": "default|success|warning|error|info|accent"} — small status chip.
- "rating": {"type": "rating", "value": 4.5, "max_value": 5, "label": "..."} — star score.
- "alert", "divider", "list", "progress" — as in the standard palette.

DESIGN RULES:
1. Reference EVERY round component exactly once via a "ref" node. Never copy, rewrite, or summarize their internal data — place them.
2. Lead with a visual anchor: a hero masthead for dashboard/report rounds, or a headline metric/one-line takeaway when the data supports one.
3. Establish hierarchy: headline strip first (metrics/ratings in a 2-4 column grid), main visuals next (charts/tables side-by-side in grids, max 3 columns), raw or secondary detail last (collapsibles/tabs).
4. Give every card/tabs/collapsible a meaningful title — small screens flatten layouts to titles and text.
5. Garnish must be brief and grounded ONLY in the component digests shown; never invent numbers or facts.
6. Vary the texture: never stack a run of same-type components; break them up with metrics, badges, keyvalue rows or grids.
7. Output ONLY JSON: {"layout": [ ...nodes... ]}. No markdown fences, no commentary.
8. If the components genuinely cannot be improved by arrangement, reply exactly: ERROR: <brief reason>."""


_REFINE_GUIDANCE = """REVIEW CHECKLIST — judge the CURRENT ARRANGEMENT against it:
1. Anchor — does the round open with a hero masthead or headline takeaway?
2. Hierarchy — headline strip, then main visuals, then secondary detail; is anything important buried, or anything trivial leading?
3. Balance — are charts/tables grouped side-by-side in grids instead of one full-width stack? Do grids avoid lonely single cells?
4. Scannability — meaningful titles everywhere; garnish brief and grounded in the digests?
5. Texture — are runs of identical component types broken up?

RESPONSE FORMAT:
- If the arrangement can be meaningfully improved, output ONLY the complete improved JSON {"layout": [ ...nodes... ]} — same rules as before: reference every round component exactly once via "ref" nodes, garnish grounded only in the digests.
- Keep EVERY component the current arrangement references (including any marked "(canvas)") — an improved layout that loses one is rejected.
- If the arrangement is already well-designed, reply exactly: DONE"""


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


def _layout_sketch(
    layout: Sequence[Any],
    labels_by_id: Dict[str, str],
    indent: int = 0,
) -> List[str]:
    """Indented structural outline of an arrangement — the 'current UI' the
    refinement pass critiques. Refs resolve to component type/title labels."""
    lines: List[str] = []
    for node in layout:
        if not isinstance(node, dict):
            continue
        pad = "  " * indent
        ntype = str(node.get("type", "?"))
        if ntype == REF_TYPE:
            cid = str(node.get("component_id") or "?")
            lines.append(f"{pad}- [component {cid}] {labels_by_id.get(cid, 'unknown')}")
            continue
        bits = [ntype]
        if node.get("title"):
            bits.append(f'title="{str(node["title"])[:60]}"')
        if ntype == "grid":
            bits.append(f"columns={node.get('columns', 2)}")
        if ntype == "text":
            bits.append(f'content="{str(node.get("content", ""))[:80]}"')
        if ntype == "metric":
            bits.append(f'value="{str(node.get("value", ""))[:40]}"')
        lines.append(f"{pad}- {' '.join(bits)}")
        for key in _CHILD_KEYS:
            nested = node.get(key)
            if isinstance(nested, list):
                lines.extend(_layout_sketch(nested, labels_by_id, indent + 1))
        tabs = node.get("tabs")
        if isinstance(tabs, list):
            for tab in tabs:
                if isinstance(tab, dict):
                    lines.append(f'{pad}  - tab "{str(tab.get("label", ""))[:60]}"')
                    content = tab.get("content")
                    if isinstance(content, list):
                        lines.extend(_layout_sketch(content, labels_by_id, indent + 2))
    return lines


def build_refine_messages(
    user_request: str,
    current_layout: Sequence[Dict[str, Any]],
    round_components: Sequence[Dict[str, Any]],
    canvas_rows: Sequence[Dict[str, Any]],
    allowed_types: Set[str],
) -> List[Dict[str, str]]:
    """Build the critique/improve messages for one refinement pass."""
    request = (user_request or "").strip()
    if len(request) > _MAX_REQUEST_CHARS:
        request = request[:_MAX_REQUEST_CHARS] + "…"

    digests = "\n".join(_component_digest(c) for c in round_components if isinstance(c, dict))

    # Canvas components first so this round's richer labels win on collision —
    # a draft may legitimately place prior-round canvas refs and the sketch
    # must not present them as "unknown".
    labels_by_id = {
        str(r.get("component_id")): f"{r.get('component_type', '?')} — {r.get('title') or 'untitled'} (canvas)"
        for r in (canvas_rows or [])
        if isinstance(r, dict) and r.get("component_id")
    }
    labels_by_id.update({
        str(c.get("component_id")): f"{c.get('type', '?')} — {c.get('title') or 'untitled'}"
        for c in round_components
        if isinstance(c, dict) and c.get("component_id")
    })
    sketch_lines = _layout_sketch(current_layout, labels_by_id)
    if len(sketch_lines) > _MAX_SKETCH_LINES:
        sketch_lines = sketch_lines[:_MAX_SKETCH_LINES] + ["  …(truncated)"]
    layout_json = json.dumps(list(current_layout), default=str)
    if len(layout_json) > _MAX_LAYOUT_JSON_CHARS:
        layout_json = layout_json[:_MAX_LAYOUT_JSON_CHARS] + "…(truncated)"

    palette = ", ".join(sorted(allowed_types))
    user_prompt = f"""USER REQUEST FOR THIS ROUND:
{request or '(not provided)'}

THIS ROUND'S COMPONENTS (each must appear exactly once via a ref node):
{digests}

CURRENT ARRANGEMENT (structural outline):
{chr(10).join(sketch_lines)}

CURRENT ARRANGEMENT (JSON):
{layout_json}

FULL ALLOWED TYPE PALETTE: {palette}

{_LAYOUT_GUIDANCE}

{_REFINE_GUIDANCE}"""

    return [
        {
            "role": "system",
            "content": (
                "You are an expert interface designer for a server-driven UI. "
                "You critique your own arrangements and improve them. "
                "Output ONLY valid JSON, the single word DONE, or an ERROR message."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]


def _is_done_reply(content: str) -> bool:
    """True when a refinement pass declares the arrangement finished."""
    text = (content or "").strip()
    if text.startswith("```"):
        # Drop fence lines (including language-tagged openers like ```json).
        text = "\n".join(
            ln for ln in text.splitlines() if not ln.strip().startswith("```")
        ).strip()
    return text.upper().rstrip(".!").strip() == "DONE"


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


#: Types whose children/content (or tabs) the renderer actually renders.
#: Refs nested anywhere else would be CLAIMED by the layout but never reach
#: the DOM — a silent FR-018 visual drop — so the validator strips them and
#: lets omission repair re-append the refs flat.
_STRUCTURAL_TYPES = frozenset({"container", "card", "grid", "collapsible"})


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
    - non-structural leaf types lose list-valued ``children``/``content``/
      ``tabs`` so they cannot invisibly swallow refs.
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
            node["type"] = ntype = "container"
        structural = ntype in _STRUCTURAL_TYPES or not ntype
        for key in _CHILD_KEYS:
            nested = node.get(key)
            if not isinstance(nested, list):
                continue
            if structural:
                node[key] = [w for w in (walk(c) for c in nested) if w is not None]
            else:
                logger.info("ui_designer: stripping nested %s from leaf type %r", key, ntype)
                node.pop(key)
        tabs = node.get("tabs")
        if isinstance(tabs, list):
            if ntype != "tabs":
                logger.info("ui_designer: stripping tabs from non-tabs type %r", ntype)
                node.pop("tabs")
            else:
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
    seen = set(referenced)
    missing = [cid for cid in dict.fromkeys(round_ids_in_order) if cid not in seen]
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


# ───────────────────────────── score ─────────────────────────────────────────
# Feature 033 (capability C-U1): the designer's DESIGN RULES (see
# _LAYOUT_GUIDANCE) were enforced ONLY by the LLM's own free-text self-critique,
# which the generative-UI literature (Draco / DracoGPT; Stanford Generative
# Interfaces) shows is unreliable and unmeasurable. This deterministic scorer
# turns those rules into a numeric objective so the LLM PROPOSES arrangements
# and pure-Python code DECIDES which to keep. Higher is better. The function is
# pure and must never raise (callers still wrap it fail-open).

_ANCHOR_TYPES = frozenset({"hero", "metric"})
_HEADLINE_TYPES = frozenset({"metric", "rating", "badge"})
_SCORE_CONTAINERS = frozenset({"grid", "card", "tabs", "collapsible", "container"})
_TITLED_CONTAINERS = frozenset({"card", "tabs", "collapsible"})

#: Scoring weights — tunable; chosen to mirror the numbered DESIGN RULES.
W_ANCHOR = 2.0              # rule 2: lead with a hero/headline anchor
W_HEADLINE_NEAR_TOP = 1.0   # rule 3: headline takeaway high in the hierarchy
W_GRID_GROUPED = 0.5        # rule 3: grids that actually group ≥2 things
W_GRID_LONELY = -1.0        # rule 3: a grid wrapping a single cell is noise
W_TITLED_CONTAINER = 0.25   # rule 4: meaningful titles everywhere
W_UNTITLED_CONTAINER = -0.75
W_SAME_TYPE_ADJACENT = -0.5  # rule 6: don't stack runs of identical types
W_WALL_OF_COMPONENTS = -1.5  # rule 3: many ungrouped top-level nodes = a wall
W_GROUPING_PRESENT = 0.5     # rule 3: at least one grouping container present
WALL_THRESHOLD = 6


def _texture_key(node: Dict[str, Any], ref_types: Optional[Dict[str, str]]) -> str:
    """Identity used for run-of-same-type detection. A ``ref`` resolves to the
    referenced component's real type when known (so a table+chart pair is not
    mistaken for a same-type run); an unknown ref gets a unique key (no penalty)."""
    t = str(node.get("type", "")).strip().lower()
    if t == REF_TYPE:
        cid = str(node.get("component_id") or "")
        rt = (ref_types or {}).get(cid)
        return f"ref:{rt}" if rt else f"ref:{cid or id(node)}"
    return t


def _score_siblings(
    siblings: Sequence[Any],
    ref_types: Optional[Dict[str, str]],
    acc: List[float],
) -> None:
    """Accumulate texture + container scores over one sibling list, recursing
    into structural children (mirrors the validator's traversal)."""
    prev_key: Optional[str] = None
    for node in siblings:
        if not isinstance(node, dict):
            prev_key = None
            continue
        ntype = str(node.get("type", "")).strip().lower()
        key = _texture_key(node, ref_types)
        if prev_key is not None and key == prev_key:
            acc[0] += W_SAME_TYPE_ADJACENT
        prev_key = key

        if ntype == "grid":
            children = [c for c in (node.get("children") or []) if isinstance(c, dict)]
            acc[0] += W_GRID_GROUPED if len(children) >= 2 else W_GRID_LONELY
        if ntype in _TITLED_CONTAINERS:
            title = node.get("title")
            acc[0] += W_TITLED_CONTAINER if (isinstance(title, str) and title.strip()) else W_UNTITLED_CONTAINER

        for ckey in _CHILD_KEYS:
            nested = node.get(ckey)
            if isinstance(nested, list):
                _score_siblings(nested, ref_types, acc)
        tabs = node.get("tabs")
        if isinstance(tabs, list):
            for tab in tabs:
                if isinstance(tab, dict) and isinstance(tab.get("content"), list):
                    _score_siblings(tab["content"], ref_types, acc)


def score_arrangement(
    layout: Sequence[Any],
    *,
    ref_types: Optional[Dict[str, str]] = None,
    allowed_types: Optional[Set[str]] = None,
) -> float:
    """Deterministically score a (validated, pre-materialize) arrangement.

    Args:
        layout: the layout node list (``ref`` leaves + garnish nodes).
        ref_types: optional ``component_id -> component type`` map so ``ref``
            leaves can be scored by the real type they place (texture rule).
        allowed_types: accepted for forward-compatibility; unused today.

    Returns:
        A float; higher means a better arrangement by the designer's own rules.
        Never raises — returns ``0.0`` for empty/degenerate input.
    """
    if not isinstance(layout, list) or not layout:
        return 0.0
    top = [n for n in layout if isinstance(n, dict)]
    if not top:
        return 0.0
    acc: List[float] = [0.0]

    first_type = str(top[0].get("type", "")).strip().lower()
    if first_type in _ANCHOR_TYPES:
        acc[0] += W_ANCHOR
    for node in top[:2]:
        if str(node.get("type", "")).strip().lower() in _HEADLINE_TYPES:
            acc[0] += W_HEADLINE_NEAR_TOP
            break
    if any(str(n.get("type", "")).strip().lower() in ("grid", "card") for n in top):
        acc[0] += W_GROUPING_PRESENT
    has_structural_top = any(
        str(n.get("type", "")).strip().lower() in _SCORE_CONTAINERS for n in top
    )
    if len(top) > WALL_THRESHOLD and not has_structural_top:
        acc[0] += W_WALL_OF_COMPONENTS

    _score_siblings(top, ref_types, acc)
    return round(acc[0], 4)


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
    max_rounds: Optional[int] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Run a bounded multi-round design conversation; return the validated
    arrangement or ``None``.

    Pass 1 drafts the arrangement. While passes remain, the designer critiques
    its own current arrangement and either improves it or replies ``DONE``.
    A draft pass that produces unusable JSON gets format-retries with the
    failure fed back; once any arrangement is valid, every later failure
    simply keeps the best arrangement so far.

    ``None`` ALWAYS means "fall back to the legacy flat append" — a first
    pass that yields no usable arrangement (LLM error, timeout, refusal,
    unparseable/invalid output, retries exhausted) is logged with a
    structured reason and swallowed (FR-022 fail-open).
    """
    budget = timeout_s if timeout_s is not None else designer_timeout_seconds()
    rounds = max_rounds if max_rounds is not None else designer_max_rounds()
    rounds = max(1, rounds)
    round_ids = [c.get("component_id") for c in round_components
                 if isinstance(c, dict) and c.get("component_id")]
    canvas_ids = {r.get("component_id") for r in (canvas_rows or []) if r.get("component_id")}
    allowed_refs = set(round_ids) | canvas_ids

    logger.info("ui_designer.invoked chat=%s components=%d budget_s=%.1f max_rounds=%d",
                chat_id, len(round_ids), budget, rounds)
    started = time.monotonic()

    def _fallback(reason: str, detail: str = "") -> None:
        latency_ms = int((time.monotonic() - started) * 1000)
        logger.warning("ui_designer.fallback chat=%s reason=%s latency_ms=%d %s",
                       chat_id, reason, latency_ms, detail)

    # Feature 033 (C-U1): LLM proposes, deterministic scorer decides. Track the
    # highest-scoring arrangement across the draft + refinements and return it
    # instead of merely the last one the conversation settled on. Fail-open: any
    # scoring error (or the flag off) leaves best_* unset → final == current.
    use_scorer = scorer_enabled()
    ref_types: Dict[str, str] = {}
    for _c in round_components:
        if isinstance(_c, dict) and _c.get("component_id"):
            ref_types[str(_c["component_id"])] = str(_c.get("type") or "")
    for _r in (canvas_rows or []):
        if isinstance(_r, dict) and _r.get("component_id"):
            ref_types.setdefault(str(_r["component_id"]), str(_r.get("component_type") or ""))
    best_layout: Optional[List[Dict[str, Any]]] = None
    best_score: Optional[float] = None

    def _consider(candidate: List[Dict[str, Any]]) -> None:
        nonlocal best_layout, best_score
        if not use_scorer:
            return
        try:
            s = score_arrangement(candidate, ref_types=ref_types, allowed_types=allowed_types)
        except Exception:
            logger.debug("ui_designer: score_arrangement failed — keeping last-wins", exc_info=True)
            return
        if best_score is None or s > best_score:
            best_layout, best_score = candidate, s

    current: Optional[List[Dict[str, Any]]] = None
    passes_used = 0
    messages = build_design_messages(user_request, round_components, canvas_rows, allowed_types)

    for attempt in range(1, rounds + 1):
        passes_used = attempt
        try:
            content = await asyncio.wait_for(llm_call(messages), timeout=budget)
        except asyncio.TimeoutError:
            if current is None:
                _fallback("timeout", f"budget_s={budget}")
                return None
            logger.info("ui_designer.refine chat=%s round=%d outcome=timeout — keeping best",
                        chat_id, attempt)
            break
        except Exception as e:  # LLM/transport errors — fail open, never up.
            if current is None:
                _fallback("llm_error", str(e))
                return None
            logger.info("ui_designer.refine chat=%s round=%d outcome=llm_error — keeping best",
                        chat_id, attempt)
            break

        if not content:
            if current is None:
                _fallback("llm_error", "empty response")
                return None
            logger.info("ui_designer.refine chat=%s round=%d outcome=empty — keeping best",
                        chat_id, attempt)
            break

        if current is not None and _is_done_reply(content):
            logger.info("ui_designer.refine chat=%s round=%d outcome=done", chat_id, attempt)
            break

        rejection: Optional[Tuple[str, str]] = None
        layout: Optional[List[Dict[str, Any]]] = None
        try:
            parsed = parse_design_response(content)
        except DesignRejected as e:
            rejection = (e.reason, str(e))
        else:
            clean, referenced = validate_layout(parsed, allowed_refs, allowed_types)
            if current is None:
                layout = repair_layout(clean, referenced, round_ids) or None
                if layout is None:
                    rejection = ("invalid", "layout empty after validation")
            else:
                # A refinement must stand on its own: everything the current
                # arrangement places must stay placed. Repair-appending its
                # omissions would silently demote good placements to flat
                # refs (and launder ref-free meta-replies into "layouts"),
                # so an incomplete refinement is rejected instead.
                placed = set(iter_refs(current))
                if clean and placed <= set(referenced):
                    layout = clean
                else:
                    rejection = ("incomplete", "refinement lost placed components")

        if layout is None:
            reason, detail = rejection
            if current is not None:
                # A failed refinement never loses a good arrangement.
                logger.info("ui_designer.refine chat=%s round=%d outcome=rejected:%s — keeping best",
                            chat_id, attempt, reason)
                break
            if reason == "refusal" or attempt >= rounds:
                _fallback(reason, detail)
                return None
            # Draft produced unusable output — feed the failure back (format retry).
            messages = messages + [
                {"role": "assistant", "content": str(content)[:2000]},
                {"role": "user", "content": (
                    f"Your previous response could not be used ({reason}: "
                    f"{detail or 'no detail'}). Reply with ONLY the JSON object "
                    '{"layout": [ ...nodes... ]} following the rules above — no markdown '
                    "fences, no commentary."
                )},
            ]
            continue

        if current is not None and layout == current:
            # The refinement regurgitated the same arrangement — converged.
            logger.info("ui_designer.refine chat=%s round=%d outcome=stable", chat_id, attempt)
            break
        improved = current is not None
        current = layout
        _consider(current)
        if improved:
            logger.info("ui_designer.refine chat=%s round=%d outcome=improved", chat_id, attempt)
        if attempt < rounds:
            messages = build_refine_messages(user_request, current, round_components,
                                             canvas_rows, allowed_types)

    if current is None:
        _fallback("invalid", "no usable arrangement produced")
        return None

    # Feature 033 (C-U1): return the highest-scoring arrangement, not just the
    # last. Scorer off (or any scoring error) → best_layout is None → final=current.
    final = best_layout if (use_scorer and best_layout is not None) else current
    layout = stamp_garnish_ids(final, chat_id, layout_key)

    garnish_count = sum(1 for n in layout if n.get("type") != REF_TYPE)
    latency_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "ui_designer.designed chat=%s layout_key=%s refs=%d garnish=%d rounds=%d "
        "score=%s latency_ms=%d",
        chat_id, layout_key, len(set(iter_refs(layout))), garnish_count, passes_used,
        ("%.3f" % best_score) if best_score is not None else "off", latency_ms,
    )
    return layout


def iter_refs(layout: Sequence[Dict[str, Any]]):
    """Yield referenced component ids (delegates to the workspace walker)."""
    from orchestrator.workspace import iter_layout_refs
    yield from iter_layout_refs(list(layout))
