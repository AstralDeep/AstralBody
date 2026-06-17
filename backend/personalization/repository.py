"""Persistence for personalization: profile, personality, and durable memory.

Thin repository over the shared ``Database`` (same convention as
``audit``/``onboarding`` repositories). All methods are strictly user-scoped.
PHI gating is applied by callers (service / memory_tools) before values reach
this layer — the repository is dumb persistence.

JSON columns (``goals``, ``personality``) are stored as ``jsonb`` via an
explicit ``::jsonb`` cast and returned already decoded by psycopg2.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

MEMORY_CATEGORIES = ("profession", "goal", "preference", "workflow_tag", "context")


def _now_ms() -> int:
    return int(time.time() * 1000)


class PersonalizationRepository:
    def __init__(self, db) -> None:
        self.db = db

    # ── Profile / personality ────────────────────────────────────────────

    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        row = self.db.fetch_one(
            """SELECT user_id, profession, goals, personality, dreaming_enabled,
                      created_at, updated_at
               FROM user_personalization WHERE user_id = ?""",
            (user_id,),
        )
        return dict(row) if row else None

    def upsert_profile(
        self,
        user_id: str,
        *,
        profession: Optional[str] = None,
        goals: Optional[List[str]] = None,
        personality: Optional[Dict[str, Any]] = None,
        dreaming_enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Insert or update the user's profile. Only provided fields change."""
        existing = self.get_profile(user_id)
        now = _now_ms()
        if existing is None:
            self.db.execute(
                """INSERT INTO user_personalization
                       (user_id, profession, goals, personality, dreaming_enabled,
                        created_at, updated_at)
                   VALUES (?, ?, ?::jsonb, ?::jsonb, ?, ?, ?)""",
                (
                    user_id,
                    profession,
                    json.dumps(goals if goals is not None else []),
                    json.dumps(personality if personality is not None else {}),
                    True if dreaming_enabled is None else bool(dreaming_enabled),
                    now,
                    now,
                ),
            )
        else:
            new_profession = profession if profession is not None else existing.get("profession")
            new_goals = goals if goals is not None else (existing.get("goals") or [])
            new_personality = personality if personality is not None else (existing.get("personality") or {})
            new_dreaming = (
                existing.get("dreaming_enabled") if dreaming_enabled is None else bool(dreaming_enabled)
            )
            self.db.execute(
                """UPDATE user_personalization
                   SET profession = ?, goals = ?::jsonb, personality = ?::jsonb,
                       dreaming_enabled = ?, updated_at = ?
                   WHERE user_id = ?""",
                (
                    new_profession,
                    json.dumps(new_goals),
                    json.dumps(new_personality),
                    new_dreaming,
                    now,
                    user_id,
                ),
            )
        return self.get_profile(user_id)  # type: ignore[return-value]

    def reset_profile(self, user_id: str) -> None:
        """Reset a user's profile/personality to defaults (keeps the row)."""
        self.db.execute(
            """UPDATE user_personalization
               SET profession = NULL, goals = '[]'::jsonb, personality = '{}'::jsonb,
                   updated_at = ?
               WHERE user_id = ?""",
            (_now_ms(), user_id),
        )

    def set_dreaming_enabled(self, user_id: str, enabled: bool) -> None:
        # Ensure a row exists, then set the flag.
        self.upsert_profile(user_id, dreaming_enabled=enabled)

    # ── Durable memory ───────────────────────────────────────────────────

    def list_memory(self, user_id: str) -> List[Dict[str, Any]]:
        # C-M1: superseded (soft-deleted / replaced) memories are excluded from
        # all recall — reconciliation keeps the live set clean.
        rows = self.db.fetch_all(
            """SELECT id, user_id, category, value, source, salience, created_at,
                      updated_at, keywords, signature
               FROM memory_item WHERE user_id = ? AND superseded_at IS NULL
               ORDER BY created_at DESC""",
            (user_id,),
        )
        return [dict(r) for r in rows]

    def create_memory(
        self, user_id: str, category: str, value: str, *, source: str = "explicit",
        salience: float = 0.0, keywords: Optional[str] = None,
    ) -> Dict[str, Any]:
        if category not in MEMORY_CATEGORIES:
            raise ValueError(f"invalid memory category: {category}")
        if source not in ("explicit", "promoted"):
            raise ValueError(f"invalid memory source: {source}")
        mem_id = str(uuid.uuid4())
        now = _now_ms()
        # C-S9: HMAC-sign the row's identifying fields (None when no key set).
        from .memory_guard import sign_fields
        signature = sign_fields(mem_id, user_id, category, value, source)
        self.db.execute(
            """INSERT INTO memory_item
                   (id, user_id, category, value, source, salience, created_at,
                    updated_at, keywords, signature)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (mem_id, user_id, category, value, source, salience, now, now, keywords, signature),
        )
        return {
            "id": mem_id, "user_id": user_id, "category": category, "value": value,
            "source": source, "salience": salience, "created_at": now, "updated_at": now,
            "keywords": keywords, "signature": signature,
        }

    def get_memory(self, user_id: str, mem_id: str) -> Optional[Dict[str, Any]]:
        row = self.db.fetch_one(
            "SELECT * FROM memory_item WHERE id = ? AND user_id = ?",
            (mem_id, user_id),
        )
        return dict(row) if row else None

    def update_memory_value(self, user_id: str, mem_id: str, value: str) -> bool:
        cur = self.db.execute(
            "UPDATE memory_item SET value = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (value, _now_ms(), mem_id, user_id),
        )
        return getattr(cur, "rowcount", 0) > 0

    def delete_memory(self, user_id: str, mem_id: str) -> bool:
        cur = self.db.execute(
            "DELETE FROM memory_item WHERE id = ? AND user_id = ?",
            (mem_id, user_id),
        )
        return getattr(cur, "rowcount", 0) > 0

    def supersede_memory(self, user_id: str, old_id: str,
                         new_id: Optional[str] = None) -> bool:
        """C-M1: soft-delete a memory (reconcile UPDATE/DELETE). Sets
        ``superseded_at`` so the row drops out of recall; ``new_id`` optionally
        points at the replacement memory (UPDATE) — left NULL for a plain
        removal (DELETE). Only affects a currently-live row (idempotent)."""
        now = _now_ms()
        cur = self.db.execute(
            """UPDATE memory_item SET superseded_by = ?, superseded_at = ?, updated_at = ?
               WHERE id = ? AND user_id = ? AND superseded_at IS NULL""",
            (new_id, now, now, old_id, user_id),
        )
        return getattr(cur, "rowcount", 0) > 0

    # ── Linked-note graph (C-M2) ─────────────────────────────────────────

    def add_link(self, user_id: str, a_id: str, b_id: str) -> bool:
        """Create an undirected link between two memories (stored as both
        directed edges so a single-column lookup finds neighbours either way).
        Idempotent; a self-link is ignored."""
        if not a_id or not b_id or a_id == b_id:
            return False
        now = _now_ms()
        for src, dst in ((a_id, b_id), (b_id, a_id)):
            try:
                self.db.execute(
                    """INSERT INTO memory_link (user_id, memory_id, linked_id, created_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT (user_id, memory_id, linked_id) DO NOTHING""",
                    (user_id, src, dst, now),
                )
            except Exception:
                return False
        return True

    def linked_ids(self, user_id: str, mem_id: str) -> List[str]:
        """Ids of memories linked to ``mem_id`` (live links only — superseded
        targets are filtered out by the join)."""
        rows = self.db.fetch_all(
            """SELECT l.linked_id FROM memory_link l
               JOIN memory_item m ON m.id = l.linked_id AND m.user_id = l.user_id
               WHERE l.user_id = ? AND l.memory_id = ? AND m.superseded_at IS NULL""",
            (user_id, mem_id),
        )
        return [str(r["linked_id"]) for r in rows]

    def list_links(self, user_id: str) -> List[Dict[str, str]]:
        """All live directed link edges for a user (both directions of each
        undirected link), filtered to live endpoints. Powers the C-M3
        Personalized-PageRank graph in one query."""
        rows = self.db.fetch_all(
            """SELECT l.memory_id, l.linked_id FROM memory_link l
               JOIN memory_item a ON a.id = l.memory_id AND a.user_id = l.user_id
               JOIN memory_item b ON b.id = l.linked_id AND b.user_id = l.user_id
               WHERE l.user_id = ? AND a.superseded_at IS NULL AND b.superseded_at IS NULL""",
            (user_id,),
        )
        return [{"memory_id": str(r["memory_id"]), "linked_id": str(r["linked_id"])}
                for r in rows]

    # ── Short-term signals ───────────────────────────────────────────────

    def add_signal(self, user_id: str, category: str, value: str) -> Dict[str, Any]:
        if category not in MEMORY_CATEGORIES:
            raise ValueError(f"invalid signal category: {category}")
        sig_id = str(uuid.uuid4())
        now = _now_ms()
        self.db.execute(
            """INSERT INTO short_term_signal
                   (id, user_id, category, value, recall_count, last_seen_at, created_at)
               VALUES (?, ?, ?, ?, 1, ?, ?)""",
            (sig_id, user_id, category, value, now, now),
        )
        return {"id": sig_id, "user_id": user_id, "category": category, "value": value}

    def list_signals(self, user_id: str) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            """SELECT id, user_id, category, value, recall_count, last_seen_at, created_at
               FROM short_term_signal WHERE user_id = ? ORDER BY last_seen_at DESC""",
            (user_id,),
        )
        return [dict(r) for r in rows]

    def delete_signal(self, user_id: str, sig_id: str) -> None:
        self.db.execute(
            "DELETE FROM short_term_signal WHERE id = ? AND user_id = ?",
            (sig_id, user_id),
        )

    # ── Consolidation sweeps ("dreams") ──────────────────────────────────

    def record_sweep(self, sweep: Dict[str, Any]) -> None:
        self.db.execute(
            """INSERT INTO consolidation_sweep
                   (id, user_id, ran_at, candidates_considered, promoted_count, summary, trigger)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (sweep["id"], sweep["user_id"], sweep["ran_at"], sweep["candidates_considered"],
             sweep["promoted_count"], sweep["summary"], sweep["trigger"]),
        )

    def list_sweeps(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            """SELECT id, ran_at, candidates_considered, promoted_count, summary, trigger
               FROM consolidation_sweep WHERE user_id = ? ORDER BY ran_at DESC LIMIT ?""",
            (user_id, limit),
        )
        return [dict(r) for r in rows]
