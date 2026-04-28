"""Per-user-isolated psycopg2 access layer for the feedback subsystem.

Every query that touches ``component_feedback``, ``tool_quality_signal``,
``knowledge_update_proposal``, or ``quarantine_entry`` lives here. Routes
and the recorder NEVER write SQL inline — they go through this module.

Design notes:

* Every method that selects, updates, or deletes ``component_feedback``
  rows takes ``actor_user_id`` as a mandatory first argument and applies
  it to the WHERE clause. There are no "list all" or "look up by id alone"
  helpers. Cross-user reads return None / empty list, indistinguishable
  from "not found" (mirrors audit-log pattern from feature 003, FR-009).
* Admin-only methods (``list_underperforming``, ``insert_quality_signal``,
  ``list_proposals``, etc.) are NOT per-user — they are gated by the
  ``admin`` role check at the API layer. The repository methods themselves
  accept any actor; authorization is the caller's responsibility.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import psycopg2

from .schemas import (
    DEFAULT_DEDUP_WINDOW_SECONDS,
    ComponentFeedbackDTO,
    KnowledgeUpdateProposalDTO,
    QuarantineEntryDTO,
    ToolQualitySignalDTO,
)

logger = logging.getLogger("Feedback.Repository")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FeedbackRepository:
    """Thin façade over the four feature-004 tables."""

    def __init__(self, db: Any):
        # ``db`` is a :class:`backend.shared.database.Database` instance.
        # We use its ``_get_connection()`` helper directly so we can
        # transactionally combine multi-statement operations.
        self._db = db

    # ------------------------------------------------------------------
    # ComponentFeedback — submit / dedup / list / retract / amend
    # ------------------------------------------------------------------

    def find_in_dedup_window(
        self,
        actor_user_id: str,
        correlation_id: Optional[str],
        component_id: Optional[str],
        *,
        window_seconds: int = DEFAULT_DEDUP_WINDOW_SECONDS,
        now: Optional[datetime] = None,
    ) -> Optional[ComponentFeedbackDTO]:
        """Return the active feedback row this user has on this dispatch+component
        within the dedup window, if any. Used to collapse rapid double-submits.
        """
        cutoff = (now or _utcnow()) - timedelta(seconds=window_seconds)
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, user_id, conversation_id, correlation_id, source_agent,
                       source_tool, component_id, sentiment, category, comment_raw,
                       comment_safety, comment_safety_reason, lifecycle, superseded_by,
                       created_at, updated_at
                FROM component_feedback
                WHERE user_id = %s
                  AND COALESCE(correlation_id, '') = COALESCE(%s, '')
                  AND COALESCE(component_id, '') = COALESCE(%s, '')
                  AND lifecycle = 'active'
                  AND created_at >= %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (actor_user_id, correlation_id, component_id, cutoff),
            )
            row = cur.fetchone()
            return _row_to_feedback_dto(row) if row else None
        finally:
            conn.close()

    def insert(
        self,
        actor_user_id: str,
        *,
        conversation_id: Optional[str],
        correlation_id: Optional[str],
        source_agent: Optional[str],
        source_tool: Optional[str],
        component_id: Optional[str],
        sentiment: str,
        category: str,
        comment_raw: Optional[str],
        comment_safety: str,
        comment_safety_reason: Optional[str],
        supersedes_id: Optional[str] = None,
    ) -> ComponentFeedbackDTO:
        """Insert a new active feedback row.

        If ``supersedes_id`` is given, that row is marked ``superseded`` and
        its ``superseded_by`` set to the new row's id, atomically with the
        insert. Caller is responsible for verifying ``supersedes_id`` belongs
        to the same user — this method assumes the check already happened.
        """
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO component_feedback (
                    user_id, conversation_id, correlation_id, source_agent,
                    source_tool, component_id, sentiment, category, comment_raw,
                    comment_safety, comment_safety_reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, user_id, conversation_id, correlation_id, source_agent,
                          source_tool, component_id, sentiment, category, comment_raw,
                          comment_safety, comment_safety_reason, lifecycle, superseded_by,
                          created_at, updated_at
                """,
                (
                    actor_user_id, conversation_id, correlation_id, source_agent,
                    source_tool, component_id, sentiment, category, comment_raw,
                    comment_safety, comment_safety_reason,
                ),
            )
            row = cur.fetchone()
            new_dto = _row_to_feedback_dto(row)

            if supersedes_id is not None:
                cur.execute(
                    """
                    UPDATE component_feedback
                    SET lifecycle = 'superseded',
                        superseded_by = %s,
                        updated_at = now()
                    WHERE id = %s AND user_id = %s AND lifecycle = 'active'
                    """,
                    (str(new_dto.id), supersedes_id, actor_user_id),
                )

            conn.commit()
            return new_dto
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_in_window(
        self,
        actor_user_id: str,
        feedback_id: str,
        *,
        sentiment: str,
        category: str,
        comment_raw: Optional[str],
        comment_safety: str,
        comment_safety_reason: Optional[str],
    ) -> Optional[ComponentFeedbackDTO]:
        """Update an existing in-window row in place. No new row created.

        Returns the updated DTO, or None if the row no longer matches the
        user (cross-user attempt — indistinguishable from not found).
        """
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE component_feedback
                SET sentiment = %s,
                    category = %s,
                    comment_raw = %s,
                    comment_safety = %s,
                    comment_safety_reason = %s,
                    updated_at = now()
                WHERE id = %s AND user_id = %s AND lifecycle = 'active'
                RETURNING id, user_id, conversation_id, correlation_id, source_agent,
                          source_tool, component_id, sentiment, category, comment_raw,
                          comment_safety, comment_safety_reason, lifecycle, superseded_by,
                          created_at, updated_at
                """,
                (sentiment, category, comment_raw, comment_safety, comment_safety_reason,
                 feedback_id, actor_user_id),
            )
            row = cur.fetchone()
            conn.commit()
            return _row_to_feedback_dto(row) if row else None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_for_user(
        self, actor_user_id: str, feedback_id: str
    ) -> Optional[ComponentFeedbackDTO]:
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, user_id, conversation_id, correlation_id, source_agent,
                       source_tool, component_id, sentiment, category, comment_raw,
                       comment_safety, comment_safety_reason, lifecycle, superseded_by,
                       created_at, updated_at
                FROM component_feedback
                WHERE id = %s AND user_id = %s
                """,
                (feedback_id, actor_user_id),
            )
            row = cur.fetchone()
            return _row_to_feedback_dto(row) if row else None
        finally:
            conn.close()

    def list_for_user(
        self,
        actor_user_id: str,
        *,
        lifecycle: str = "active",
        source_tool: Optional[str] = None,
        source_agent: Optional[str] = None,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Tuple[List[ComponentFeedbackDTO], Optional[str]]:
        """Strictly per-user list. Cursor is the last row's created_at + id, JSON-encoded."""
        clauses = ["user_id = %s", "lifecycle = %s"]
        params: List[Any] = [actor_user_id, lifecycle]

        if source_tool:
            clauses.append("source_tool = %s")
            params.append(source_tool)
        if source_agent:
            clauses.append("source_agent = %s")
            params.append(source_agent)
        if from_ts:
            clauses.append("created_at >= %s")
            params.append(from_ts)
        if to_ts:
            clauses.append("created_at <= %s")
            params.append(to_ts)
        if cursor:
            try:
                c_data = json.loads(cursor)
                clauses.append("(created_at, id::text) < (%s, %s)")
                params.append(c_data["t"])
                params.append(c_data["i"])
            except Exception:
                pass  # ignore malformed cursor

        sql = f"""
            SELECT id, user_id, conversation_id, correlation_id, source_agent,
                   source_tool, component_id, sentiment, category, comment_raw,
                   comment_safety, comment_safety_reason, lifecycle, superseded_by,
                   created_at, updated_at
            FROM component_feedback
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC, id DESC
            LIMIT %s
        """
        params.append(limit + 1)

        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            dtos = [_row_to_feedback_dto(r) for r in rows[:limit]]
            next_cursor = None
            if len(rows) > limit:
                last = dtos[-1]
                next_cursor = json.dumps({
                    "t": last.created_at.isoformat(),
                    "i": str(last.id),
                })
            return dtos, next_cursor
        finally:
            conn.close()

    def retract(
        self, actor_user_id: str, feedback_id: str
    ) -> Optional[ComponentFeedbackDTO]:
        """Mark the user's own row as retracted. Returns the updated DTO,
        or None if not found / cross-user."""
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE component_feedback
                SET lifecycle = 'retracted',
                    updated_at = now()
                WHERE id = %s AND user_id = %s AND lifecycle = 'active'
                RETURNING id, user_id, conversation_id, correlation_id, source_agent,
                          source_tool, component_id, sentiment, category, comment_raw,
                          comment_safety, comment_safety_reason, lifecycle, superseded_by,
                          created_at, updated_at
                """,
                (feedback_id, actor_user_id),
            )
            row = cur.fetchone()
            conn.commit()
            return _row_to_feedback_dto(row) if row else None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Quarantine entries
    # ------------------------------------------------------------------

    def upsert_quarantine(
        self,
        feedback_id: str,
        *,
        reason: str,
        detector: str,
    ) -> QuarantineEntryDTO:
        """Create or replace the quarantine_entry for a feedback record.

        Used by both the inline submit path (``detector='inline'``) and the
        loop pre-pass (``detector='loop_pre_pass'``). When the loop pre-pass
        flags a record the inline pass had cleared, the existing inline row
        is overwritten — the PRIMARY KEY on ``feedback_id`` enforces single-row.
        """
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO quarantine_entry (feedback_id, reason, detector, status)
                VALUES (%s, %s, %s, 'held')
                ON CONFLICT (feedback_id) DO UPDATE SET
                    reason = EXCLUDED.reason,
                    detector = EXCLUDED.detector,
                    detected_at = now(),
                    status = 'held',
                    actor_user_id = NULL,
                    actioned_at = NULL
                RETURNING feedback_id, reason, detector, detected_at, status,
                          actor_user_id, actioned_at
                """,
                (feedback_id, reason, detector),
            )
            row = cur.fetchone()
            conn.commit()
            return _row_to_quarantine_dto(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_quarantine(
        self, *, status: str = "held", limit: int = 50, cursor: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Admin-only list of quarantine entries joined with their feedback rows."""
        clauses = ["q.status = %s"]
        params: List[Any] = [status]
        if cursor:
            try:
                c_data = json.loads(cursor)
                clauses.append("(q.detected_at, q.feedback_id::text) < (%s, %s)")
                params.append(c_data["t"])
                params.append(c_data["i"])
            except Exception:
                pass

        sql = f"""
            SELECT q.feedback_id, q.reason, q.detector, q.detected_at, q.status,
                   q.actor_user_id, q.actioned_at,
                   f.user_id, f.source_agent, f.source_tool, f.comment_raw
            FROM quarantine_entry q
            JOIN component_feedback f ON f.id = q.feedback_id
            WHERE {' AND '.join(clauses)}
            ORDER BY q.detected_at DESC, q.feedback_id DESC
            LIMIT %s
        """
        params.append(limit + 1)

        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            items = [
                {
                    "feedback_id": str(r["feedback_id"]),
                    "user_id": r["user_id"],
                    "source_agent": r["source_agent"],
                    "source_tool": r["source_tool"],
                    "comment_raw": r["comment_raw"],
                    "reason": r["reason"],
                    "detector": r["detector"],
                    "detected_at": _iso(r["detected_at"]),
                    "status": r["status"],
                }
                for r in rows[:limit]
            ]
            next_cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                next_cursor = json.dumps({
                    "t": _iso(last["detected_at"]),
                    "i": str(last["feedback_id"]),
                })
            return items, next_cursor
        finally:
            conn.close()

    def quarantine_action(
        self, feedback_id: str, *, status: str, actor_user_id: str,
    ) -> Optional[QuarantineEntryDTO]:
        """Apply a 'released' or 'dismissed' action.

        Released: also flips the underlying feedback's ``comment_safety`` back
        to ``'clean'`` so subsequent synthesizer cycles pick up the comment.
        Dismissed: feedback's ``comment_safety`` stays ``'quarantined'``.
        """
        if status not in ("released", "dismissed"):
            raise ValueError(f"unsupported quarantine status transition: {status!r}")
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE quarantine_entry
                SET status = %s,
                    actor_user_id = %s,
                    actioned_at = now()
                WHERE feedback_id = %s AND status = 'held'
                RETURNING feedback_id, reason, detector, detected_at, status,
                          actor_user_id, actioned_at
                """,
                (status, actor_user_id, feedback_id),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return None

            if status == "released":
                cur.execute(
                    """
                    UPDATE component_feedback
                    SET comment_safety = 'clean',
                        comment_safety_reason = NULL,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (feedback_id,),
                )
            conn.commit()
            return _row_to_quarantine_dto(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Tool quality signals
    # ------------------------------------------------------------------

    def insert_quality_signal(self, dto: ToolQualitySignalDTO) -> ToolQualitySignalDTO:
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO tool_quality_signal (
                    agent_id, tool_name, window_start, window_end, dispatch_count,
                    failure_count, negative_feedback_count, failure_rate,
                    negative_feedback_rate, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (agent_id, tool_name, window_end) DO UPDATE SET
                    dispatch_count = EXCLUDED.dispatch_count,
                    failure_count = EXCLUDED.failure_count,
                    negative_feedback_count = EXCLUDED.negative_feedback_count,
                    failure_rate = EXCLUDED.failure_rate,
                    negative_feedback_rate = EXCLUDED.negative_feedback_rate,
                    status = EXCLUDED.status,
                    computed_at = now()
                RETURNING id, agent_id, tool_name, window_start, window_end,
                          dispatch_count, failure_count, negative_feedback_count,
                          failure_rate, negative_feedback_rate, status, computed_at
                """,
                (
                    dto.agent_id, dto.tool_name, dto.window_start, dto.window_end,
                    dto.dispatch_count, dto.failure_count, dto.negative_feedback_count,
                    dto.failure_rate, dto.negative_feedback_rate, dto.status,
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return _row_to_quality_dto(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def latest_quality_signal(
        self, agent_id: str, tool_name: str
    ) -> Optional[ToolQualitySignalDTO]:
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, agent_id, tool_name, window_start, window_end,
                       dispatch_count, failure_count, negative_feedback_count,
                       failure_rate, negative_feedback_rate, status, computed_at
                FROM tool_quality_signal
                WHERE agent_id = %s AND tool_name = %s
                ORDER BY computed_at DESC
                LIMIT 1
                """,
                (agent_id, tool_name),
            )
            row = cur.fetchone()
            return _row_to_quality_dto(row) if row else None
        finally:
            conn.close()

    def list_underperforming(
        self, *, limit: int = 50, cursor: Optional[str] = None,
    ) -> Tuple[List[ToolQualitySignalDTO], Optional[str]]:
        """List the latest snapshot per (agent, tool) where status='underperforming'."""
        clauses = []
        params: List[Any] = []
        if cursor:
            try:
                c_data = json.loads(cursor)
                clauses.append("(latest.computed_at, latest.id::text) < (%s, %s)")
                params.append(c_data["t"])
                params.append(c_data["i"])
            except Exception:
                pass
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
            WITH latest AS (
                SELECT DISTINCT ON (agent_id, tool_name)
                    id, agent_id, tool_name, window_start, window_end,
                    dispatch_count, failure_count, negative_feedback_count,
                    failure_rate, negative_feedback_rate, status, computed_at
                FROM tool_quality_signal
                ORDER BY agent_id, tool_name, computed_at DESC
            )
            SELECT * FROM latest
            {where}
            { 'AND' if where else 'WHERE' } status = 'underperforming'
            ORDER BY computed_at DESC, id DESC
            LIMIT %s
        """
        params.append(limit + 1)

        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            dtos = [_row_to_quality_dto(r) for r in rows[:limit]]
            next_cursor = None
            if len(rows) > limit:
                last = dtos[-1]
                next_cursor = json.dumps({
                    "t": last.computed_at.isoformat(),
                    "i": str(last.id),
                })
            return dtos, next_cursor
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Aggregations used by the daily quality job
    # ------------------------------------------------------------------

    def aggregate_window(
        self, window_start: datetime, window_end: datetime
    ) -> List[Dict[str, Any]]:
        """Aggregate dispatch + failure + negative-feedback counts per (agent, tool)
        over the given window. Pulls ``dispatch_count`` and ``failure_count`` from
        the audit-log via the ``agent_tool_call`` event class.
        """
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            # Tool-call audit: each dispatch produces a *.start (in_progress) and a
            # *.end row. We count by *.end with outcome='failure' for failure_count,
            # and total *.end rows for dispatch_count (regardless of outcome — that's
            # the total dispatches in the window).
            cur.execute(
                """
                WITH dispatches AS (
                    SELECT
                        agent_id,
                        REPLACE(REPLACE(action_type, 'tool.', ''), '.end', '') AS tool_name,
                        COUNT(*) AS dispatch_count,
                        COUNT(*) FILTER (WHERE outcome = 'failure') AS failure_count
                    FROM audit_events
                    WHERE event_class = 'agent_tool_call'
                      AND action_type LIKE 'tool.%%.end'
                      AND recorded_at >= %s AND recorded_at <= %s
                    GROUP BY agent_id, tool_name
                ),
                feedback_negs AS (
                    SELECT
                        source_agent AS agent_id,
                        source_tool AS tool_name,
                        COUNT(*) AS negative_feedback_count
                    FROM component_feedback
                    WHERE lifecycle = 'active'
                      AND sentiment = 'negative'
                      AND created_at >= %s AND created_at <= %s
                      AND source_tool IS NOT NULL
                    GROUP BY source_agent, source_tool
                )
                SELECT
                    COALESCE(d.agent_id, f.agent_id) AS agent_id,
                    COALESCE(d.tool_name, f.tool_name) AS tool_name,
                    COALESCE(d.dispatch_count, 0) AS dispatch_count,
                    COALESCE(d.failure_count, 0) AS failure_count,
                    COALESCE(f.negative_feedback_count, 0) AS negative_feedback_count
                FROM dispatches d
                FULL OUTER JOIN feedback_negs f
                    ON d.agent_id = f.agent_id AND d.tool_name = f.tool_name
                WHERE COALESCE(d.agent_id, f.agent_id) IS NOT NULL
                  AND COALESCE(d.tool_name, f.tool_name) IS NOT NULL
                """,
                (window_start, window_end, window_start, window_end),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def category_breakdown(
        self, agent_id: str, tool_name: str,
        window_start: datetime, window_end: datetime,
    ) -> Dict[str, int]:
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT category, COUNT(*) AS n
                FROM component_feedback
                WHERE lifecycle = 'active'
                  AND sentiment = 'negative'
                  AND source_agent = %s AND source_tool = %s
                  AND created_at >= %s AND created_at <= %s
                GROUP BY category
                """,
                (agent_id, tool_name, window_start, window_end),
            )
            return {r["category"]: r["n"] for r in cur.fetchall()}
        finally:
            conn.close()

    def evidence_ids(
        self, agent_id: str, tool_name: str,
        window_start: datetime, window_end: datetime,
        *, cap: int = 500,
    ) -> Tuple[List[str], List[str]]:
        """Return (audit_event_ids, component_feedback_ids) for a flagged tool's evidence."""
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT event_id FROM audit_events
                WHERE event_class = 'agent_tool_call'
                  AND action_type = %s
                  AND agent_id = %s
                  AND outcome = 'failure'
                  AND recorded_at >= %s AND recorded_at <= %s
                ORDER BY recorded_at DESC
                LIMIT %s
                """,
                (f"tool.{tool_name}.end", agent_id, window_start, window_end, cap),
            )
            audit_ids = [str(r["event_id"]) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT id FROM component_feedback
                WHERE lifecycle = 'active'
                  AND sentiment = 'negative'
                  AND source_agent = %s AND source_tool = %s
                  AND created_at >= %s AND created_at <= %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (agent_id, tool_name, window_start, window_end, cap),
            )
            fb_ids = [str(r["id"]) for r in cur.fetchall()]
            return audit_ids, fb_ids
        finally:
            conn.close()

    def collect_clean_comment_samples(
        self, agent_id: str, tool_name: str, window_start: datetime, window_end: datetime,
        *, cap: int = 5,
    ) -> List[Dict[str, Any]]:
        """A bounded sample of clean negative-feedback comments for synthesizer input."""
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, category, comment_raw, created_at
                FROM component_feedback
                WHERE lifecycle = 'active'
                  AND sentiment = 'negative'
                  AND comment_safety = 'clean'
                  AND comment_raw IS NOT NULL
                  AND comment_raw <> ''
                  AND source_agent = %s AND source_tool = %s
                  AND created_at >= %s AND created_at <= %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (agent_id, tool_name, window_start, window_end, cap),
            )
            return [
                {"id": str(r["id"]), "category": r["category"],
                 "comment": r["comment_raw"], "created_at": _iso(r["created_at"])}
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Knowledge update proposals
    # ------------------------------------------------------------------

    def insert_proposal(
        self,
        *,
        agent_id: str,
        tool_name: str,
        artifact_path: str,
        diff_payload: str,
        artifact_sha_at_gen: str,
        evidence: Dict[str, Any],
    ) -> KnowledgeUpdateProposalDTO:
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            # Supersede any earlier pending proposal for the same (agent, tool).
            cur.execute(
                """
                UPDATE knowledge_update_proposal
                SET status = 'superseded'
                WHERE agent_id = %s AND tool_name = %s AND status = 'pending'
                """,
                (agent_id, tool_name),
            )
            cur.execute(
                """
                INSERT INTO knowledge_update_proposal (
                    agent_id, tool_name, artifact_path, diff_payload,
                    artifact_sha_at_gen, evidence
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id, agent_id, tool_name, artifact_path, diff_payload,
                          artifact_sha_at_gen, evidence, status, reviewer_user_id,
                          reviewed_at, reviewer_rationale, applied_at, generated_at
                """,
                (agent_id, tool_name, artifact_path, diff_payload,
                 artifact_sha_at_gen, json.dumps(evidence)),
            )
            row = cur.fetchone()
            conn.commit()
            return _row_to_proposal_dto(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_proposal(self, proposal_id: str) -> Optional[KnowledgeUpdateProposalDTO]:
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, agent_id, tool_name, artifact_path, diff_payload,
                       artifact_sha_at_gen, evidence, status, reviewer_user_id,
                       reviewed_at, reviewer_rationale, applied_at, generated_at
                FROM knowledge_update_proposal
                WHERE id = %s
                """,
                (proposal_id,),
            )
            row = cur.fetchone()
            return _row_to_proposal_dto(row) if row else None
        finally:
            conn.close()

    def list_proposals(
        self,
        *,
        status: Optional[str] = None,
        agent_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Tuple[List[KnowledgeUpdateProposalDTO], Optional[str]]:
        clauses = []
        params: List[Any] = []
        if status:
            clauses.append("status = %s")
            params.append(status)
        if agent_id:
            clauses.append("agent_id = %s")
            params.append(agent_id)
        if tool_name:
            clauses.append("tool_name = %s")
            params.append(tool_name)
        if cursor:
            try:
                c_data = json.loads(cursor)
                clauses.append("(generated_at, id::text) < (%s, %s)")
                params.append(c_data["t"])
                params.append(c_data["i"])
            except Exception:
                pass

        sql = f"""
            SELECT id, agent_id, tool_name, artifact_path, diff_payload,
                   artifact_sha_at_gen, evidence, status, reviewer_user_id,
                   reviewed_at, reviewer_rationale, applied_at, generated_at
            FROM knowledge_update_proposal
            { ('WHERE ' + ' AND '.join(clauses)) if clauses else '' }
            ORDER BY generated_at DESC, id DESC
            LIMIT %s
        """
        params.append(limit + 1)

        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            dtos = [_row_to_proposal_dto(r) for r in rows[:limit]]
            next_cursor = None
            if len(rows) > limit:
                last = dtos[-1]
                next_cursor = json.dumps({
                    "t": last.generated_at.isoformat(),
                    "i": str(last.id),
                })
            return dtos, next_cursor
        finally:
            conn.close()

    def transition_proposal(
        self,
        proposal_id: str,
        *,
        new_status: str,
        reviewer_user_id: str,
        reviewer_rationale: Optional[str] = None,
        applied: bool = False,
    ) -> Optional[KnowledgeUpdateProposalDTO]:
        """Atomic state transition for accept / reject / apply."""
        sets = ["status = %s", "reviewer_user_id = %s", "reviewed_at = now()"]
        params: List[Any] = [new_status, reviewer_user_id]
        if reviewer_rationale is not None:
            sets.append("reviewer_rationale = %s")
            params.append(reviewer_rationale)
        if applied:
            sets.append("applied_at = now()")
        params.append(proposal_id)

        sql = f"""
            UPDATE knowledge_update_proposal
            SET {', '.join(sets)}
            WHERE id = %s
            RETURNING id, agent_id, tool_name, artifact_path, diff_payload,
                      artifact_sha_at_gen, evidence, status, reviewer_user_id,
                      reviewed_at, reviewer_rationale, applied_at, generated_at
        """
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
            conn.commit()
            return _row_to_proposal_dto(row) if row else None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def pending_count(self) -> int:
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS n FROM knowledge_update_proposal WHERE status = 'pending'")
            return int(cur.fetchone()["n"])
        finally:
            conn.close()

    def underperforming_count(self) -> int:
        """Count of distinct (agent, tool) currently in 'underperforming' state."""
        conn = self._db._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (agent_id, tool_name) status
                    FROM tool_quality_signal
                    ORDER BY agent_id, tool_name, computed_at DESC
                )
                SELECT COUNT(*) AS n FROM latest WHERE status = 'underperforming'
                """
            )
            return int(cur.fetchone()["n"])
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Row mappers
# ---------------------------------------------------------------------------

def _row_to_feedback_dto(row: Any) -> ComponentFeedbackDTO:
    return ComponentFeedbackDTO(
        id=str(row["id"]),
        user_id=row["user_id"],
        conversation_id=row["conversation_id"],
        correlation_id=row["correlation_id"],
        source_agent=row["source_agent"],
        source_tool=row["source_tool"],
        component_id=row["component_id"],
        sentiment=row["sentiment"],
        category=row["category"],
        comment_raw=row["comment_raw"],
        comment_safety=row["comment_safety"],
        comment_safety_reason=row["comment_safety_reason"],
        lifecycle=row["lifecycle"],
        superseded_by=str(row["superseded_by"]) if row["superseded_by"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_quality_dto(row: Any) -> ToolQualitySignalDTO:
    return ToolQualitySignalDTO(
        id=str(row["id"]),
        agent_id=row["agent_id"],
        tool_name=row["tool_name"],
        window_start=row["window_start"],
        window_end=row["window_end"],
        dispatch_count=row["dispatch_count"],
        failure_count=row["failure_count"],
        negative_feedback_count=row["negative_feedback_count"],
        failure_rate=float(row["failure_rate"]),
        negative_feedback_rate=float(row["negative_feedback_rate"]),
        status=row["status"],
        computed_at=row["computed_at"],
    )


def _row_to_proposal_dto(row: Any) -> KnowledgeUpdateProposalDTO:
    evidence = row["evidence"]
    if isinstance(evidence, str):
        evidence = json.loads(evidence)
    return KnowledgeUpdateProposalDTO(
        id=str(row["id"]),
        agent_id=row["agent_id"],
        tool_name=row["tool_name"],
        artifact_path=row["artifact_path"],
        diff_payload=row["diff_payload"],
        artifact_sha_at_gen=row["artifact_sha_at_gen"],
        evidence=evidence or {},
        status=row["status"],
        reviewer_user_id=row["reviewer_user_id"],
        reviewed_at=row["reviewed_at"],
        reviewer_rationale=row["reviewer_rationale"],
        applied_at=row["applied_at"],
        generated_at=row["generated_at"],
    )


def _row_to_quarantine_dto(row: Any) -> QuarantineEntryDTO:
    return QuarantineEntryDTO(
        feedback_id=str(row["feedback_id"]),
        reason=row["reason"],
        detector=row["detector"],
        detected_at=row["detected_at"],
        status=row["status"],
        actor_user_id=row["actor_user_id"],
        actioned_at=row["actioned_at"],
    )


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None
