"""Evolutionary archive-conditioned auto-create + surrogate predictor — 033 Wave-2 (C-N4).

Every generated draft agent's code, self-test score and gap-fingerprint can be
archived. New code generation is then *conditioned* on the top archived
exemplars (the agents that previously scored well for similar gaps), and a
cheap **surrogate** rubric pre-scores a fresh draft from purely static signals
*before* the costly self-test runs, so obviously weak drafts are rejected early.

The module is intentionally PURE and deterministic: there is no database, no
network and no LLM access here. The archive is passed in by the caller as a
plain ``list`` of :class:`ArchivedDraft` records; persistence lives elsewhere.
This keeps the evolutionary logic trivially testable and side-effect free.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import List

__all__ = [
    "ArchivedDraft",
    "archive_enabled",
    "surrogate_score",
    "top_exemplars",
    "condition_prompt",
    "should_skip_self_test",
]


# ───────────────────────────── feature flag ──────────────────────────────────


def archive_enabled() -> bool:
    """Return whether the evolutionary draft-archive feature is enabled.

    Controlled by the ``FF_DRAFT_ARCHIVE`` environment variable. Truthy values
    are ``1``, ``true``, ``yes`` and ``on`` (case-insensitive, surrounding
    whitespace ignored). Anything else — including an unset variable — is
    treated as disabled (fail-closed).
    """
    return os.getenv("FF_DRAFT_ARCHIVE", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# ─────────────────────────────── records ─────────────────────────────────────


@dataclass(frozen=True)
class ArchivedDraft:
    """One archived draft-agent generation outcome.

    Attributes:
        fingerprint: The capability-gap fingerprint the draft was created for.
            Used to measure relevance to a new gap.
        code: The full generated agent source code.
        score: The self-test score the draft achieved, in ``[0, 1]``. Records
            with a non-positive score are treated as failures and are never
            offered back as exemplars.
        created_at: Optional creation timestamp (epoch seconds). Defaults to
            ``0``; used only as informational metadata here.
    """

    fingerprint: str
    code: str
    score: float
    created_at: int = 0


# ───────────────────────────── tokenisation ──────────────────────────────────


def _tokens(fingerprint: str) -> set[str]:
    """Split a fingerprint into a set of lowercase alphanumeric tokens.

    Splitting is on runs of non-alphanumeric characters, so ``read_pdf|v2``
    and ``read-pdf v2`` both yield ``{"read", "pdf", "v2"}``. Empty tokens are
    dropped.
    """
    return {t for t in re.split(r"[^0-9a-zA-Z]+", (fingerprint or "").lower()) if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity of two token sets, in ``[0, 1]``.

    Two empty sets are defined as perfectly dissimilar (``0.0``) so that an
    empty fingerprint never artificially matches everything.
    """
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


# ─────────────────────────── surrogate predictor ─────────────────────────────


# Static red flags that strongly predict self-test failure (or an unsafe agent
# that the security gate would reject). Their mere textual presence is penalised.
_RED_FLAGS: tuple[str, ...] = (
    "eval(",
    "exec(",
    "subprocess",
    "import socket",
    "__import__",
)


def surrogate_score(code: str) -> float:
    """Cheaply predict self-test success from STATIC signals, in ``[0, 1]``.

    This is a deterministic rubric — it never executes ``code`` — that
    approximates how likely a draft is to pass the expensive self-test. It is
    used to reject hopeless drafts early (see :func:`should_skip_self_test`).

    Rubric (additive rewards, then multiplicative red-flag penalty):

    * Empty / very short code scores ``0.0`` outright (nothing to run).
    * ``+0.25`` — registers a tool (defines/uses ``TOOL_REGISTRY`` or a
      ``register_tool`` / ``@tool`` style registration).
    * ``+0.20`` — contains a docstring (a triple-quoted string).
    * ``+0.20`` — returns something component-shaped (``return {`` / ``.to_dict``
      / ``create_ui_response`` / mentions ``components``).
    * ``+0.15`` — guards work with ``try`` / ``except``.
    * ``+0.20`` — reasonable length (roughly 200–8000 chars of real code).
    * Each distinct red flag present (``eval(``, ``exec(``, ``subprocess``,
      ``import socket``, ``__import__``) multiplies the running reward by
      ``0.5`` — several red flags compound toward zero.

    The result is clamped to ``[0, 1]``.

    Args:
        code: Candidate agent source code.

    Returns:
        A score in ``[0, 1]``; higher means more likely to pass self-test.
    """
    text = code or ""
    stripped = text.strip()

    # Nothing meaningful to evaluate — guaranteed failure.
    if len(stripped) < 20:
        return 0.0

    lowered = text.lower()
    score = 0.0

    # Reward: registers a tool.
    if (
        "tool_registry" in lowered
        or "register_tool" in lowered
        or re.search(r"@\w*tool\b", lowered) is not None
    ):
        score += 0.25

    # Reward: has a docstring (any triple-quoted block).
    if '"""' in text or "'''" in text:
        score += 0.20

    # Reward: returns a dict / components.
    if (
        re.search(r"return\s*\{", text) is not None
        or ".to_dict" in lowered
        or "create_ui_response" in lowered
        or "components" in lowered
    ):
        score += 0.20

    # Reward: defensive error handling.
    if re.search(r"\btry\b", text) is not None and re.search(r"\bexcept\b", text) is not None:
        score += 0.15

    # Reward: reasonable length (not a stub, not a runaway blob).
    n = len(stripped)
    if 200 <= n <= 8000:
        score += 0.20
    elif 80 <= n < 200:
        # Short but plausible — partial credit.
        score += 0.10

    # Penalty: each distinct red flag halves the running reward.
    for flag in _RED_FLAGS:
        if flag in lowered:
            score *= 0.5

    return _clamp01(score)


