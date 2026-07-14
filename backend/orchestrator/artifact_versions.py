"""Feature 055 (US4) — bounded per-component version history (research D10).

``component_version`` archives a component dict immediately BEFORE a
refine/restore overwrites the live ``saved_components`` row, so every live
component keeps up to :data:`RETAIN` restorable prior states. Restores never
delete archived rows — the current dict is archived first and the chosen
version is copied back onto the live row — so pruning is count-based only,
enforced at archive time.

All reads and writes are scoped by ``(chat_id, user_id)`` exactly like the
workspace store (workspace.py). ``version_no`` is monotonic per
``(chat_id, component_id)`` and assigned atomically by the insert itself;
the UNIQUE constraint turns a concurrent double-archive into a bounded
retry instead of silent renumbering.

Functions take the shared ``Database`` facade explicitly so the cascade
sites (component/chat deletion in workspace.py and history.py) and the T038
refine/restore handlers can call them with the handle they already own.
``a``-prefixed async twins run the sync functions off the event loop
(feature 052 loop guard).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import psycopg2

logger = logging.getLogger("orchestrator.artifact_versions")

# FR-024: newest versions retained per (chat_id, component_id).
RETAIN = 5

VALID_REASONS = ("refine", "restore")

_ARCHIVE_ATTEMPTS = 3


def _iso(value: Any) -> Any:
    """TIMESTAMPTZ columns come back as datetimes; return wire-ready strings."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def archive(db, chat_id: str, user_id: str, component_id: str,
            component: Dict[str, Any], reason: str = "refine") -> int:
    """Archive one component dict; returns the assigned ``version_no``.

    Called BEFORE a refine/restore overwrites the live row. Prunes rows
    beyond the newest :data:`RETAIN` for this component as a side effect.
    """
    if not chat_id or not user_id or not component_id:
        raise ValueError("archive requires chat_id, user_id and component_id")
    if not isinstance(component, dict):
        raise ValueError("archive requires a component dict")
    if reason not in VALID_REASONS:
        raise ValueError(f"unknown archive reason {reason!r}")

    payload = json.dumps(component)
    last_err: Optional[Exception] = None
    for _ in range(_ARCHIVE_ATTEMPTS):
        try:
            # MAX is scoped like the UNIQUE constraint (no user_id) so a
            # constraint-violating number can never be computed.
            cur = db.execute(
                "INSERT INTO component_version "
                "(chat_id, user_id, component_id, version_no, component, reason) "
                "SELECT ?, ?, ?, COALESCE(MAX(version_no), 0) + 1, ?::jsonb, ? "
                "FROM component_version WHERE chat_id = ? AND component_id = ? "
                "RETURNING version_no",
                (chat_id, user_id, component_id, payload, reason,
                 chat_id, component_id),
            )
            row = cur.fetchone()
            version_no = int(row["version_no"])
            break
        except psycopg2.IntegrityError as e:
            # Concurrent archive won this version_no — recompute and retry.
            last_err = e
    else:
        raise last_err  # noqa: B904 — the retried error IS the failure

    if version_no > RETAIN:
        db.execute(
            "DELETE FROM component_version WHERE chat_id = ? AND user_id = ? "
            "AND component_id = ? AND version_no <= ?",
            (chat_id, user_id, component_id, version_no - RETAIN),
        )
    return version_no


def list_versions(db, chat_id: str, user_id: str, component_id: str,
                  limit: int = RETAIN) -> List[Dict[str, Any]]:
    """Bounded newest-first metadata list (no component payloads)."""
    if not chat_id or not user_id or not component_id:
        return []
    try:
        limit = max(1, min(int(limit), RETAIN))
    except (TypeError, ValueError):
        limit = RETAIN
    rows = db.fetch_all(
        "SELECT id, version_no, reason, created_at, "
        "component->>'title' AS title, component->>'type' AS component_type "
        "FROM component_version "
        "WHERE chat_id = ? AND user_id = ? AND component_id = ? "
        "ORDER BY version_no DESC LIMIT ?",
        (chat_id, user_id, component_id, limit),
    )
    return [{
        "id": r["id"],
        "version_no": r["version_no"],
        "reason": r["reason"],
        "created_at": _iso(r["created_at"]),
        "title": r.get("title"),
        "component_type": r.get("component_type"),
    } for r in rows]


def get_version(db, chat_id: str, user_id: str, component_id: str,
                version_no: Any) -> Optional[Dict[str, Any]]:
    """One archived version with its full component dict, or ``None``."""
    if not chat_id or not user_id or not component_id:
        return None
    try:
        version_no = int(version_no)
    except (TypeError, ValueError):
        return None
    row = db.fetch_one(
        "SELECT id, version_no, reason, created_at, component "
        "FROM component_version "
        "WHERE chat_id = ? AND user_id = ? AND component_id = ? AND version_no = ?",
        (chat_id, user_id, component_id, version_no),
    )
    if not row:
        return None
    component = row["component"]
    if isinstance(component, str):
        try:
            component = json.loads(component)
        except (json.JSONDecodeError, TypeError):
            logger.warning("component_version %s holds unparseable JSON", row["id"])
            return None
    return {
        "id": row["id"],
        "chat_id": chat_id,
        "component_id": component_id,
        "version_no": row["version_no"],
        "reason": row["reason"],
        "created_at": _iso(row["created_at"]),
        "component": component,
    }


def delete_for_component(db, chat_id: str, user_id: str, component_id: str) -> int:
    """Cascade: drop all versions of one deleted component. Returns row count."""
    if not chat_id or not user_id or not component_id:
        return 0
    cur = db.execute(
        "DELETE FROM component_version "
        "WHERE chat_id = ? AND user_id = ? AND component_id = ?",
        (chat_id, user_id, component_id),
    )
    return int(getattr(cur, "rowcount", 0) or 0)


def delete_for_chat(db, chat_id: str, user_id: str) -> int:
    """Cascade: drop all versions in a deleted chat (no chats FK on this table)."""
    if not chat_id or not user_id:
        return 0
    cur = db.execute(
        "DELETE FROM component_version WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id),
    )
    return int(getattr(cur, "rowcount", 0) or 0)


# ── async facade (event-loop-safe twins of the sync functions above) ────────
async def aarchive(db, chat_id: str, user_id: str, component_id: str,
                   component: Dict[str, Any], reason: str = "refine") -> int:
    """Async twin of :func:`archive`, run off the event loop."""
    return await asyncio.to_thread(archive, db, chat_id, user_id,
                                   component_id, component, reason)


async def alist_versions(db, chat_id: str, user_id: str, component_id: str,
                         limit: int = RETAIN) -> List[Dict[str, Any]]:
    """Async twin of :func:`list_versions`, run off the event loop."""
    return await asyncio.to_thread(list_versions, db, chat_id, user_id,
                                   component_id, limit)


async def aget_version(db, chat_id: str, user_id: str, component_id: str,
                       version_no: Any) -> Optional[Dict[str, Any]]:
    """Async twin of :func:`get_version`, run off the event loop."""
    return await asyncio.to_thread(get_version, db, chat_id, user_id,
                                   component_id, version_no)


async def adelete_for_component(db, chat_id: str, user_id: str,
                                component_id: str) -> int:
    """Async twin of :func:`delete_for_component`, run off the event loop."""
    return await asyncio.to_thread(delete_for_component, db, chat_id,
                                   user_id, component_id)


async def adelete_for_chat(db, chat_id: str, user_id: str) -> int:
    """Async twin of :func:`delete_for_chat`, run off the event loop."""
    return await asyncio.to_thread(delete_for_chat, db, chat_id, user_id)
