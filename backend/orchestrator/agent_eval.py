"""Feature 035 (capability 033 C-N5) — the trajectory-evaluation backbone.

The self-improving agent architecture (US3) needs a *measurement* substrate:
the agentic-frameworks literature (Agent-as-a-Judge, arXiv:2410.10934; Google
Vertex/ADK agent evaluation; τ-bench `pass^k`, arXiv:2406.12045) shows quality
must be judged at the *trajectory* level (the ordered sequence of tool calls)
and for *reliability* (does it succeed on all of k trials?), not by a single
final-answer pass/fail.

This module is the deterministic core of that backbone — pure functions over a
trajectory (an ordered sequence of tool calls) compared to a reference, plus the
`pass^k` reliability estimator. It is intentionally dependency-free and
side-effect-free so it can be:

* the metric that grades drafts in the evolutionary auto-create loop (C-N4),
* a `pass^k`-gated upgrade to the single-shot self-test, and
* a regression harness over the existing hash-chained audit/tool-dispatch trace.

A trajectory item may be a bare tool-name string or a dict carrying a
``tool`` / ``name`` / ``tool_name`` key; both normalise to a tool name. No LLM
is required (an LLM judge MAY layer on top, but the deterministic gate never
depends on model availability — the same posture the 033 verification harness
mandates).
"""
from __future__ import annotations

from math import comb
from typing import Any, Dict, List, Sequence, Union

ToolCall = Union[str, Dict[str, Any]]


def _tool_name(call: ToolCall) -> str:
    """Normalise a trajectory item to its tool name."""
    if isinstance(call, str):
        return call
    if isinstance(call, dict):
        return str(call.get("tool") or call.get("name") or call.get("tool_name") or "")
    return str(call)


def _names(trajectory: Sequence[ToolCall]) -> List[str]:
    return [_tool_name(c) for c in (trajectory or [])]


# ───────────────────────── trajectory metrics ────────────────────────────────
# All return a float in [0, 1]; the binary metrics return exactly 0.0 or 1.0.

def trajectory_exact_match(predicted: Sequence[ToolCall], reference: Sequence[ToolCall]) -> float:
    """1.0 iff the predicted tool sequence equals the reference, order included."""
    return 1.0 if _names(predicted) == _names(reference) else 0.0


def trajectory_in_order_match(predicted: Sequence[ToolCall], reference: Sequence[ToolCall]) -> float:
    """1.0 iff every reference tool appears in the predicted sequence in the same
    relative order (extra predicted tools allowed — reference is a subsequence)."""
    pred_iter = iter(_names(predicted))
    return 1.0 if all(name in pred_iter for name in _names(reference)) else 0.0


def trajectory_any_order_match(predicted: Sequence[ToolCall], reference: Sequence[ToolCall]) -> float:
    """1.0 iff every reference tool appears in the predicted sequence (any order)."""
    return 1.0 if set(_names(reference)) <= set(_names(predicted)) else 0.0


def trajectory_precision(predicted: Sequence[ToolCall], reference: Sequence[ToolCall]) -> float:
    """Fraction of the (unique) predicted tools that are in the reference."""
    pred, ref = set(_names(predicted)), set(_names(reference))
    return (len(pred & ref) / len(pred)) if pred else 0.0


def trajectory_recall(predicted: Sequence[ToolCall], reference: Sequence[ToolCall]) -> float:
    """Fraction of the (unique) reference tools that were actually used."""
    pred, ref = set(_names(predicted)), set(_names(reference))
    return (len(pred & ref) / len(ref)) if ref else 0.0


def trajectory_single_tool_use(predicted: Sequence[ToolCall], tool_name: str) -> float:
    """1.0 iff ``tool_name`` is used at least once in the predicted trajectory."""
    return 1.0 if tool_name in set(_names(predicted)) else 0.0


def score_trajectory(predicted: Sequence[ToolCall], reference: Sequence[ToolCall]) -> Dict[str, float]:
    """All six trajectory metrics as a dict (the ADK/Vertex named set)."""
    return {
        "exact_match": trajectory_exact_match(predicted, reference),
        "in_order_match": trajectory_in_order_match(predicted, reference),
        "any_order_match": trajectory_any_order_match(predicted, reference),
        "precision": trajectory_precision(predicted, reference),
        "recall": trajectory_recall(predicted, reference),
    }


#: Default weights for :func:`aggregate_quality` — reward getting the right
#: tools (recall) and ordering (in_order) most; penalise extraneous tools
#: (precision) less. Tunable by callers.
DEFAULT_QUALITY_WEIGHTS: Dict[str, float] = {
    "in_order_match": 0.4, "recall": 0.35, "precision": 0.25,
}


def aggregate_quality(scores: Dict[str, float], weights: Dict[str, float] = None) -> float:
    """Weighted 0–1 quality from a :func:`score_trajectory` dict (the single
    number a self-improving loop optimises). Weights are renormalised over the
    metrics actually present, so a partial score dict still yields a clean [0,1]."""
    w = weights or DEFAULT_QUALITY_WEIGHTS
    present = {k: v for k, v in w.items() if k in scores}
    total = sum(present.values())
    if total <= 0:
        return 0.0
    return round(sum(scores[k] * wt for k, wt in present.items()) / total, 4)


# ───────────────────────── reliability (pass^k) ──────────────────────────────

def pass_hat_k(num_trials: int, num_successes: int, k: int) -> float:
    """τ-bench ``pass^k`` — the probability that a random size-``k`` subset of
    ``num_trials`` independent trials is *all* successes (the unbiased
    combinatorial estimator ``C(c, k) / C(n, k)``).

    Measures *reliability/consistency*, not average success: a flaky agent with
    a high pass^1 can have a low pass^8. Returns 0.0 when there are fewer than
    ``k`` trials or fewer than ``k`` successes.

    Raises:
        ValueError: if ``k`` < 1 or the counts are negative / inconsistent.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    if num_trials < 0 or num_successes < 0 or num_successes > num_trials:
        raise ValueError("require 0 <= num_successes <= num_trials")
    if num_trials < k or num_successes < k:
        return 0.0
    denom = comb(num_trials, k)
    return round(comb(num_successes, k) / denom, 6) if denom else 0.0


def pass_k_from_outcomes(outcomes: Sequence[bool], k: int) -> float:
    """`pass^k` from a list of per-trial boolean outcomes (convenience over
    :func:`pass_hat_k`)."""
    outs = list(outcomes)
    return pass_hat_k(len(outs), sum(1 for o in outs if o), k)