def _clamp01(value: float) -> float:
    """Clamp ``value`` to the closed unit interval ``[0, 1]``.

    Non-finite inputs (``nan``/``inf``) collapse to ``0.0`` so callers always
    receive a usable score.
    """
    if not math.isfinite(value):
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def should_skip_self_test(code: str, *, min_score: float = 0.25) -> bool:
    """Return whether the expensive self-test should be skipped (cheap-reject).

    When the :func:`surrogate_score` of ``code`` falls below ``min_score`` the
    draft is predicted to fail, so the caller can reject it without paying for
    a full self-test run.

    Args:
        code: Candidate agent source code.
        min_score: Inclusive lower bound the surrogate score must meet to be
            worth testing. Defaults to ``0.25``.

    Returns:
        ``True`` to skip (predicted failure), ``False`` to proceed to the
        real self-test.
    """
    return surrogate_score(code) < min_score


# ───────────────────────── exemplar selection ────────────────────────────────


def top_exemplars(
    archive: List[ArchivedDraft],
    fingerprint: str,
    *,
    k: int = 3,
) -> List[ArchivedDraft]:
    """Return up to ``k`` archived drafts most relevant to ``fingerprint``.

    Relevance is ranked by, in order:

    1. Fingerprint-token overlap (Jaccard) with ``fingerprint``, descending.
    2. The draft's self-test ``score``, descending.

    Only successful exemplars are eligible: any record with ``score <= 0`` is
    excluded entirely. Ranking is deterministic — ties beyond the two keys are
    broken by the record's original position in ``archive``.

    Args:
        archive: All archived drafts to choose from.
        fingerprint: The capability-gap fingerprint of the new draft.
        k: Maximum number of exemplars to return. Non-positive ``k`` yields an
            empty list.

    Returns:
        Up to ``k`` :class:`ArchivedDraft` records, best first.
    """
    if k <= 0:
        return []

    target = _tokens(fingerprint)
    candidates = [d for d in archive if d.score > 0.0]

    # Stable sort by descending (overlap, score); Python's sort is stable, so
    # equal-key records retain their original archive order.
    ranked = sorted(
        candidates,
        key=lambda d: (_jaccard(target, _tokens(d.fingerprint)), d.score),
        reverse=True,
    )
    return ranked[:k]


# ───────────────────────── prompt conditioning ───────────────────────────────


_EXEMPLAR_HEADER = "## Exemplars from past successful agents"


def condition_prompt(
    base_prompt: str,
    exemplars: List[ArchivedDraft],
    *,
    max_chars: int = 4000,
) -> str:
    """Append an exemplar section embedding past successful agent code.

    The appended section is bounded: every exemplar's code is truncated as
    needed so the *entire appended block* (header plus all exemplars) stays
    within ``max_chars`` characters. Exemplars are emitted in the order given
    (callers should pass them best-first, e.g. from :func:`top_exemplars`).

    If ``exemplars`` is empty — or ``max_chars`` leaves no room for content —
    ``base_prompt`` is returned unchanged.

    Args:
        base_prompt: The original code-generation prompt.
        exemplars: Successful drafts to show the model, best first.
        max_chars: Hard upper bound on the *appended* section length.

    Returns:
        ``base_prompt`` with the exemplar section appended, or ``base_prompt``
        unchanged when there is nothing to add.
    """
    if not exemplars or max_chars <= 0:
        return base_prompt

    # Build the appended block incrementally, never exceeding max_chars.
    parts: List[str] = ["\n\n" + _EXEMPLAR_HEADER + "\n"]
    used = len(parts[0])

    appended_any = False
    for idx, ex in enumerate(exemplars, start=1):
        # Per-exemplar scaffolding (label + fenced code block).
        prefix = f"\n### Exemplar {idx} (score {ex.score:.2f})\n```python\n"
        suffix = "\n```\n"
        scaffold = len(prefix) + len(suffix)

        remaining = max_chars - used - scaffold
        if remaining <= 0:
            # No room for even an empty body for this (or any further) exemplar.
            break

        body = ex.code or ""
        if len(body) > remaining:
            body = body[:remaining]

        block = prefix + body + suffix
        parts.append(block)
        used += len(block)
        appended_any = True

    if not appended_any:
        return base_prompt

    return base_prompt + "".join(parts)
