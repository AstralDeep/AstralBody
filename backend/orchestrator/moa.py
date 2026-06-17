"""Mixture-of-Agents / debate for hard turns — 033 Wave-2 (C-N9).

This module provides difficulty-gated panel logic: for high-stakes or
low-confidence turns, several candidate answers ("proposals") are combined
either by Mixture-of-Agents (MoA) aggregation or by pairwise
debate-then-judge into a single winning proposal.

The module is intentionally PURE and deterministic: there is no database,
no network, and no LLM access here. Any model interaction (e.g. scoring a
proposal or judging a debate) is supplied by the caller as an injected
callable, which keeps this logic trivially testable and provider-agnostic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import reduce
from typing import Callable, List, Optional

__all__ = [
    "Proposal",
    "moa_enabled",
    "should_invoke",
    "aggregate",
    "majority_answer",
    "debate_judge",
    "panel",
]


def moa_enabled() -> bool:
    """Return whether the MoA/debate feature flag is enabled.

    Controlled by the ``FF_MOA_DEBATE`` environment variable. Truthy values
    are ``1``, ``true``, ``yes`` and ``on`` (case-insensitive, surrounding
    whitespace ignored). Anything else — including an unset variable — is
    treated as disabled (fail-closed).
    """
    return os.getenv("FF_MOA_DEBATE", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def should_invoke(
    *,
    difficulty: float,
    confidence: float,
    difficulty_threshold: float = 0.6,
    confidence_threshold: float = 0.5,
) -> bool:
    """Decide whether the expensive panel should run for this turn.

    The panel is reserved for hard turns: it runs only when the turn is at
    least as hard as ``difficulty_threshold`` OR the current answer's
    confidence is at most ``confidence_threshold``. Easy, confident turns
    skip the panel and answer directly.

    Both ``difficulty`` and ``confidence`` are expected in ``[0, 1]``.

    Returns:
        ``True`` when the panel should be invoked, ``False`` otherwise.
    """
    return difficulty >= difficulty_threshold or confidence <= confidence_threshold


@dataclass(frozen=True)
class Proposal:
    """A single candidate answer produced by one agent.

    Attributes:
        agent: Identifier of the agent (or persona) that produced the text.
        text: The candidate answer.
        score: Quality/confidence score used by aggregation and as a
            debate fallback. Higher is better. Defaults to ``0.0``.
    """

    agent: str
    text: str
    score: float = 0.0


def aggregate(proposals: List[Proposal]) -> Proposal:
    """MoA aggregation: return the highest-scoring proposal.

    Ties on ``score`` are broken by order — the earliest proposal in the
    list wins.

    Args:
        proposals: Non-empty list of candidate proposals.

    Returns:
        The single winning proposal.

    Raises:
        ValueError: If ``proposals`` is empty.
    """
    if not proposals:
        raise ValueError("aggregate() requires at least one proposal")
    # max() is stable: on equal scores it keeps the first-seen item, which
    # gives the earliest-wins tie-break we want.
    return max(proposals, key=lambda p: p.score)


def majority_answer(
    proposals: List[Proposal],
    *,
    key: Optional[Callable[[str], str]] = None,
) -> Optional[str]:
    """Return the most common normalized answer text (majority vote).

    Each proposal's ``text`` is normalized via ``key`` before counting. The
    default normalizer strips surrounding whitespace and lower-cases the
    text. The returned value is the *normalized* form of the most frequent
    answer. Ties in frequency are broken by earliest appearance.

    Args:
        proposals: List of candidate proposals (may be empty).
        key: Optional normalizer applied to each ``text``. Defaults to
            ``lambda t: t.strip().lower()``.

    Returns:
        The winning normalized text, or ``None`` if ``proposals`` is empty.
    """
    if not proposals:
        return None

    normalize = key if key is not None else (lambda t: t.strip().lower())

    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for index, proposal in enumerate(proposals):
        normalized = normalize(proposal.text)
        counts[normalized] = counts.get(normalized, 0) + 1
        if normalized not in first_seen:
            first_seen[normalized] = index

    # Highest count wins; tie-break on the earliest first-seen index.
    return min(
        counts,
        key=lambda value: (-counts[value], first_seen[value]),
    )


def debate_judge(
    a: Proposal,
    b: Proposal,
    judge: Callable[[Proposal, Proposal], int],
) -> Proposal:
    """Run a single pairwise debate between two proposals.

    The ``judge`` callable receives ``(a, b)`` and returns an integer:

    * ``-1`` — ``a`` wins,
    * ``1``  — ``b`` wins,
    * ``0``  — tie, resolved in favour of ``a``.

    If the judge raises any exception, the debate falls back to the
    higher-scoring proposal (ties resolved in favour of ``a``).

    Args:
        a: First proposal.
        b: Second proposal.
        judge: Callable deciding the winner.

    Returns:
        The winning proposal.
    """
    try:
        verdict = judge(a, b)
    except Exception:
        # Fallback: defer to score, with `a` winning ties.
        return a if a.score >= b.score else b

    if verdict > 0:
        return b
    # verdict < 0 (a wins) and verdict == 0 (tie -> a) both pick `a`.
    return a


def panel(
    proposals: List[Proposal],
    *,
    judge: Optional[Callable[[Proposal, Proposal], int]] = None,
) -> Proposal:
    """Reduce many proposals to a single winner.

    When a ``judge`` is supplied, run a single-elimination tournament: fold
    the proposals left-to-right, pitting the running winner against each
    next proposal via :func:`debate_judge`. Otherwise, fall back to MoA
    :func:`aggregate` (highest score wins).

    Args:
        proposals: Non-empty list of candidate proposals.
        judge: Optional pairwise judge callable (see :func:`debate_judge`).

    Returns:
        The single winning proposal.

    Raises:
        ValueError: If ``proposals`` is empty.
    """
    if not proposals:
        raise ValueError("panel() requires at least one proposal")

    if judge is None:
        return aggregate(proposals)

    return reduce(lambda winner, nxt: debate_judge(winner, nxt, judge), proposals)
