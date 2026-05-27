"""Background memory consolidation ("dreaming") scoring + sweep (feature 025).

Pure scoring helpers (unit-testable) plus the integration ``run_sweep`` that
promotes high-signal, recurring, non-PHI short-term signals into durable
memory, re-checking the PHI gate at promotion (FR-027/FR-028) and recording a
human-readable sweep summary (FR-029).
"""
from __future__ import annotations

import math
import time
import uuid
from typing import Any, Dict, List, Optional

_RECENCY_HALF_LIFE_DAYS = 7.0


def score_signal(recall_count: int, last_seen_ms: int, now_ms: int) -> float:
    """Score a short-term signal: frequency + time-decayed recency.

    Higher is stronger. Recency decays with a 7-day half-life so stale one-offs
    fade while recurring recent signals rise.
    """
    age_days = max(0.0, (now_ms - (last_seen_ms or now_ms)) / 86_400_000.0)
    recency = math.pow(0.5, age_days / _RECENCY_HALF_LIFE_DAYS)
    return float(recall_count) + recency


def select_promotions(
    signals: List[Dict[str, Any]],
    now_ms: int,
    *,
    min_recalls: int = 2,
    max_promote: int = 25,
) -> List[Dict[str, Any]]:
    """Pick which signals to promote: recurring (>= min_recalls), top by score.

    Pure function. One-off signals (recall_count < min_recalls) are never
    promoted — that is what keeps durable memory high-signal (SC-011).
    """
    eligible = [s for s in signals if int(s.get("recall_count", 0)) >= min_recalls]
    eligible.sort(
        key=lambda s: score_signal(int(s.get("recall_count", 0)), int(s.get("last_seen_at") or now_ms), now_ms),
        reverse=True,
    )
    return eligible[:max_promote]


def run_sweep(
    repo,
    phi_gate,
    user_id: str,
    *,
    trigger: str = "scheduled",
    min_recalls: int = 2,
    now_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Run one consolidation sweep for ``user_id``; return the sweep record.

    Promotes eligible non-PHI signals into durable memory, re-checking the PHI
    gate at promotion (defense in depth — signals were already gated at
    capture). Consumed signals are deleted; a ``consolidation_sweep`` row is
    written for review.
    """
    now_ms = now_ms or int(time.time() * 1000)
    signals = repo.list_signals(user_id)
    candidates = select_promotions(signals, now_ms, min_recalls=min_recalls)

    promoted = 0
    for sig in candidates:
        value = sig.get("value", "")
        # Defense in depth: never promote anything the gate now flags.
        if phi_gate.contains_phi(value):
            repo.delete_signal(user_id, sig["id"])
            continue
        repo.create_memory(
            user_id, sig["category"], value,
            source="promoted",
            salience=score_signal(int(sig.get("recall_count", 0)), int(sig.get("last_seen_at") or now_ms), now_ms),
        )
        repo.delete_signal(user_id, sig["id"])
        promoted += 1

    summary = (
        f"Reviewed {len(signals)} recent signal(s); promoted {promoted} recurring, "
        f"non-PHI item(s) into long-term memory."
    )
    sweep = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "ran_at": now_ms,
        "candidates_considered": len(signals),
        "promoted_count": promoted,
        "summary": summary,
        "trigger": trigger,
    }
    # Persist the sweep record (best-effort; caller audits).
    if hasattr(repo, "record_sweep"):
        repo.record_sweep(sweep)
    return sweep
