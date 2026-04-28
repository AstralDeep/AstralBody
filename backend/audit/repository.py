"""
Audit log repository — psycopg2-backed, append-only, hash-chained.

Provides three primary operations:

* :meth:`AuditRepository.insert` — atomic per-user hash-chained insert.
  Wraps the row in a transaction that ``SELECT … FOR UPDATE`` locks the
  user's most recent entry, computes the new ``prev_hash`` and HMAC
  ``entry_hash``, and INSERTs. Concurrent inserts for the same user
  serialize through the row-level lock; concurrent inserts for
  different users do not contend.
* :meth:`AuditRepository.list_for_user` — cursor-paged, filterable list
  scoped to a single ``actor_user_id``. The repository never accepts a
  user_id from external input on this method; callers always pass the
  authenticated principal.
* :meth:`AuditRepository.get_for_user` — single-row fetch, scoped per
  user; returns ``None`` for either non-existence or cross-user access.

Other helpers:

* :meth:`AuditRepository.verify_chain` — walks a user's chain forward
  and returns the first event_id whose computed hash diverges from the
  stored ``entry_hash``. Used by the verify-chain CLI.
* :meth:`AuditRepository.purge_older_than` — DELETEs rows whose
  ``recorded_at`` is older than the retention window. Caller MUST set
  the ``audit.allow_purge`` session GUC; application code never does.

The repository never updates rows — there is no ``update`` method. The
in-progress → terminal transition is modeled as a *new* row sharing
``correlation_id``.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor, Json

from .pii import chain_hmac, get_active_key_id
from .schemas import AuditEventCreate, AuditEventDTO, ArtifactPointer

logger = logging.getLogger("Audit.Repository")

GENESIS_PREV_HASH = bytes(32)


# ---------------------------------------------------------------------------
# Canonicalization helpers
# ---------------------------------------------------------------------------

def _canonical_row_bytes(row: Dict[str, Any]) -> bytes:
    """Produce a deterministic byte string for hash-chain HMAC input.

    Excludes the chain fields themselves (``prev_hash``, ``entry_hash``,
    ``key_id``) and the ``recorded_at`` column, which is server-clocked
    after canonicalization. ``schema_version`` is included so a future
    canonicalization change cannot retroactively break old rows that
    used the old shape.
    """
    canonical = {
        "schema_version": row["schema_version"],
        "event_id": row["event_id"],
        "actor_user_id": row["actor_user_id"],
        "auth_principal": row["auth_principal"],
        "agent_id": row.get("agent_id"),
        "event_class": row["event_class"],
        "action_type": row["action_type"],
        "description": row["description"],
        "conversation_id": row.get("conversation_id"),
        "correlation_id": row["correlation_id"],
        "outcome": row["outcome"],
        "outcome_detail": row.get("outcome_detail"),
        "inputs_meta": row["inputs_meta"],
        "outputs_meta": row["outputs_meta"],
        "artifact_pointers": row["artifact_pointers"],
        "started_at": row["started_at"],
        "completed_at": row.get("completed_at"),
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _row_to_dto(row: Dict[str, Any], availability_resolver=None) -> AuditEventDTO:
    """Map a DB row to the public DTO. Computes pointer availability."""
    pointers_raw = row.get("artifact_pointers") or []
    if isinstance(pointers_raw, str):
        pointers_raw = json.loads(pointers_raw)
    pointers: List[ArtifactPointer] = []
    for p in pointers_raw:
        item = dict(p)
        if availability_resolver is not None:
            try:
                item["available"] = bool(availability_resolver(item))
            except Exception:  # pragma: no cover — never block a read
                item["available"] = True
        else:
            item.setdefault("available", True)
        pointers.append(ArtifactPointer(**{k: item.get(k) for k in ("artifact_id", "store", "extension", "size_bytes", "available")}))
    inputs = row.get("inputs_meta") or {}
    outputs = row.get("outputs_meta") or {}
    if isinstance(inputs, str):
        inputs = json.loads(inputs)
    if isinstance(outputs, str):
        outputs = json.loads(outputs)
    return AuditEventDTO(
        event_id=str(row["event_id"]),
        event_class=row["event_class"],
        action_type=row["action_type"],
        description=row["description"],
        agent_id=row.get("agent_id"),
        conversation_id=row.get("conversation_id"),
        correlation_id=str(row["correlation_id"]),
        outcome=row["outcome"],
        outcome_detail=row.get("outcome_detail"),
        inputs_meta=inputs,
        outputs_meta=outputs,
        artifact_pointers=pointers,
        started_at=row["started_at"],
        completed_at=row.get("completed_at"),
        recorded_at=row["recorded_at"],
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class AuditRepository:
    """Append-only audit log access. Owned by ``Recorder``.

    The repository exposes ``insert`` / ``list_for_user`` / ``get_for_user``
    plus the operator helpers ``verify_chain`` and ``purge_older_than``.
    All writes go through ``insert``; all reads are filtered on
    ``actor_user_id``.
    """

    def __init__(self, db):
        self._db = db  # shared.database.Database instance

    # ------------------------------------------------------------------
    # Insert (write path)
    # ------------------------------------------------------------------

    def insert(self, event: AuditEventCreate) -> AuditEventDTO:
        """Insert a new audit row, hash-chained to the user's previous row.

        Returns the DTO of the inserted row (with ``recorded_at``
        populated by the database). Raises if the underlying DB
        operation fails — callers in ``Recorder`` decide whether to
        retry from the disk queue.
        """
        event_id = str(uuid.uuid4())
        key_id = get_active_key_id()
        schema_version = 1

        conn = self._db._get_connection()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                # Serialize chain insertion per user via an advisory
                # transaction-scoped lock keyed on hash(user_id). Held until
                # COMMIT/ROLLBACK. Using an advisory lock (rather than
                # SELECT ... FOR UPDATE on the most-recent row) covers the
                # genesis case where there is no prior row to lock.
                cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (f"audit_events:{event.actor_user_id}",),
                )
                cur.execute(
                    """
                    SELECT entry_hash
                    FROM audit_events
                    WHERE actor_user_id = %s
                    ORDER BY recorded_at DESC, event_id DESC
                    LIMIT 1
                    """,
                    (event.actor_user_id,),
                )
                row = cur.fetchone()
                prev_hash = bytes(row["entry_hash"]) if row else GENESIS_PREV_HASH

                row_for_chain = {
                    "schema_version": schema_version,
                    "event_id": event_id,
                    "actor_user_id": event.actor_user_id,
                    "auth_principal": event.auth_principal,
                    "agent_id": event.agent_id,
                    "event_class": event.event_class,
                    "action_type": event.action_type,
                    "description": event.description,
                    "conversation_id": event.conversation_id,
                    "correlation_id": event.correlation_id,
                    "outcome": event.outcome,
                    "outcome_detail": event.outcome_detail,
                    "inputs_meta": event.inputs_meta,
                    "outputs_meta": event.outputs_meta,
                    "artifact_pointers": [p.model_dump() for p in event.artifact_pointers],
                    "started_at": event.started_at.astimezone(timezone.utc).isoformat(),
                    "completed_at": event.completed_at.astimezone(timezone.utc).isoformat() if event.completed_at else None,
                }
                entry_hash, used_kid = chain_hmac(
                    prev_hash, _canonical_row_bytes(row_for_chain), key_id=key_id
                )

                cur.execute(
                    """
                    INSERT INTO audit_events (
                        event_id, actor_user_id, auth_principal, agent_id,
                        event_class, action_type, description, conversation_id,
                        correlation_id, outcome, outcome_detail,
                        inputs_meta, outputs_meta, artifact_pointers,
                        started_at, completed_at,
                        prev_hash, entry_hash, key_id, schema_version
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s, %s, %s
                    )
                    RETURNING *
                    """,
                    (
                        event_id, event.actor_user_id, event.auth_principal, event.agent_id,
                        event.event_class, event.action_type, event.description, event.conversation_id,
                        event.correlation_id, event.outcome, event.outcome_detail,
                        Json(event.inputs_meta), Json(event.outputs_meta),
                        Json([p.model_dump() for p in event.artifact_pointers]),
                        event.started_at, event.completed_at,
                        psycopg2.Binary(prev_hash), psycopg2.Binary(entry_hash),
                        used_kid, schema_version,
                    ),
                )
                inserted = cur.fetchone()
                conn.commit()
                return _row_to_dto(inserted)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Reads (filtered by authenticated user)
    # ------------------------------------------------------------------

    def list_for_user(
        self,
        actor_user_id: str,
        *,
        limit: int = 50,
        cursor: Optional[str] = None,
        event_classes: Optional[List[str]] = None,
        outcomes: Optional[List[str]] = None,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
        keyword: Optional[str] = None,
        availability_resolver=None,
    ) -> Tuple[List[AuditEventDTO], Optional[str]]:
        """Return at most ``limit`` events for a user plus a next-cursor.

        Cursor encodes ``(recorded_at_iso, event_id)`` of the last
        returned row; pagination is keyset, not offset, so it stays
        stable under concurrent inserts.
        """
        if limit < 1 or limit > 200:
            raise ValueError("limit out of range")

        clauses = ["actor_user_id = %s"]
        params: List[Any] = [actor_user_id]

        if cursor:
            try:
                ts_iso, eid = cursor.split("|", 1)
                cursor_ts = datetime.fromisoformat(ts_iso)
                # Validate the UUID shape before passing it through (psycopg2
                # doesn't adapt uuid.UUID by default for ad-hoc queries).
                uuid.UUID(eid)
            except Exception as exc:
                raise ValueError(f"invalid cursor: {exc}") from exc
            clauses.append("(recorded_at, event_id) < (%s, %s::uuid)")
            params.extend([cursor_ts, eid])

        if event_classes:
            clauses.append("event_class = ANY(%s)")
            params.append(list(event_classes))
        if outcomes:
            clauses.append("outcome = ANY(%s)")
            params.append(list(outcomes))
        if from_ts:
            clauses.append("recorded_at >= %s")
            params.append(from_ts)
        if to_ts:
            clauses.append("recorded_at < %s")
            params.append(to_ts)
        if keyword:
            kw = f"%{keyword.lower()}%"
            clauses.append("(LOWER(description) LIKE %s OR LOWER(action_type) LIKE %s)")
            params.extend([kw, kw])

        where_sql = " AND ".join(clauses)
        # Fetch limit+1 to detect whether more pages exist
        params.append(limit + 1)

        conn = self._db._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT * FROM audit_events
                    WHERE {where_sql}
                    ORDER BY recorded_at DESC, event_id DESC
                    LIMIT %s
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        next_cursor: Optional[str] = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = f"{last['recorded_at'].isoformat()}|{last['event_id']}"
            rows = rows[:limit]
        return [_row_to_dto(r, availability_resolver) for r in rows], next_cursor

    def get_for_user(
        self,
        actor_user_id: str,
        event_id: str,
        availability_resolver=None,
    ) -> Optional[AuditEventDTO]:
        """Fetch a single event by id, scoped to the authenticated user.

        Returns ``None`` for either non-existence or wrong owner — this
        indistinguishability is intentional (FR-007 / FR-019).
        """
        try:
            uuid.UUID(event_id)
        except (ValueError, TypeError):
            return None
        conn = self._db._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM audit_events WHERE event_id = %s AND actor_user_id = %s",
                    (event_id, actor_user_id),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return _row_to_dto(row, availability_resolver)

    # ------------------------------------------------------------------
    # Operator helpers (NOT exposed via REST)
    # ------------------------------------------------------------------

    def verify_chain(self, actor_user_id: str) -> Optional[str]:
        """Walk the user's chain forward; return the first bad event_id or ``None``."""
        conn = self._db._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM audit_events
                    WHERE actor_user_id = %s
                    ORDER BY recorded_at ASC, event_id ASC
                    """,
                    (actor_user_id,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        prev = GENESIS_PREV_HASH
        for r in rows:
            row_for_chain = {
                "schema_version": r["schema_version"],
                "event_id": str(r["event_id"]),
                "actor_user_id": r["actor_user_id"],
                "auth_principal": r["auth_principal"],
                "agent_id": r.get("agent_id"),
                "event_class": r["event_class"],
                "action_type": r["action_type"],
                "description": r["description"],
                "conversation_id": r.get("conversation_id"),
                "correlation_id": str(r["correlation_id"]),
                "outcome": r["outcome"],
                "outcome_detail": r.get("outcome_detail"),
                "inputs_meta": r["inputs_meta"],
                "outputs_meta": r["outputs_meta"],
                "artifact_pointers": r["artifact_pointers"],
                "started_at": r["started_at"].astimezone(timezone.utc).isoformat() if r["started_at"] else None,
                "completed_at": r["completed_at"].astimezone(timezone.utc).isoformat() if r["completed_at"] else None,
            }
            expected, _ = chain_hmac(prev, _canonical_row_bytes(row_for_chain), key_id=r["key_id"])
            stored_prev = bytes(r["prev_hash"])
            stored_entry = bytes(r["entry_hash"])
            if stored_prev != prev or stored_entry != expected:
                return str(r["event_id"])
            prev = stored_entry
        return None

    def purge_older_than(self, cutoff: datetime) -> int:
        """DELETE rows older than ``cutoff``. Caller must hold the GUC.

        Returns the number of rows deleted. Raises if the protective
        trigger fires — meaning the caller forgot to set
        ``audit.allow_purge`` in its session.
        """
        conn = self._db._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL audit.allow_purge = 'true'")
                cur.execute(
                    "DELETE FROM audit_events WHERE recorded_at < %s",
                    (cutoff,),
                )
                count = cur.rowcount
                conn.commit()
                return count
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
