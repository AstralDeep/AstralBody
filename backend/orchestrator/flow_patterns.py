"""Security-by-construction flow patterns — 033 Wave-4 (C-S1).

Each conversational turn is routed to a *minimal, safe-by-construction* flow
pattern, and the pattern itself constrains what the turn is even allowed to do
— rather than relying on a downstream gate to notice a bad action after the
fact:

* a **read-only** turn (a question / lookup) → context-minimization plus an
  action-selector: it gets at most one tool call and is never handed a free
  tool loop;
* a **multi-tool** turn (an explicit multi-step request, or one the caller
  already resolved to ≥2 tools) → plan-then-execute: a plan is required and any
  tool call *not* in the approved plan is refused;
* a **parser** turn (an attachment, or a parse/extract/read-file request) →
  map-reduce: a small, bounded fan of reader calls, no free tool loop.

Pure + deterministic; **stdlib only, no new dependency.** The feature flag
``FF_FLOW_PATTERNS`` (default OFF) gates whether the orchestrator routes turns
through these constraints; the helpers themselves are side-effect-free and can
be unit-tested regardless of the flag.

Classification precedence (most-constrained applicable pattern wins)::

    PARSER  >  MULTI_TOOL  >  READ_ONLY  >  DEFAULT

with the caveat that an attachment *forces* :data:`PARSER` irrespective of the
phrasing of the request.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# ──────────────────────────── feature flag ───────────────────────────────────


def flow_patterns_enabled() -> bool:
    """Return ``True`` when the flow-pattern router is enabled via env.

    Gated by ``FF_FLOW_PATTERNS`` (default OFF). Accepts the usual truthy
    spellings (``1``/``true``/``yes``/``on``, case-insensitive); anything else
    — including unset — is treated as OFF (fail-closed for the new behaviour).
    """
    return os.getenv("FF_FLOW_PATTERNS", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# ──────────────────────────── pattern names ──────────────────────────────────

#: Question / lookup turn — context-minimization + single action-selector.
#: Multi-tool turn — plan-then-execute (refuse out-of-plan tool calls).
#: Parser turn — map-reduce over a bounded fan of reader calls.
#: Fallback when no specialised pattern applies — ordinary bounded tool loop.
READ_ONLY, MULTI_TOOL, PARSER, DEFAULT = "read_only", "multi_tool", "parser", "default"

# Keyword sets used by :func:`classify_flow`. Lower-cased; matched as substrings
# (parser) or as a leading token / phrase (multi-step) against the request.
_PARSER_KEYWORDS = (
    "parse",
    "extract",
    "read file",
    "read-file",
    "read the file",
    "read this file",
    "read my file",
    "read attachment",
    "read the attachment",
)

#: Leading interrogatives / lookup verbs that mark a read-only question.
_LOOKUP_LEADERS = (
    "what",
    "who",
    "when",
    "where",
    "why",
    "how",
    "is",
    "are",
    "does",
    "list",
    "show",
    "find",
)

#: Phrases that mark an explicit multi-step (sequenced) request.
_MULTI_STEP_KEYWORDS = (
    "then",
    "and then",
    "after that",
    "finally",
    "steps",
)


def _first_token(text: str) -> str:
    """Return the lower-cased first alphabetic word of ``text`` (or ``""``)."""
    for raw in text.strip().split():
        token = "".join(ch for ch in raw if ch.isalpha()).lower()
        if token:
            return token
    return ""


def classify_flow(
    request: str,
    *,
    tool_count: int = 0,
    has_attachment: bool = False,
) -> str:
    """Classify a turn into the most-constrained applicable flow pattern.

    Precedence is ``PARSER > MULTI_TOOL > READ_ONLY > DEFAULT`` — we always pick
    the *most constrained* pattern that applies, so a turn that looks like both
    a lookup and a multi-step request is treated as multi-tool, and an
    attachment-bearing turn is always a parser turn.

    Rules:

    * ``has_attachment`` is ``True``, **or** the request mentions a
      parse / extract / read-file keyword → :data:`PARSER` (an attachment forces
      this regardless of phrasing).
    * the request is a question / lookup (first word is one of
      what/who/when/where/why/how/is/are/does/list/show/find, *or* it ends with
      ``"?"``) **and** ``tool_count <= 1`` → :data:`READ_ONLY`.
    * ``tool_count >= 2`` **or** the request mentions a multi-step keyword
      (then / and then / after that / finally / steps) → :data:`MULTI_TOOL`.
    * otherwise → :data:`DEFAULT`.

    :param request: the user's turn text (may be empty).
    :param tool_count: number of tools the caller already resolved for the turn.
    :param has_attachment: whether the turn carries a file attachment.
    """
    text = (request or "").strip()
    low = text.lower()

    # PARSER — highest precedence; an attachment forces it.
    if has_attachment or any(kw in low for kw in _PARSER_KEYWORDS):
        return PARSER

    is_lookup = _first_token(text) in _LOOKUP_LEADERS or low.endswith("?")
    is_multi_step = tool_count >= 2 or any(kw in low for kw in _MULTI_STEP_KEYWORDS)

    # MULTI_TOOL outranks READ_ONLY: a sequenced/multi-tool turn is the more
    # constrained classification even if it is phrased as a question.
    if is_multi_step:
        return MULTI_TOOL

    # READ_ONLY — a lookup that the caller can satisfy with at most one tool.
    if is_lookup and tool_count <= 1:
        return READ_ONLY

    return DEFAULT


# ──────────────────────────── constraints ────────────────────────────────────


@dataclass(frozen=True)
class FlowConstraints:
    """The hard limits a flow pattern imposes on a turn.

    :param pattern: the pattern these constraints belong to.
    :param allow_free_tool_calls: whether the turn may call tools freely (a
        free tool loop). When ``False`` the turn is restricted to an
        action-selector / approved plan / bounded map-reduce fan.
    :param requires_plan: whether an explicit, approved plan is required before
        any tool runs (plan-then-execute).
    :param max_tools: the maximum number of tool invocations the turn may make.
    """

    pattern: str
    allow_free_tool_calls: bool
    requires_plan: bool
    max_tools: int


# Frozen, deterministic constraint table keyed by pattern name.
_CONSTRAINTS = {
    READ_ONLY: FlowConstraints(
        pattern=READ_ONLY,
        allow_free_tool_calls=False,
        requires_plan=False,
        max_tools=1,
    ),
    MULTI_TOOL: FlowConstraints(
        pattern=MULTI_TOOL,
        allow_free_tool_calls=False,
        requires_plan=True,
        max_tools=12,
    ),
    PARSER: FlowConstraints(
        pattern=PARSER,
        allow_free_tool_calls=False,
        requires_plan=False,
        max_tools=4,
    ),
    DEFAULT: FlowConstraints(
        pattern=DEFAULT,
        allow_free_tool_calls=True,
        requires_plan=False,
        max_tools=8,
    ),
}


def constraints_for(pattern: str) -> FlowConstraints:
    """Return the :class:`FlowConstraints` for ``pattern``.

    An unknown pattern falls back to the :data:`DEFAULT` constraints (fail-open
    to ordinary bounded behaviour rather than crashing the turn), but the
    returned object's ``pattern`` field reflects the requested name so callers
    and audit logs can see exactly what was asked for.
    """
    known = _CONSTRAINTS.get(pattern)
    if known is not None:
        return known
    base = _CONSTRAINTS[DEFAULT]
    return FlowConstraints(
        pattern=pattern,
        allow_free_tool_calls=base.allow_free_tool_calls,
        requires_plan=base.requires_plan,
        max_tools=base.max_tools,
    )


# ──────────────────────────── invariants ─────────────────────────────────────


def refuse_out_of_plan(planned_tools: list, called_tool: str) -> bool:
    """Plan-then-execute invariant: should this tool call be **refused**?

    Returns ``True`` (REFUSE) when ``called_tool`` is not one of
    ``planned_tools``. An empty plan refuses *every* tool call — a multi-tool
    turn with no approved plan may run nothing. The comparison is
    case-insensitive and whitespace-insensitive on both sides.

    :param planned_tools: the approved plan (tool names); may be empty.
    :param called_tool: the tool the turn is attempting to invoke.
    """
    target = (called_tool or "").strip().lower()
    allowed = {
        (str(name) or "").strip().lower()
        for name in (planned_tools or [])
    }
    return target not in allowed


def within_tool_budget(pattern: str, tools_used: int) -> bool:
    """Return ``True`` while ``tools_used`` stays within ``pattern``'s budget.

    The budget is inclusive: ``tools_used <= constraints_for(pattern).max_tools``.
    """
    return tools_used <= constraints_for(pattern).max_tools
