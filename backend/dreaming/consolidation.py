"""Background memory consolidation ("dreaming") scoring + sweep (feature 025).

Pure scoring helpers (unit-testable) plus the integration ``run_sweep`` that
promotes high-signal, recurring, non-PHI short-term signals into durable
memory, re-checking the PHI gate at promotion (FR-027/FR-028) and recording a
human-readable sweep summary (FR-029).
"""
from __future__ import annotations

import logging
import math
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Dreaming.Consolidation")

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


# Key under which the idle anticipatory precompute plan is stashed inside the
# user's existing ``user_personalization.personality`` jsonb (NO new table —
# 033 C-N11 constraint). A leading underscore namespaces it away from the
# user-facing personality traits (tone/notes/...).
_SLEEPTIME_PLAN_KEY = "_sleeptime_precompute"
# Cap on how many recent signal values are mined for follow-up topics.
_SLEEPTIME_MAX_SIGNALS = 25


def _run_sleeptime_precompute(
    repo,
    user_id: str,
    *,
    now_ms: int,
    last_activity_ms: Optional[int],
    idle_after_ms: int,
    budget: int,
) -> Optional[Dict[str, Any]]:
    """Idle-time anticipatory precompute (033 C-N11 / sleeptime.py).

    Returns the persisted plan record, or ``None`` when sleeptime is disabled,
    the user is still active, the repo can't store a plan, or nothing is worth
    precomputing. Behind ``FF_SLEEPTIME_COMPUTE`` (default OFF) — when the flag
    is off this is a no-op. Best-effort: never raises into the sweep.
    """
    # Import lazily so consolidation has no hard dependency on the optional
    # sleeptime module path and the flag is read at call time (testable).
    from dreaming.sleeptime import (
        anticipate_questions,
        is_idle,
        precompute_plan,
        sleeptime_enabled,
    )

    if not sleeptime_enabled():
        return None
    # Only precompute when the user is actually idle. When the caller can't
    # supply a last-activity timestamp we treat the scheduled sweep itself as
    # idle-time (a sweep already implies a quiet window).
    if last_activity_ms is not None and not is_idle(
        last_activity_ms, now_ms, idle_after_ms=idle_after_ms
    ):
        return None

    # Persisting needs a profile store; fail-closed if the repo lacks one.
    if not (hasattr(repo, "upsert_profile") and hasattr(repo, "get_profile")):
        return None

    # Recent-topic signal: mine the still-pending short-term signal values
    # (the freshest, in-DB, already-PHI-gated text we have for this user) plus
    # durable goal/workflow memories.
    try:
        signals = repo.list_signals(user_id) or []
    except Exception:  # pragma: no cover - defensive
        signals = []
    recent_messages = [str(s.get("value") or "") for s in signals[:_SLEEPTIME_MAX_SIGNALS]]
    try:
        memories = repo.list_memory(user_id) if hasattr(repo, "list_memory") else []
    except Exception:  # pragma: no cover - defensive
        memories = []

    anticipated = anticipate_questions(recent_messages, list(memories or []))
    plan = precompute_plan(anticipated, budget=budget)
    if not plan:
        return None

    record = {
        "generated_at": now_ms,
        "trigger": "idle",
        "questions": [
            {"question": a.question, "rationale": a.rationale, "priority": a.priority}
            for a in plan
        ],
    }
    # Persist into the EXISTING personality jsonb (merge, never clobber the
    # user-facing traits). Best-effort — a storage failure must not break the
    # sweep's promotion path.
    try:
        profile = repo.get_profile(user_id) or {}
        personality = dict(profile.get("personality") or {})
        personality[_SLEEPTIME_PLAN_KEY] = record
        repo.upsert_profile(user_id, personality=personality)
    except Exception:  # pragma: no cover - defensive
        logger.debug("dreaming.sleeptime persist failed (non-fatal)", exc_info=True)
        return None

    logger.info("dreaming.sleeptime_precomputed",
                extra={"user_id": user_id, "precomputed": len(plan)})
    return record


def run_sweep(
    repo,
    phi_gate,
    user_id: str,
    *,
    trigger: str = "scheduled",
    min_recalls: int = 2,
    now_ms: Optional[int] = None,
    last_activity_ms: Optional[int] = None,
    idle_after_ms: int = 300_000,
    precompute_budget: int = 3,
) -> Dict[str, Any]:
    """Run one consolidation sweep for ``user_id``; return the sweep record.

    Promotes eligible non-PHI signals into durable memory, re-checking the PHI
    gate at promotion (defense in depth — signals were already gated at
    capture). Consumed signals are deleted; a ``consolidation_sweep`` row is
    written for review.

    When ``FF_SLEEPTIME_COMPUTE`` is enabled (default OFF, 033 C-N11) and the
    user is idle, the sweep also anticipates likely next questions and persists
    a small precompute plan into the user's existing personality jsonb (no new
    table). ``last_activity_ms`` (epoch-ms of the user's last activity) gates
    the idle check; when omitted the scheduled sweep is itself treated as
    idle-time. The returned record gains a ``precompute`` block describing what
    was anticipated (empty list when sleeptime is off or nothing qualified).
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
    # Persist the sweep record (best-effort; caller audits). The precompute
    # plan rides the existing personality store, so the DB-persisted sweep row
    # shape is unchanged (no schema delta — 033 constraint).
    if hasattr(repo, "record_sweep"):
        repo.record_sweep(sweep)

    # 033 C-N11: idle anticipatory precompute (flag-gated, default OFF). Run
    # AFTER promotion so anticipation reflects the post-sweep memory state.
    precompute = _run_sleeptime_precompute(
        repo, user_id, now_ms=now_ms, last_activity_ms=last_activity_ms,
        idle_after_ms=idle_after_ms, budget=precompute_budget,
    )
    sweep["precompute"] = (precompute or {}).get("questions", [])

    # 030 FR-017: structured observability for consolidation sweeps.
    logger.info("dreaming.sweep_ran",
                extra={"user_id": user_id, "trigger": trigger,
                       "considered": len(signals), "promoted": promoted,
                       "precomputed": len(sweep["precompute"])})
    return sweep
