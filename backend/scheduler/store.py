"""Durable persistence for scheduled jobs and runs (feature 025, US5).

Thin repository over the shared ``Database`` (same convention as the audit /
onboarding / personalization repositories). All methods are user-scoped except
the scheduler-internal ``list_due`` / ``reconcile_interrupted`` which operate
across users for the single in-process scheduler loop.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

ACTIVE_STATUSES = ("active",)


def _now_ms() -> int:
    return int(time.time() * 1000)


class ScheduledJobStore:
    def __init__(self, db) -> None:
        self.db = db

    # ── Jobs ─────────────────────────────────────────────────────────────

    def count_active(self, user_id: str) -> int:
        row = self.db.fetch_one(
            "SELECT COUNT(*) AS n FROM scheduled_job WHERE user_id = ? AND status = 'active'",
            (user_id,),
        )
        return int(row["n"]) if row else 0

    def create_job(
        self, user_id: str, *, name: str, instruction: str, schedule_kind: str,
        schedule_expr: str, timezone: str, consented_scopes: List[str],
        agent_id: Optional[str], target_chat_id: Optional[str],
        next_run_at: Optional[int], offline_grant_id: Optional[str],
    ) -> Dict[str, Any]:
        job_id = str(uuid.uuid4())
        now = _now_ms()
        self.db.execute(
            """INSERT INTO scheduled_job
                   (id, user_id, agent_id, name, instruction, schedule_kind, schedule_expr,
                    timezone, consented_scopes, delivery, status, target_chat_id,
                    next_run_at, last_run_at, offline_grant_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, 'in_app', 'active', ?, ?, NULL, ?, ?, ?)""",
            (job_id, user_id, agent_id, name, instruction, schedule_kind, schedule_expr,
             timezone, json.dumps(consented_scopes), target_chat_id, next_run_at,
             offline_grant_id, now, now),
        )
        return self.get_job(user_id, job_id)  # type: ignore[return-value]

    def get_job(self, user_id: str, job_id: str) -> Optional[Dict[str, Any]]:
        row = self.db.fetch_one(
            "SELECT * FROM scheduled_job WHERE id = ? AND user_id = ?", (job_id, user_id)
        )
        return dict(row) if row else None

    def list_jobs(self, user_id: str) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT * FROM scheduled_job WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        )
        return [dict(r) for r in rows]

    def set_offline_grant(self, user_id: str, job_id: str, grant_id: Optional[str]) -> bool:
        """Attach (or clear) the captured offline-grant id on a job (030 FR-003 / 025 T042).

        Written by the WS consent-capture flow after ``OfflineGrantStore.capture``
        so the runner can mint a fresh token per run. Until set, ``offline_grant_id``
        is NULL and the runner refuses to execute (``skipped_auth``)."""
        cur = self.db.execute(
            "UPDATE scheduled_job SET offline_grant_id = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (grant_id, _now_ms(), job_id, user_id),
        )
        return getattr(cur, "rowcount", 0) > 0

    def set_status(self, user_id: str, job_id: str, status: str) -> bool:
        cur = self.db.execute(
            "UPDATE scheduled_job SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (status, _now_ms(), job_id, user_id),
        )
        return getattr(cur, "rowcount", 0) > 0

    def update_after_run(self, job_id: str, *, last_run_at: int, next_run_at: Optional[int],
                         completed: bool) -> None:
        status_clause = "status = 'completed', " if completed else ""
        self.db.execute(
            f"""UPDATE scheduled_job SET {status_clause} last_run_at = ?, next_run_at = ?,
                   updated_at = ? WHERE id = ?""",
            (last_run_at, next_run_at, _now_ms(), job_id),
        )

    # ── Scheduler-internal (cross-user) ──────────────────────────────────

    def list_due(self, now_ms: int) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            """SELECT * FROM scheduled_job
               WHERE status = 'active' AND next_run_at IS NOT NULL AND next_run_at <= ?
               ORDER BY next_run_at ASC""",
            (now_ms,),
        )
        return [dict(r) for r in rows]

    # ── Runs ─────────────────────────────────────────────────────────────

    def start_run(self, job_id: str, user_id: str, correlation_id: str) -> str:
        run_id = str(uuid.uuid4())
        self.db.execute(
            """INSERT INTO job_run (id, job_id, user_id, started_at, outcome, correlation_id)
               VALUES (?, ?, ?, ?, 'running', ?)""",
            (run_id, job_id, user_id, _now_ms(), correlation_id),
        )
        return run_id

    def finish_run(self, run_id: str, *, outcome: str, summary: Optional[str] = None,
                   auth_ref: Optional[str] = None) -> None:
        self.db.execute(
            "UPDATE job_run SET ended_at = ?, outcome = ?, summary = ?, auth_ref = ? WHERE id = ?",
            (_now_ms(), outcome, summary, auth_ref, run_id),
        )

    def list_runs(self, user_id: str, job_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            """SELECT * FROM job_run WHERE job_id = ? AND user_id = ?
               ORDER BY started_at DESC LIMIT ?""",
            (job_id, user_id, limit),
        )
        return [dict(r) for r in rows]

    def reconcile_interrupted(self) -> int:
        """On startup, mark any run left 'running' (by a crash/restart) as interrupted."""
        cur = self.db.execute(
            "UPDATE job_run SET outcome = 'interrupted', ended_at = ? WHERE outcome = 'running'",
            (_now_ms(),),
        )
        return getattr(cur, "rowcount", 0)
