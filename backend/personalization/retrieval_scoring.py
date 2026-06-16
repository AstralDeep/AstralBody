"""Feature 036 (capability 033 C-M4) — multi-signal memory retrieval scoring.

Memory recall today is single-signal: ``repository.list_memory`` orders by
``created_at`` (recency) and ``MemoryTools.memory_search`` ranks by raw token
overlap (relevance). The Generative Agents recipe (Park et al., UIST 2023) — the
canonical, still-cited memory-retrieval baseline — combines **recency ×
importance × relevance** as a weighted composite, which beats any single signal.

This module is the pure scoring core: every signal is normalised to [0, 1] and
combined with renormalised weights. It is dependency-free and side-effect-free
so it can rank `memory_item` rows (Postgres, no vector DB) and is trivially
unit-testable. The importance signal reuses the existing ``salience`` column
(and falls back to a source-based floor), so no schema change is required.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

#: Generative-Agents-style weights (recency/importance/relevance). Tunable;
#: renormalised over whatever signals a caller supplies.
DEFAULT_WEIGHTS: Dict[str, float] = {"recency": 0.34, "importance": 0.33, "relevance": 0.33}


def multisignal_enabled() -> bool:
    """FF_MEMORY_MULTISIGNAL feature flag (default ON). When off, callers keep
    their legacy single-signal ranking; when on, scoring uses the composite.
    Fail-open: callers wrap scoring so any error reverts to legacy ranking."""
    return os.getenv("FF_MEMORY_MULTISIGNAL", "true").strip().lower() not in ("0", "false", "no", "off")


def _clamp01(x: float) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if v < 0 else (1.0 if v > 1 else v)


def recency_from_rank(index: int, total: int) -> float:
    """Rank-based recency in [0, 1] — newest (``index`` 0) → 1.0, oldest → ~0.

    Uses position in a recency-sorted list rather than parsing timestamps, so it
    is timezone- and format-robust.
    """
    if total <= 1:
        return 1.0
    return round(1.0 - (index / (total - 1)), 6)


def relevance_from_overlap(overlap: int, query_size: int) -> float:
    """Token-overlap relevance normalised by query size, capped at 1.0."""
    if query_size <= 0:
        return 0.0
    return round(min(1.0, overlap / query_size), 6)


def importance_signal(salience: float = 0.0, source: Optional[str] = None) -> float:
    """Importance in [0, 1]: the row's ``salience`` when set, else a source-based
    floor (explicitly-remembered facts outrank auto-promoted ones)."""
    s = _clamp01(salience)
    if s > 0:
        return s
    src = str(source or "").lower()
    if src == "explicit":
        return 0.7
    if src == "promoted":
        return 0.5
    return 0.5


def multi_signal_score(
    *,
    recency: float,
    importance: float,
    relevance: float,
    weights: Dict[str, float] = None,
) -> float:
    """Weighted composite of the three [0, 1] signals (weights renormalised)."""
    w = weights or DEFAULT_WEIGHTS
    signals = {
        "recency": _clamp01(recency),
        "importance": _clamp01(importance),
        "relevance": _clamp01(relevance),
    }
    total = sum(w.get(k, 0.0) for k in signals)
    if total <= 0:
        return 0.0
    return round(sum(signals[k] * w.get(k, 0.0) for k in signals) / total, 6)


def score_memory_row(row: Dict[str, Any], *, index: int, total: int,
                     overlap: int, query_size: int, weights: Dict[str, float] = None) -> float:
    """Convenience: score one ``memory_item`` dict given its recency rank and
    its token overlap with the query."""
    return multi_signal_score(
        recency=recency_from_rank(index, total),
        importance=importance_signal(row.get("salience", 0.0), row.get("source")),
        relevance=relevance_from_overlap(overlap, query_size),
        weights=weights,
    )
