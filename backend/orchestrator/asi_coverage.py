"""Plan-to-audit persistence + OWASP ASI coverage matrix — 033 Wave-4 (C-S12).

Two deterministic, dependency-free concerns:

Part A — Plan persistence / deviation detection.
    Before an agent executes a tool sequence, the *intended* plan is captured
    via :func:`plan_record` and written to the audit chain. After execution,
    :func:`detect_deviation` compares the intended plan against the tools that
    actually ran, so any drift (unexpected extra calls, skipped steps, or a
    reordered execution of the planned steps) becomes detectable.

Part B — OWASP ASI01–ASI10 agentic-security coverage matrix.
    The OWASP Agentic Security Initiative (ASI) top-10 risks are encoded as
    data, together with the feature-033 capability IDs that mitigate each risk.
    :func:`coverage_report`, :func:`uncovered_risks`, and
    :func:`coverage_ratio` derive their answers purely from that data.

This module is pure: stdlib only, no DB, no network, no LLM.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def asi_coverage_enabled() -> bool:
    """Return True when the ASI-coverage feature flag is enabled.

    Reads ``FF_ASI_COVERAGE`` from the environment and treats the truthy
    spellings ``1``/``true``/``yes``/``on`` (case-insensitive, surrounding
    whitespace ignored) as enabled. Anything else — including an unset
    variable — is disabled (fail-closed).
    """
    return os.getenv("FF_ASI_COVERAGE", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# ---------------------------------------------------------------------------
# Part A — plan persistence / deviation detection
# ---------------------------------------------------------------------------


def plan_record(
    planned_tools: list,
    *,
    request: str = "",
    correlation_id: str = "",
) -> dict:
    """Build the JSON-safe audit record for an intended (pre-execution) plan.

    This is the payload written to the audit chain *before* the agent runs any
    tool, so the recorded intent can later be compared against actual behavior.

    Args:
        planned_tools: The ordered tool identifiers the agent intends to call.
        request: The originating user request (truncated to 500 chars).
        correlation_id: An id tying this plan to its execution / audit trail.

    Returns:
        A dict with only JSON-serializable values:
        ``{"kind", "request", "planned_tools", "correlation_id", "step_count"}``.
    """
    return {
        "kind": "intended_plan",
        "request": request[:500],
        "planned_tools": [str(t) for t in planned_tools],
        "correlation_id": correlation_id,
        "step_count": len(planned_tools),
    }


@dataclass(frozen=True)
class Deviation:
    """Describes how actual execution drifted from the intended plan.

    Attributes:
        extra_calls: Tools that ran but were not in the plan (order preserved,
            de-duplicated).
        skipped_steps: Planned tools that never ran (order preserved,
            de-duplicated).
        out_of_order: True when the planned tools that *did* run appeared in a
            different relative order than the plan specified.
    """

    extra_calls: tuple
    skipped_steps: tuple
    out_of_order: bool


def detect_deviation(planned_tools: list, actual_tools: list) -> Deviation:
    """Compare an intended plan against the tools that actually executed.

    Comparison rules:
      * ``extra_calls`` — every tool in ``actual_tools`` whose value does not
        appear anywhere in ``planned_tools``. Reported in the order first seen
        and de-duplicated.
      * ``skipped_steps`` — every tool in ``planned_tools`` whose value does not
        appear anywhere in ``actual_tools``. Reported in plan order and
        de-duplicated.
      * ``out_of_order`` — restrict ``actual_tools`` to the subsequence of tools
        that are part of the plan, then check whether that subsequence is a
        valid (forward, possibly-skipping) traversal of the plan. If the
        planned tools ran in a different relative order than the plan, this is
        True. Pure extra calls or pure skips alone do not, by themselves, set
        this flag.

    Tool identities are compared by ``str()`` so heterogeneous inputs (e.g.
    plain strings vs. richer objects with stable ``__str__``) line up the same
    way :func:`plan_record` serializes them.

    Args:
        planned_tools: The ordered intended tool identifiers.
        actual_tools: The ordered tool identifiers that actually ran.

    Returns:
        A :class:`Deviation` summarizing the drift.
    """
    planned = [str(t) for t in planned_tools]
    actual = [str(t) for t in actual_tools]

    planned_set = set(planned)
    actual_set = set(actual)

    # extra_calls: actual tools not present anywhere in the plan (dedup, ordered)
    extra_calls: list = []
    seen_extra: set = set()
    for tool in actual:
        if tool not in planned_set and tool not in seen_extra:
            extra_calls.append(tool)
            seen_extra.add(tool)

    # skipped_steps: planned tools that never ran (dedup, ordered by plan)
    skipped_steps: list = []
    seen_skipped: set = set()
    for tool in planned:
        if tool not in actual_set and tool not in seen_skipped:
            skipped_steps.append(tool)
            seen_skipped.add(tool)

    # out_of_order: do the planned tools that DID run honor the plan's order?
    #
    # Build the relative ordering the plan expects (first-occurrence index of
    # each planned tool), then walk the planned tools that actually ran and
    # confirm their plan-indices are non-decreasing. A decrease means a planned
    # step ran before an earlier planned step — i.e. reordering.
    plan_first_index: dict = {}
    for idx, tool in enumerate(planned):
        if tool not in plan_first_index:
            plan_first_index[tool] = idx

    out_of_order = False
    last_index = -1
    for tool in actual:
        if tool not in plan_first_index:
            continue  # extra call — does not affect plan ordering
        idx = plan_first_index[tool]
        if idx < last_index:
            out_of_order = True
            break
        last_index = idx

    return Deviation(
        extra_calls=tuple(extra_calls),
        skipped_steps=tuple(skipped_steps),
        out_of_order=out_of_order,
    )


def has_deviation(d: Deviation) -> bool:
    """Return True when the deviation indicates any drift from the plan."""
    return bool(d.extra_calls) or bool(d.skipped_steps) or bool(d.out_of_order)


# ---------------------------------------------------------------------------
# Part B — OWASP ASI01–ASI10 coverage matrix
# ---------------------------------------------------------------------------

# Ordered ASI risk codes → short title (OWASP Agentic Security Initiative
# top-10 themes). Kept as a tuple of pairs to guarantee ASI01..ASI10 order.
ASI_RISKS: tuple = (
    ("ASI01", "Agent Authorization & Control Hijacking"),
    ("ASI02", "Tool Misuse & Exploitation"),
    ("ASI03", "Memory & Context Poisoning"),
    ("ASI04", "Insecure Agent Orchestration"),
    ("ASI05", "Excessive Agency & Privilege"),
    ("ASI06", "Untrusted Input & Prompt Injection"),
    ("ASI07", "Sensitive Information Disclosure"),
    ("ASI08", "Supply Chain & Generated-Code Risk"),
    ("ASI09", "Identity & Impersonation"),
    ("ASI10", "Insufficient Monitoring & Auditability"),
)

# ASI code → feature-033 capability IDs that mitigate it.
COVERAGE: dict = {
    "ASI01": ["C-S3", "C-S8"],
    "ASI02": ["C-S2", "C-S11"],
    "ASI03": ["C-S9", "C-M6"],
    "ASI04": ["C-S14", "C-N7"],
    "ASI05": ["C-S1", "C-S5"],
    "ASI06": ["C-S4", "C-S5"],
    "ASI07": ["C-S2", "C-S7"],
    "ASI08": ["C-S6", "C-S7"],
    "ASI09": ["C-S8", "C-S14"],
    "ASI10": ["C-S12", "C-S3"],
}


def coverage_report() -> list:
    """Return the full ASI coverage matrix as a list of records.

    Each record is ``{"code", "title", "capabilities", "covered"}`` where
    ``covered`` is True when at least one capability mitigates the risk. The
    list is in ASI01..ASI10 order. ``capabilities`` is a fresh copy so callers
    cannot mutate the module-level :data:`COVERAGE` data.
    """
    report: list = []
    for code, title in ASI_RISKS:
        caps = list(COVERAGE.get(code, []))
        report.append(
            {
                "code": code,
                "title": title,
                "capabilities": caps,
                "covered": bool(caps),
            }
        )
    return report


def uncovered_risks() -> list:
    """Return the ASI codes (ASI01..ASI10 order) that have no capabilities."""
    return [code for code, _title in ASI_RISKS if not COVERAGE.get(code)]


def coverage_ratio() -> float:
    """Return the fraction of ASI risks covered by ≥1 capability, in [0, 1]."""
    total = len(ASI_RISKS)
    if total == 0:
        return 0.0
    covered = sum(1 for _code, _title in ASI_RISKS if COVERAGE.get(_code))
    return covered / total
