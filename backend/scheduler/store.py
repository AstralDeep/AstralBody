"""Durable scheduled jobs, occurrence claims, attempts, and effect fencing.

Feature 060 keeps the feature-025 job APIs as compatibility methods while
making PostgreSQL ``scheduled_occurrence`` and ``effect_ledger`` rows the only
execution authority.  New scheduler workers never dispatch from ``list_due``;
they materialize, advance, and claim in one transaction and carry both the
occurrence and accepted-operation fences through every mutation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Dict, Iterator, List, Optional

from orchestrator.work_admission import (
    AdmissionClass,
    ExecutionFence,
    OperationNotFoundError,
    OperationOwner,
    OperationRequest,
    OperationState,
    OwnerScope,
    RefusedAdmission,
    StaleExecutionFenceError,
    WorkAdmissionCoordinator,
)
from orchestrator.scheduled_publication import ScheduledHistoryBatch

from .cron import compute_next_run_ms


logger = logging.getLogger("scheduler.store")

ACTIVE_STATUSES = ("active",)
_SAFE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_INSTANCE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class StaleOccurrenceClaimError(RuntimeError):
    """The supplied occurrence token/generation no longer owns the row."""

    def __init__(self, code: str, *, terminal_code: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.terminal_code = terminal_code


class ScheduleActionError(RuntimeError):
    """Safe, owner-scoped refusal from a scheduler definition action."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EffectIdempotencyConflictError(RuntimeError):
    """One effect key was reused with different normalized payload bytes."""


class ScheduledAdmissionRefusedError(RuntimeError):
    """The scheduled operation could not enter its finite admission queue."""

    def __init__(self, refusal: RefusedAdmission) -> None:
        super().__init__(refusal.code)
        self.code = refusal.code
        self.retryable = refusal.retryable
        self.retry_after_ms = refusal.retry_after_ms


@dataclass(frozen=True)
class OccurrenceClaim:
    """One current PostgreSQL claim for a stable scheduled occurrence."""

    occurrence_id: uuid.UUID
    job: Dict[str, Any]
    scheduled_for: datetime
    claim_generation: int
    lease_token: uuid.UUID
    lease_owner: str
    lease_expires_at: datetime
    attempt_number: int
    parent_operation_id: uuid.UUID | None


@dataclass(frozen=True)
class ScheduledAttempt:
    """Attempt-scoped accepted operation attached to an occurrence claim."""

    claim: OccurrenceClaim
    operation_id: uuid.UUID
    operation_state: OperationState
    execution_fence: ExecutionFence | None
    parent_operation_id: uuid.UUID | None
    run_id: uuid.UUID | None = None
    request_generation: uuid.UUID | None = None

    @property
    def job(self) -> Dict[str, Any]:
        return self.claim.job


@dataclass(frozen=True)
class EffectReservation:
    """Safe effect-ledger reconciliation result."""

    state: str
    created: bool
    ambiguous: bool


@dataclass(frozen=True)
class RunNowMaterialization:
    """Canonical result of one owner-scoped run-now submission."""

    occurrence_id: uuid.UUID
    job_id: uuid.UUID
    owner_user_id: str
    scheduled_for: datetime
    state: str
    created: bool


def _as_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _now_ms() -> int:
    return int(time.time() * 1000)


class ScheduledJobStore:
    def __init__(
        self,
        db,
        *,
        coordinator: WorkAdmissionCoordinator | None = None,
    ) -> None:
        self.db = db
        self._coordinator = coordinator

    def bind_coordinator(self, coordinator: WorkAdmissionCoordinator) -> None:
        """Bind the shared production operation authority exactly once."""

        if self._coordinator is not None and self._coordinator is not coordinator:
            raise RuntimeError("cannot replace the scheduler operation coordinator")
        self._coordinator = coordinator

    def _require_coordinator(self) -> WorkAdmissionCoordinator:
        if self._coordinator is None:
            raise RuntimeError(
                "durable scheduler execution requires a WorkAdmissionCoordinator"
            )
        return self._coordinator

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        connection = self.db._get_connection()
        try:
            cursor = connection.cursor()
            yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _validate_claim_settings(
        instance_id: str, *, limit: int, lease_seconds: int
    ) -> None:
        if not _INSTANCE_RE.fullmatch(instance_id):
            raise ValueError("instance_id must be a bounded non-sensitive identifier")
        if limit <= 0 or limit > 1_000:
            raise ValueError("claim limit must be between 1 and 1000")
        if lease_seconds < 5 or lease_seconds > 60:
            raise ValueError("scheduled claim lease must be between 5 and 60 seconds")

    @staticmethod
    def _claim_matches(row: Dict[str, Any], claim: OccurrenceClaim) -> bool:
        return (
            _as_uuid(row.get("occurrence_id")) == claim.occurrence_id
            and int(row.get("claim_generation") or 0) == claim.claim_generation
            and _as_uuid(row.get("lease_token")) == claim.lease_token
            and row.get("lease_owner") == claim.lease_owner
        )

    @staticmethod
    def _owner(claim: OccurrenceClaim) -> OperationOwner:
        return OperationOwner(
            owner_scope=OwnerScope.SCHEDULE,
            owner_user_id=str(claim.job["user_id"]),
            connection_scope_id=None,
        )

    # ── Jobs ─────────────────────────────────────────────────────────────

    def count_active(self, user_id: str) -> int:
        row = self.db.fetch_one(
            "SELECT COUNT(*) AS n FROM scheduled_job WHERE user_id = ? AND status = 'active'",
            (user_id,),
        )
        return int(row["n"]) if row else 0

    def create_job(
        self,
        user_id: str,
        *,
        name: str,
        instruction: str,
        schedule_kind: str,
        schedule_expr: str,
        timezone: str,
        consented_scopes: List[str],
        agent_id: Optional[str],
        target_chat_id: Optional[str],
        next_run_at: Optional[int],
        offline_grant_id: Optional[str],
    ) -> Dict[str, Any]:
        job_id = str(uuid.uuid4())
        now = _now_ms()
        self.db.execute(
            """INSERT INTO scheduled_job
                   (id, user_id, agent_id, name, instruction, schedule_kind, schedule_expr,
                    timezone, consented_scopes, delivery, status, target_chat_id,
                    next_run_at, last_run_at, offline_grant_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, 'in_app', 'active', ?, ?, NULL, ?, ?, ?)""",
            (
                job_id,
                user_id,
                agent_id,
                name,
                instruction,
                schedule_kind,
                schedule_expr,
                timezone,
                json.dumps(consented_scopes),
                target_chat_id,
                next_run_at,
                offline_grant_id,
                now,
                now,
            ),
        )
        return self.get_job(user_id, job_id)  # type: ignore[return-value]

    def get_job(self, user_id: str, job_id: str) -> Optional[Dict[str, Any]]:
        row = self.db.fetch_one(
            "SELECT * FROM scheduled_job WHERE id = ? AND user_id = ?",
            (job_id, user_id),
        )
        return dict(row) if row else None

    def list_jobs(self, user_id: str) -> List[Dict[str, Any]]:
        rows = self.db.fetch_all(
            "SELECT * FROM scheduled_job WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        return [dict(r) for r in rows]

    def set_offline_grant(
        self, user_id: str, job_id: str, grant_id: Optional[str]
    ) -> bool:
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

    @staticmethod
    def _run_now_result(
        row: Dict[str, Any], *, created: bool
    ) -> RunNowMaterialization:
        occurrence_id = _as_uuid(row.get("occurrence_id"))
        job_id = _as_uuid(row.get("job_id"))
        if occurrence_id is None or job_id is None:
            raise RuntimeError("run-now occurrence identity is invalid")
        return RunNowMaterialization(
            occurrence_id=occurrence_id,
            job_id=job_id,
            owner_user_id=str(row["owner_user_id"]),
            scheduled_for=_utc(row["scheduled_for"]),
            state=str(row["state"]),
            created=created,
        )

    def materialize_run_now(
        self,
        *,
        user_id: str,
        job_id: str,
        submission_id: uuid.UUID,
        eligibility: Callable[[Dict[str, Any]], Any] | None = None,
    ) -> RunNowMaterialization:
        """Create or reconcile one manual firing without changing cadence."""

        try:
            job_identity = uuid.UUID(str(job_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ScheduleActionError("job_not_found") from exc
        try:
            submission_identity = uuid.UUID(str(submission_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ScheduleActionError("invalid_submission_id") from exc
        if submission_identity.version != 4:
            raise ScheduleActionError("invalid_submission_id")

        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM scheduled_job
                WHERE id = %s AND user_id = %s
                FOR UPDATE
                """,
                (str(job_identity), user_id),
            )
            job_row = cursor.fetchone()
            if job_row is None:
                raise ScheduleActionError("job_not_found")
            job = dict(job_row)

            cursor.execute(
                """
                SELECT * FROM scheduled_occurrence
                WHERE owner_user_id = %s AND run_now_submission_id = %s
                FOR UPDATE
                """,
                (user_id, str(submission_identity)),
            )
            existing = cursor.fetchone()
            if existing is not None:
                if _as_uuid(existing["job_id"]) != job_identity:
                    raise ScheduleActionError("idempotency_conflict")
                return self._run_now_result(dict(existing), created=False)

            if str(job.get("status") or "") != "active":
                raise ScheduleActionError("job_not_active")
            if eligibility is not None:
                decision = eligibility(job)
                if not bool(getattr(decision, "eligible", decision)):
                    code = str(
                        getattr(decision, "code", None)
                        or "handler_not_idempotent"
                    )
                    if code not in {
                        "handler_not_idempotent",
                        "handler_downstream_idempotency_unreviewed",
                    }:
                        code = "handler_not_idempotent"
                    raise ScheduleActionError(code)

            cursor.execute("SELECT clock_timestamp() AS now")
            database_now = _utc(cursor.fetchone()["now"])
            occurrence_id = uuid.uuid4()
            scheduled_for = database_now
            for collision in range(32):
                cursor.execute(
                    """
                    INSERT INTO scheduled_occurrence (
                        occurrence_id, job_id, owner_user_id, scheduled_for,
                        run_now_submission_id, state, first_eligible_at,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, 'pending', %s, %s, %s
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING *
                    """,
                    (
                        str(occurrence_id),
                        str(job_identity),
                        user_id,
                        scheduled_for,
                        str(submission_identity),
                        database_now,
                        database_now,
                        database_now,
                    ),
                )
                inserted = cursor.fetchone()
                if inserted is not None:
                    return self._run_now_result(dict(inserted), created=True)

                cursor.execute(
                    """
                    SELECT * FROM scheduled_occurrence
                    WHERE owner_user_id = %s AND run_now_submission_id = %s
                    FOR UPDATE
                    """,
                    (user_id, str(submission_identity)),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    if _as_uuid(existing["job_id"]) != job_identity:
                        raise ScheduleActionError("idempotency_conflict")
                    return self._run_now_result(dict(existing), created=False)
                scheduled_for = database_now - timedelta(
                    microseconds=collision + 1
                )

        raise ScheduleActionError("run_now_timestamp_conflict")

    def set_status_and_cancel_unstarted(
        self,
        *,
        user_id: str,
        job_id: str,
        status: str,
        terminal_code: str,
    ) -> bool:
        """Transition a job and atomically cancel every unstarted occurrence."""

        expected_codes = {
            "paused": "cancelled_job_paused",
            "disabled": "cancelled_job_deleted",
        }
        if expected_codes.get(status) != terminal_code:
            raise ValueError("status and scheduler cancellation code disagree")
        try:
            job_identity = uuid.UUID(str(job_id))
        except (TypeError, ValueError, AttributeError):
            return False

        coordinator = self._require_coordinator()
        owner = OperationOwner(
            owner_scope=OwnerScope.SCHEDULE,
            owner_user_id=user_id,
            connection_scope_id=None,
        )
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT id FROM scheduled_job
                WHERE id = %s AND user_id = %s
                FOR UPDATE
                """,
                (str(job_identity), user_id),
            )
            if cursor.fetchone() is None:
                return False
            cursor.execute(
                """
                UPDATE scheduled_job
                SET status = %s,
                    updated_at = (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::BIGINT
                WHERE id = %s AND user_id = %s
                """,
                (status, str(job_identity), user_id),
            )
            cursor.execute(
                """
                SELECT occurrence_id, state, current_operation_id
                FROM scheduled_occurrence
                WHERE job_id = %s
                  AND state IN ('pending', 'retryable', 'claimed')
                ORDER BY occurrence_id
                """,
                (str(job_identity),),
            )
            candidates = [dict(row) for row in cursor.fetchall()]

            for candidate in candidates:
                occurrence_id = _as_uuid(candidate["occurrence_id"])
                operation_id = _as_uuid(candidate.get("current_operation_id"))
                if occurrence_id is None:
                    raise RuntimeError("scheduled occurrence identity is invalid")

                operation = None
                if operation_id is not None:
                    try:
                        operation = coordinator.cancel(
                            owner=owner,
                            operation_id=operation_id,
                            terminal_code=terminal_code,
                            request_running=False,
                            transaction=cursor,
                        )
                    except OperationNotFoundError:
                        operation = None

                cursor.execute(
                    """
                    SELECT state, current_operation_id
                    FROM scheduled_occurrence
                    WHERE occurrence_id = %s
                    FOR UPDATE
                    """,
                    (str(occurrence_id),),
                )
                current = cursor.fetchone()
                if current is None or str(current["state"]) == "running":
                    continue
                if str(current["state"]) not in {
                    "pending",
                    "retryable",
                    "claimed",
                }:
                    continue

                current_operation_id = _as_uuid(current["current_operation_id"])
                if current_operation_id != operation_id:
                    raise RuntimeError(
                        "scheduled occurrence operation changed during status transition"
                    )
                if operation_id is not None and operation is None:
                    raise RuntimeError(
                        "scheduled occurrence references a missing operation"
                    )
                if operation is not None and operation.state is OperationState.RUNNING:
                    if operation.execution_lease_token is None:
                        raise RuntimeError("running operation has no execution fence")
                    coordinator.terminalize(
                        ExecutionFence(
                            operation_id=operation.operation_id,
                            execution_generation=operation.execution_generation,
                            execution_lease_token=operation.execution_lease_token,
                        ),
                        state=OperationState.CANCELLED,
                        terminal_code=terminal_code,
                        safe_summary="Scheduled job cancelled before start",
                        retry_after_ms=None,
                        transaction=cursor,
                    )

                cursor.execute(
                    """
                    UPDATE scheduled_occurrence
                    SET state = 'cancelled',
                        lease_token = NULL,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        next_attempt_at = NULL,
                        terminal_at = clock_timestamp(),
                        result_code = %s,
                        last_error_code = %s,
                        updated_at = clock_timestamp()
                    WHERE occurrence_id = %s
                      AND state IN ('pending', 'retryable', 'claimed')
                    """,
                    (terminal_code, terminal_code, str(occurrence_id)),
                )
        return True

    def update_after_run(
        self,
        job_id: str,
        *,
        last_run_at: int,
        next_run_at: Optional[int],
        completed: bool,
    ) -> None:
        status_clause = "status = 'completed', " if completed else ""
        self.db.execute(
            f"""UPDATE scheduled_job SET {status_clause} last_run_at = ?, next_run_at = ?,
                   updated_at = ? WHERE id = ?""",
            (last_run_at, next_run_at, _now_ms(), job_id),
        )

    # ── Scheduler-internal (cross-user) ──────────────────────────────────

    def list_due(self, now_ms: int) -> List[Dict[str, Any]]:
        """Legacy read-only due list; feature-060 execution does not use it."""

        rows = self.db.fetch_all(
            """SELECT * FROM scheduled_job
               WHERE status = 'active' AND next_run_at IS NOT NULL AND next_run_at <= ?
               ORDER BY next_run_at ASC""",
            (now_ms,),
        )
        return [dict(r) for r in rows]

    # ── Feature 060 occurrence authority ────────────────────────────────

    def materialize_and_claim_due(
        self,
        instance_id: str,
        *,
        limit: int = 20,
        lease_seconds: int = 15,
        eligibility: Callable[[Dict[str, Any]], Any] | None = None,
    ) -> tuple[OccurrenceClaim, ...]:
        """Materialize due jobs, advance them, and claim occurrences atomically.

        ``eligibility`` is a pure pre-materialization handler declaration
        check.  A false decision leaves the job untouched; no occurrence or
        accepted operation is fabricated for an ineligible handler.
        """

        self._validate_claim_settings(
            instance_id, limit=limit, lease_seconds=lease_seconds
        )
        claims: list[OccurrenceClaim] = []
        prior_attempts: list[tuple[uuid.UUID, int, uuid.UUID, str]] = []
        with self._transaction() as cursor:
            cursor.execute("SELECT clock_timestamp() AS now")
            database_now = _utc(cursor.fetchone()["now"])
            database_now_ms = int(database_now.timestamp() * 1000)

            cursor.execute(
                """
                SELECT *
                FROM scheduled_job
                WHERE status = 'active'
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= %s
                ORDER BY next_run_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (database_now_ms, limit),
            )
            due_jobs = [dict(row) for row in cursor.fetchall()]
            for job in due_jobs:
                decision = eligibility(job) if eligibility is not None else None
                if decision is not None and not bool(
                    getattr(decision, "eligible", decision)
                ):
                    logger.warning(
                        "scheduler.handler_ineligible",
                        extra={
                            "job_id": str(job["id"]),
                            "code": "handler_not_idempotent",
                        },
                    )
                    continue
                scheduled_ms = int(job["next_run_at"])
                scheduled_for = datetime.fromtimestamp(scheduled_ms / 1000, tz=UTC)
                occurrence_id = uuid.uuid4()
                cursor.execute(
                    """
                    INSERT INTO scheduled_occurrence (
                        occurrence_id, job_id, owner_user_id, scheduled_for,
                        state, first_eligible_at, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s)
                    ON CONFLICT (job_id, scheduled_for) DO NOTHING
                    """,
                    (
                        str(occurrence_id),
                        str(job["id"]),
                        str(job["user_id"]),
                        scheduled_for,
                        database_now,
                        database_now,
                        database_now,
                    ),
                )
                next_run_at = compute_next_run_ms(
                    str(job["schedule_kind"]),
                    str(job["schedule_expr"]),
                    str(job.get("timezone") or "UTC"),
                    scheduled_ms,
                )
                completed = (
                    str(job["schedule_kind"]) == "one_shot" or next_run_at is None
                )
                cursor.execute(
                    """
                    UPDATE scheduled_job
                    SET next_run_at = %s,
                        status = CASE WHEN %s THEN 'completed' ELSE status END,
                        updated_at = %s
                    WHERE id = %s AND next_run_at = %s
                    """,
                    (
                        next_run_at,
                        completed,
                        database_now_ms,
                        str(job["id"]),
                        scheduled_ms,
                    ),
                )

            cursor.execute(
                """
                SELECT occurrence.occurrence_id AS occurrence_identity,
                       occurrence.scheduled_for,
                       occurrence.claim_generation AS occurrence_claim_generation,
                       occurrence.attempt_count AS occurrence_attempt_count,
                       occurrence.current_operation_id AS occurrence_operation_id,
                       to_jsonb(job) AS job_record,
                       operation.state AS prior_operation_state,
                       operation.execution_generation AS prior_execution_generation,
                       operation.execution_lease_token AS prior_execution_lease_token
                FROM scheduled_occurrence AS occurrence
                JOIN scheduled_job AS job ON job.id = occurrence.job_id
                LEFT JOIN operation_record AS operation
                  ON operation.operation_id = occurrence.current_operation_id
                WHERE (
                    job.status = 'active'
                    OR (job.status = 'completed' AND job.schedule_kind = 'one_shot')
                )
                  AND (
                    (occurrence.state = 'pending'
                        AND occurrence.scheduled_for <= %s)
                    OR (occurrence.state = 'retryable'
                        AND (occurrence.next_attempt_at IS NULL
                             OR occurrence.next_attempt_at <= %s))
                    OR (occurrence.state IN ('claimed', 'running')
                        AND occurrence.lease_expires_at <= %s)
                )
                ORDER BY occurrence.scheduled_for, occurrence.occurrence_id
                FOR UPDATE OF occurrence SKIP LOCKED
                LIMIT %s
                """,
                (database_now, database_now, database_now, limit),
            )
            candidates = [dict(row) for row in cursor.fetchall()]
            for row in candidates:
                job = dict(row["job_record"])
                decision = eligibility(job) if eligibility is not None else None
                if decision is not None and not bool(
                    getattr(decision, "eligible", decision)
                ):
                    continue
                occurrence_id = _as_uuid(row["occurrence_identity"])
                assert occurrence_id is not None
                parent_operation_id = _as_uuid(row["occurrence_operation_id"])
                prior_generation = int(row.get("prior_execution_generation") or 0)
                prior_token = _as_uuid(row.get("prior_execution_lease_token"))
                prior_state = row.get("prior_operation_state")
                if parent_operation_id is not None and prior_state in {
                    "queued",
                    "running",
                }:
                    prior_attempts.append(
                        (
                            parent_operation_id,
                            prior_generation,
                            prior_token or uuid.UUID(int=0),
                            str(prior_state),
                        )
                    )
                claim_generation = int(row["occurrence_claim_generation"]) + 1
                attempt_number = int(row["occurrence_attempt_count"]) + 1
                lease_token = uuid.uuid4()
                cursor.execute(
                    """
                    UPDATE scheduled_occurrence
                    SET state = 'claimed',
                        lease_token = %s,
                        claim_generation = %s,
                        lease_owner = %s,
                        lease_expires_at = %s + (%s * INTERVAL '1 second'),
                        attempt_count = %s,
                        current_operation_id = NULL,
                        operation_execution_generation = NULL,
                        started_at = NULL,
                        terminal_at = NULL,
                        next_attempt_at = NULL,
                        result_code = NULL,
                        updated_at = %s
                    WHERE occurrence_id = %s
                    RETURNING lease_expires_at
                    """,
                    (
                        str(lease_token),
                        claim_generation,
                        instance_id,
                        database_now,
                        lease_seconds,
                        attempt_number,
                        database_now,
                        str(occurrence_id),
                    ),
                )
                lease_expires_at = _utc(cursor.fetchone()["lease_expires_at"])
                claims.append(
                    OccurrenceClaim(
                        occurrence_id=occurrence_id,
                        job=job,
                        scheduled_for=_utc(row["scheduled_for"]),
                        claim_generation=claim_generation,
                        lease_token=lease_token,
                        lease_owner=instance_id,
                        lease_expires_at=lease_expires_at,
                        attempt_number=attempt_number,
                        parent_operation_id=parent_operation_id,
                    )
                )

        for operation_id, generation, token, state in prior_attempts:
            self._terminalize_recovered_attempt(
                operation_id=operation_id,
                execution_generation=generation,
                execution_lease_token=token,
                state=state,
            )
        return tuple(claims)

    def _terminalize_recovered_attempt(
        self,
        *,
        operation_id: uuid.UUID,
        execution_generation: int,
        execution_lease_token: uuid.UUID,
        state: str,
    ) -> None:
        """Settle the prior operation before its replacement is allocated."""

        coordinator = self._coordinator
        if (
            coordinator is not None
            and state == "running"
            and execution_generation > 0
            and execution_lease_token.int != 0
        ):
            try:
                coordinator.terminalize(
                    ExecutionFence(
                        operation_id=operation_id,
                        execution_generation=execution_generation,
                        execution_lease_token=execution_lease_token,
                    ),
                    state=OperationState.RETRYABLE,
                    terminal_code="claim_lost",
                    safe_summary="Scheduled claim expired before completion",
                    retry_after_ms=0,
                )
                return
            except StaleExecutionFenceError:
                pass

        if coordinator is not None and state in {"queued", "running"}:
            coordinator.terminalize_unselected(
                operation_id,
                terminal_code="claim_lost",
                safe_summary="Scheduled claim expired before start",
                retry_after_ms=0,
            )

    def renew_claim(
        self, claim: OccurrenceClaim, *, lease_seconds: int = 15
    ) -> datetime | None:
        """Renew one unexpired current claim using PostgreSQL time."""

        self._validate_claim_settings(
            claim.lease_owner, limit=1, lease_seconds=lease_seconds
        )
        with self._transaction() as cursor:
            cursor.execute(
                """
                UPDATE scheduled_occurrence
                SET lease_expires_at = clock_timestamp()
                        + (%s * INTERVAL '1 second'),
                    updated_at = clock_timestamp()
                WHERE occurrence_id = %s
                  AND claim_generation = %s
                  AND lease_token = %s
                  AND lease_owner = %s
                  AND state IN ('claimed', 'running')
                  AND lease_expires_at > clock_timestamp()
                RETURNING lease_expires_at
                """,
                (
                    lease_seconds,
                    str(claim.occurrence_id),
                    claim.claim_generation,
                    str(claim.lease_token),
                    claim.lease_owner,
                ),
            )
            row = cursor.fetchone()
            return _utc(row["lease_expires_at"]) if row else None

    def _current_claim_row(
        self,
        cursor: Any,
        claim: OccurrenceClaim,
        *,
        states: tuple[str, ...] = ("claimed", "running"),
    ) -> Dict[str, Any]:
        cursor.execute(
            """
            SELECT *, clock_timestamp() AS database_now
            FROM scheduled_occurrence
            WHERE occurrence_id = %s
            FOR UPDATE
            """,
            (str(claim.occurrence_id),),
        )
        row = cursor.fetchone()
        row_data = dict(row) if row is not None else None
        terminal_code = (
            str(row_data.get("result_code"))
            if row_data is not None
            and row_data.get("state") == "cancelled"
            and row_data.get("result_code")
            else None
        )
        if (
            row is None
            or not self._claim_matches(row_data or {}, claim)
            or row["state"] not in states
            or row["lease_expires_at"] is None
            or _utc(row["lease_expires_at"]) <= _utc(row["database_now"])
        ):
            raise StaleOccurrenceClaimError(
                "stale_occurrence_claim", terminal_code=terminal_code
            )
        return row_data or {}

    @staticmethod
    def _lock_claim_job(cursor: Any, claim: OccurrenceClaim) -> None:
        """Serialize attempt allocation with pause/delete definition changes."""

        cursor.execute(
            """
            SELECT status FROM scheduled_job
            WHERE id = %s AND user_id = %s
            FOR UPDATE
            """,
            (str(claim.job["id"]), str(claim.job["user_id"])),
        )
        row = cursor.fetchone()
        status = str(row["status"]) if row is not None else "missing"
        terminal_code = {
            "paused": "cancelled_job_paused",
            "disabled": "cancelled_job_deleted",
        }.get(status)
        if row is None or status not in {"active", "completed"}:
            raise StaleOccurrenceClaimError(
                "stale_occurrence_claim", terminal_code=terminal_code
            )

    def allocate_attempt(self, claim: OccurrenceClaim) -> ScheduledAttempt:
        """Create/resolve and attach one attempt-scoped scheduled operation."""

        coordinator = self._require_coordinator()
        with self._transaction() as cursor:
            self._lock_claim_job(cursor, claim)
            self._current_claim_row(cursor, claim, states=("claimed",))

        attempt_key = f"{claim.occurrence_id}:{claim.attempt_number}"
        normalized_identity = "|".join(
            (
                attempt_key,
                str(claim.job["id"]),
                claim.scheduled_for.isoformat(),
            )
        )
        request = OperationRequest(
            operation_kind="scheduled_occurrence",
            admission_class=AdmissionClass.SCHEDULED,
            owner=self._owner(claim),
            submission_id=uuid.uuid5(
                uuid.NAMESPACE_URL, f"astraldeep:scheduled:{attempt_key}"
            ),
            idempotency_namespace="scheduled_occurrence_attempt",
            idempotency_key=attempt_key,
            normalized_input_digest=hashlib.sha256(
                normalized_identity.encode("utf-8")
            ).hexdigest(),
            chat_id=str(claim.job.get("target_chat_id") or claim.job["id"]),
            parent_operation_id=claim.parent_operation_id,
            connection_generation=None,
            request_generation=uuid.uuid4(),
        )
        admitted = coordinator.submit(request)
        if not admitted.accepted:
            self.mark_claim_retryable(
                claim,
                error_code=admitted.code,
                retry_after_seconds=max(1, (admitted.retry_after_ms or 1_000) // 1_000),
            )
            raise ScheduledAdmissionRefusedError(admitted)

        try:
            with self._transaction() as cursor:
                self._lock_claim_job(cursor, claim)
                self._current_claim_row(cursor, claim, states=("claimed",))
                cursor.execute(
                    """
                    UPDATE scheduled_occurrence
                    SET current_operation_id = %s, updated_at = clock_timestamp()
                    WHERE occurrence_id = %s
                      AND claim_generation = %s
                      AND lease_token = %s
                      AND (current_operation_id IS NULL
                           OR current_operation_id = %s)
                    RETURNING occurrence_id
                    """,
                    (
                        str(admitted.operation_id),
                        str(claim.occurrence_id),
                        claim.claim_generation,
                        str(claim.lease_token),
                        str(admitted.operation_id),
                    ),
                )
                if cursor.fetchone() is None:
                    raise StaleOccurrenceClaimError("stale_occurrence_claim")
        except StaleOccurrenceClaimError as exc:
            self._settle_unstarted_operation(
                claim,
                admitted.operation_id,
                admitted.state,
                terminal_code=exc.terminal_code,
            )
            raise

        projection = coordinator.query_operation(
            owner=self._owner(claim), operation_id=admitted.operation_id
        )
        attempt = ScheduledAttempt(
            claim=claim,
            operation_id=admitted.operation_id,
            operation_state=admitted.state,
            execution_fence=None,
            parent_operation_id=claim.parent_operation_id,
            request_generation=projection.request_generation,
        )
        selected = self.claim_attempt_execution(attempt)
        return selected or attempt

    def _settle_unstarted_operation(
        self,
        claim: OccurrenceClaim,
        operation_id: uuid.UUID,
        state: OperationState,
        *,
        terminal_code: str | None = None,
    ) -> None:
        coordinator = self._require_coordinator()
        if state in {OperationState.QUEUED, OperationState.RUNNING}:
            if terminal_code in {
                "cancelled_job_paused",
                "cancelled_job_deleted",
            }:
                coordinator.cancel(
                    owner=self._owner(claim),
                    operation_id=operation_id,
                    terminal_code=terminal_code,
                )
                return
            coordinator.terminalize_unselected(
                operation_id,
                terminal_code="claim_lost",
                safe_summary="Scheduled claim lost before start",
                retry_after_ms=0,
            )

    def claim_attempt_execution(
        self, attempt: ScheduledAttempt
    ) -> ScheduledAttempt | None:
        """Select the exact queued attempt only while its claim is current."""

        if attempt.execution_fence is not None:
            return attempt
        coordinator = self._require_coordinator()
        try:
            with self._transaction() as cursor:
                self._lock_claim_job(cursor, attempt.claim)
                self._current_claim_row(cursor, attempt.claim, states=("claimed",))
        except StaleOccurrenceClaimError as exc:
            self._settle_unstarted_operation(
                attempt.claim,
                attempt.operation_id,
                attempt.operation_state,
                terminal_code=exc.terminal_code,
            )
            return None
        selected = coordinator.claim_operation(
            AdmissionClass.SCHEDULED, attempt.operation_id
        )
        if selected is None:
            return None
        try:
            with self._transaction() as cursor:
                self._lock_claim_job(cursor, attempt.claim)
                self._current_claim_row(cursor, attempt.claim, states=("claimed",))
        except StaleOccurrenceClaimError as exc:
            try:
                coordinator.terminalize(
                    selected.fence,
                    state=(
                        OperationState.CANCELLED
                        if exc.terminal_code
                        else OperationState.RETRYABLE
                    ),
                    terminal_code=exc.terminal_code or "claim_lost",
                    safe_summary=(
                        "Scheduled job cancelled before start"
                        if exc.terminal_code
                        else "Scheduled claim lost before start"
                    ),
                    retry_after_ms=None if exc.terminal_code else 0,
                )
            except StaleExecutionFenceError:
                pass
            return None
        return replace(
            attempt,
            operation_state=selected.operation.state,
            execution_fence=selected.fence,
        )

    def start_attempt(
        self, attempt: ScheduledAttempt, *, lease_seconds: int = 15
    ) -> ScheduledAttempt:
        """Fenced claimed→running transition and unique ``job_run`` insert."""

        self._validate_claim_settings(
            attempt.claim.lease_owner, limit=1, lease_seconds=lease_seconds
        )
        if attempt.execution_fence is None:
            raise StaleOccurrenceClaimError("attempt has no selected execution")
        coordinator = self._require_coordinator()
        run_id = uuid.uuid4()
        correlation_id = uuid.uuid4()
        with coordinator.fenced_transaction(attempt.execution_fence) as cursor:
            self._current_claim_row(cursor, attempt.claim, states=("claimed",))
            cursor.execute(
                """
                UPDATE scheduled_occurrence
                SET state = 'running',
                    started_at = COALESCE(started_at, clock_timestamp()),
                    operation_execution_generation = %s,
                    lease_expires_at = clock_timestamp()
                        + (%s * INTERVAL '1 second'),
                    updated_at = clock_timestamp()
                WHERE occurrence_id = %s
                  AND claim_generation = %s
                  AND lease_token = %s
                  AND current_operation_id = %s
                  AND state = 'claimed'
                RETURNING occurrence_id
                """,
                (
                    attempt.execution_fence.execution_generation,
                    lease_seconds,
                    str(attempt.claim.occurrence_id),
                    attempt.claim.claim_generation,
                    str(attempt.claim.lease_token),
                    str(attempt.operation_id),
                ),
            )
            if cursor.fetchone() is None:
                raise StaleOccurrenceClaimError("stale_occurrence_claim")
            cursor.execute(
                """
                INSERT INTO job_run (
                    id, job_id, user_id, started_at, outcome, correlation_id,
                    occurrence_id, attempt_number, operation_id,
                    operation_execution_generation,
                    occurrence_claim_generation
                ) VALUES (
                    %s, %s, %s,
                    (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::BIGINT,
                    'running', %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (occurrence_id, attempt_number)
                    WHERE occurrence_id IS NOT NULL
                    DO NOTHING
                RETURNING id
                """,
                (
                    str(run_id),
                    str(attempt.claim.job["id"]),
                    str(attempt.claim.job["user_id"]),
                    str(correlation_id),
                    str(attempt.claim.occurrence_id),
                    attempt.claim.attempt_number,
                    str(attempt.operation_id),
                    attempt.execution_fence.execution_generation,
                    attempt.claim.claim_generation,
                ),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                cursor.execute(
                    """
                    SELECT id, operation_id, operation_execution_generation,
                           occurrence_claim_generation
                    FROM job_run
                    WHERE occurrence_id = %s AND attempt_number = %s
                    """,
                    (
                        str(attempt.claim.occurrence_id),
                        attempt.claim.attempt_number,
                    ),
                )
                existing = cursor.fetchone()
                if (
                    existing is None
                    or _as_uuid(existing["operation_id"]) != attempt.operation_id
                    or int(existing["operation_execution_generation"])
                    != attempt.execution_fence.execution_generation
                    or int(existing["occurrence_claim_generation"])
                    != attempt.claim.claim_generation
                ):
                    raise StaleOccurrenceClaimError("job_run fence conflict")
                run_id = _as_uuid(existing["id"]) or run_id
            else:
                run_id = _as_uuid(inserted["id"]) or run_id
        return replace(
            attempt,
            operation_state=OperationState.RUNNING,
            run_id=run_id,
        )

    def mark_claim_retryable(
        self,
        claim: OccurrenceClaim,
        *,
        error_code: str,
        retry_after_seconds: int = 1,
    ) -> None:
        """Release a current claim for a later attempt without an effect."""

        if not _SAFE_NAME_RE.fullmatch(error_code):
            raise ValueError("error_code must be bounded snake_case")
        if retry_after_seconds < 0 or retry_after_seconds > 86_400:
            raise ValueError("retry_after_seconds is out of range")
        with self._transaction() as cursor:
            current = self._current_claim_row(
                cursor, claim, states=("claimed", "running")
            )
            if str(current["state"]) == "running":
                operation_id = _as_uuid(current.get("current_operation_id"))
                execution_generation = int(
                    current.get("operation_execution_generation") or 0
                )
                if operation_id is None or execution_generation <= 0:
                    raise RuntimeError(
                        "running occurrence has no exact operation identity"
                    )
                cursor.execute(
                    """
                    UPDATE job_run
                    SET outcome = 'interrupted',
                        ended_at = (EXTRACT(EPOCH FROM clock_timestamp())
                                    * 1000)::BIGINT
                    WHERE occurrence_id = %s
                      AND attempt_number = %s
                      AND operation_id = %s
                      AND operation_execution_generation = %s
                      AND occurrence_claim_generation = %s
                      AND outcome = 'running'
                    RETURNING id
                    """,
                    (
                        str(claim.occurrence_id),
                        claim.attempt_number,
                        str(operation_id),
                        execution_generation,
                        claim.claim_generation,
                    ),
                )
                if cursor.fetchone() is None:
                    raise RuntimeError(
                        "running occurrence has no current job_run"
                    )
            cursor.execute(
                """
                UPDATE scheduled_occurrence
                SET state = 'retryable', lease_token = NULL,
                    lease_owner = NULL, lease_expires_at = NULL,
                    next_attempt_at = clock_timestamp()
                        + (%s * INTERVAL '1 second'),
                    last_error_code = %s, updated_at = clock_timestamp()
                WHERE occurrence_id = %s
                  AND claim_generation = %s AND lease_token = %s
                """,
                (
                    retry_after_seconds,
                    error_code,
                    str(claim.occurrence_id),
                    claim.claim_generation,
                    str(claim.lease_token),
                ),
            )

    @staticmethod
    def _validate_effect_identity(
        *, effect_kind: str, effect_key: str, payload_digest: str
    ) -> None:
        if not _SAFE_NAME_RE.fullmatch(effect_kind):
            raise ValueError("effect_kind must be bounded snake_case")
        if not (1 <= len(effect_key) <= 256):
            raise ValueError("effect_key must be 1..256 characters")
        if not _SHA256_RE.fullmatch(payload_digest):
            raise ValueError("payload_digest must be lowercase SHA-256")

    def _assert_effect_authority(
        self, cursor: Any, attempt: ScheduledAttempt
    ) -> Dict[str, Any]:
        if attempt.execution_fence is None or attempt.run_id is None:
            raise StaleOccurrenceClaimError("attempt has not started")
        row = self._current_claim_row(cursor, attempt.claim, states=("running",))
        if (
            _as_uuid(row.get("current_operation_id")) != attempt.operation_id
            or int(row.get("operation_execution_generation") or 0)
            != attempt.execution_fence.execution_generation
        ):
            raise StaleOccurrenceClaimError("stale_occurrence_claim")
        return row

    def reserve_effect(
        self,
        attempt: ScheduledAttempt,
        *,
        effect_kind: str,
        effect_key: str,
        payload_digest: str,
    ) -> EffectReservation:
        """Reserve or reconcile one stable AstralDeep-controlled effect."""

        self._validate_effect_identity(
            effect_kind=effect_kind,
            effect_key=effect_key,
            payload_digest=payload_digest,
        )
        if attempt.execution_fence is None:
            raise StaleOccurrenceClaimError("attempt has no execution fence")
        coordinator = self._require_coordinator()
        with coordinator.fenced_transaction(attempt.execution_fence) as cursor:
            self._assert_effect_authority(cursor, attempt)
            cursor.execute(
                """
                SELECT * FROM effect_ledger
                WHERE occurrence_id = %s AND effect_kind = %s AND effect_key = %s
                FOR UPDATE
                """,
                (str(attempt.claim.occurrence_id), effect_kind, effect_key),
            )
            existing = cursor.fetchone()
            if existing is None:
                cursor.execute(
                    """
                    INSERT INTO effect_ledger (
                        occurrence_id, effect_kind, effect_key, payload_digest,
                        state, operation_id, operation_execution_generation,
                        occurrence_claim_generation, reserved_at
                    ) VALUES (%s, %s, %s, %s, 'reserved', %s, %s, %s,
                              clock_timestamp())
                    """,
                    (
                        str(attempt.claim.occurrence_id),
                        effect_kind,
                        effect_key,
                        payload_digest,
                        str(attempt.operation_id),
                        attempt.execution_fence.execution_generation,
                        attempt.claim.claim_generation,
                    ),
                )
                return EffectReservation("reserved", True, False)

            if str(existing["payload_digest"]) != payload_digest:
                raise EffectIdempotencyConflictError("effect_idempotency_conflict")
            state = str(existing["state"])
            same_attempt = (
                _as_uuid(existing.get("operation_id")) == attempt.operation_id
                and int(existing["operation_execution_generation"])
                == attempt.execution_fence.execution_generation
                and int(existing["occurrence_claim_generation"])
                == attempt.claim.claim_generation
            )
            if state == "failed":
                cursor.execute(
                    """
                    UPDATE effect_ledger
                    SET state = 'reserved', operation_id = %s,
                        operation_execution_generation = %s,
                        occurrence_claim_generation = %s,
                        reserved_at = clock_timestamp(), published_at = NULL,
                        failed_at = NULL, failure_code = NULL,
                        downstream_receipt_digest = NULL
                    WHERE occurrence_id = %s AND effect_kind = %s
                      AND effect_key = %s
                    """,
                    (
                        str(attempt.operation_id),
                        attempt.execution_fence.execution_generation,
                        attempt.claim.claim_generation,
                        str(attempt.claim.occurrence_id),
                        effect_kind,
                        effect_key,
                    ),
                )
                return EffectReservation("reserved", True, False)
            return EffectReservation(
                state=state,
                created=False,
                ambiguous=(state == "reserved" and not same_attempt),
            )

    def reserve_atomic_chat_effect(
        self,
        attempt: ScheduledAttempt,
        *,
        effect_key: str,
        payload_digest: str,
    ) -> EffectReservation:
        """Reserve a database-only chat effect with crash-safe reassignment.

        A ``reserved`` row from an older attempt is recoverable here because
        scheduled chat messages exist only in memory until the same PostgreSQL
        transaction inserts them and marks this row ``published``.  Therefore
        a committed ``reserved`` state proves that no target message escaped.
        """

        effect_kind = "chat_history"
        self._validate_effect_identity(
            effect_kind=effect_kind,
            effect_key=effect_key,
            payload_digest=payload_digest,
        )
        if attempt.execution_fence is None:
            raise StaleOccurrenceClaimError("attempt has no execution fence")
        coordinator = self._require_coordinator()
        with coordinator.fenced_transaction(attempt.execution_fence) as cursor:
            self._assert_effect_authority(cursor, attempt)
            cursor.execute(
                """
                SELECT * FROM effect_ledger
                WHERE occurrence_id = %s AND effect_kind = %s AND effect_key = %s
                FOR UPDATE
                """,
                (str(attempt.claim.occurrence_id), effect_kind, effect_key),
            )
            existing = cursor.fetchone()
            if existing is None:
                cursor.execute(
                    """
                    INSERT INTO effect_ledger (
                        occurrence_id, effect_kind, effect_key, payload_digest,
                        state, operation_id, operation_execution_generation,
                        occurrence_claim_generation, reserved_at
                    ) VALUES (%s, %s, %s, %s, 'reserved', %s, %s, %s,
                              clock_timestamp())
                    """,
                    (
                        str(attempt.claim.occurrence_id),
                        effect_kind,
                        effect_key,
                        payload_digest,
                        str(attempt.operation_id),
                        attempt.execution_fence.execution_generation,
                        attempt.claim.claim_generation,
                    ),
                )
                return EffectReservation("reserved", True, False)
            if str(existing["payload_digest"]) != payload_digest:
                raise EffectIdempotencyConflictError("effect_idempotency_conflict")
            state = str(existing["state"])
            if state == "published":
                return EffectReservation("published", False, False)
            if state not in {"reserved", "failed"}:
                raise StaleOccurrenceClaimError("unsupported chat effect state")
            cursor.execute(
                """
                UPDATE effect_ledger
                SET state = 'reserved', operation_id = %s,
                    operation_execution_generation = %s,
                    occurrence_claim_generation = %s,
                    reserved_at = clock_timestamp(), published_at = NULL,
                    failed_at = NULL, failure_code = NULL,
                    downstream_receipt_digest = NULL
                WHERE occurrence_id = %s AND effect_kind = %s
                  AND effect_key = %s AND state IN ('reserved', 'failed')
                """,
                (
                    str(attempt.operation_id),
                    attempt.execution_fence.execution_generation,
                    attempt.claim.claim_generation,
                    str(attempt.claim.occurrence_id),
                    effect_kind,
                    effect_key,
                ),
            )
            return EffectReservation("reserved", False, False)

    def _mark_effect_published_cursor(
        self,
        cursor: Any,
        attempt: ScheduledAttempt,
        *,
        effect_kind: str,
        effect_key: str,
        payload_digest: str,
    ) -> None:
        """Transition the exact reservation using an existing transaction."""

        cursor.execute(
            """
            UPDATE effect_ledger
            SET state = 'published', published_at = clock_timestamp(),
                failed_at = NULL, failure_code = NULL
            WHERE occurrence_id = %s AND effect_kind = %s
              AND effect_key = %s AND payload_digest = %s
              AND state = 'reserved' AND operation_id = %s
              AND operation_execution_generation = %s
              AND occurrence_claim_generation = %s
            RETURNING state
            """,
            (
                str(attempt.claim.occurrence_id),
                effect_kind,
                effect_key,
                payload_digest,
                str(attempt.operation_id),
                attempt.execution_fence.execution_generation,
                attempt.claim.claim_generation,
            ),
        )
        if cursor.fetchone() is None:
            raise StaleOccurrenceClaimError(
                "chat effect reservation belongs to another attempt"
            )

    def publish_staged_chat_effect(
        self,
        attempt: ScheduledAttempt,
        batch: ScheduledHistoryBatch,
        *,
        effect_kind: str,
        effect_key: str,
        payload_digest: str,
    ) -> EffectReservation:
        """Atomically publish one conversation revision and its effect row."""

        if effect_kind != "chat_history":
            raise ValueError("staged chat publication requires chat_history")
        self._validate_effect_identity(
            effect_kind=effect_kind,
            effect_key=effect_key,
            payload_digest=payload_digest,
        )
        if batch.chat_id != effect_key:
            raise ValueError("chat effect key must equal the staged chat identity")
        if str(attempt.job["user_id"]) != batch.user_id:
            raise ValueError("staged chat owner differs from the occurrence owner")
        if not batch.messages:
            raise ValueError("scheduled chat produced no history messages")
        if attempt.execution_fence is None:
            raise StaleOccurrenceClaimError("attempt has no execution fence")
        commit_id = _as_uuid(batch.conversation_commit_id)
        request_generation = _as_uuid(batch.request_generation)
        if (
            commit_id is None
            or commit_id.version != 4
            or request_generation is None
            or request_generation.version != 4
            or attempt.request_generation != request_generation
            or isinstance(batch.base_render_revision, bool)
            or not isinstance(batch.base_render_revision, int)
            or isinstance(batch.committed_render_revision, bool)
            or not isinstance(batch.committed_render_revision, int)
            or batch.base_render_revision < 0
            or batch.committed_render_revision != batch.base_render_revision + 1
        ):
            raise ValueError("scheduled conversation commit metadata is invalid")
        validated_layouts = []
        seen_layouts = set()
        for layout in batch.canvas_layouts:
            if not isinstance(layout, dict):
                raise ValueError("scheduled canvas layout is invalid")
            key = layout.get("layout_key")
            position = layout.get("position")
            tree = layout.get("layout")
            if (
                not isinstance(key, str)
                or not key
                or len(key) > 512
                or key in seen_layouts
                or isinstance(position, bool)
                or not isinstance(position, int)
                or position < 0
                or not isinstance(tree, list)
            ):
                raise ValueError("scheduled canvas layout is invalid")
            try:
                encoded_tree = json.dumps(
                    tree,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("scheduled canvas layout is invalid") from exc
            seen_layouts.add(key)
            validated_layouts.append((key, position, encoded_tree))

        coordinator = self._require_coordinator()
        with coordinator.fenced_transaction(attempt.execution_fence) as cursor:
            self._assert_effect_authority(cursor, attempt)
            cursor.execute(
                """
                SELECT * FROM effect_ledger
                WHERE occurrence_id = %s AND effect_kind = %s AND effect_key = %s
                FOR UPDATE
                """,
                (str(attempt.claim.occurrence_id), effect_kind, effect_key),
            )
            existing = cursor.fetchone()
            if existing is None:
                raise StaleOccurrenceClaimError("chat effect was not reserved")
            if str(existing["payload_digest"]) != payload_digest:
                raise EffectIdempotencyConflictError("effect_idempotency_conflict")
            if str(existing["state"]) == "published":
                return EffectReservation("published", False, False)
            if (
                str(existing["state"]) != "reserved"
                or _as_uuid(existing.get("operation_id")) != attempt.operation_id
                or int(existing["operation_execution_generation"])
                != attempt.execution_fence.execution_generation
                or int(existing["occurrence_claim_generation"])
                != attempt.claim.claim_generation
            ):
                raise StaleOccurrenceClaimError(
                    "chat effect reservation belongs to another attempt"
                )

            cursor.execute(
                """
                SELECT * FROM chats WHERE id = %s FOR UPDATE
                """,
                (batch.chat_id,),
            )
            chat = cursor.fetchone()
            if chat is None and batch.create_chat_if_missing:
                created_at = batch.messages[0].timestamp_ms
                cursor.execute(
                    """
                    INSERT INTO chats (
                        id, user_id, title, agent_id, created_at, updated_at
                    ) VALUES (%s, %s, 'New Chat', %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        batch.chat_id,
                        batch.user_id,
                        batch.agent_id,
                        created_at,
                        created_at,
                    ),
                )
                cursor.execute(
                    "SELECT * FROM chats WHERE id = %s FOR UPDATE",
                    (batch.chat_id,),
                )
                chat = cursor.fetchone()
            if chat is None or str(chat["user_id"]) != batch.user_id:
                raise StaleOccurrenceClaimError(
                    "scheduled target chat is missing or owner-mismatched"
                )

            cursor.execute(
                "SELECT * FROM conversation_commit WHERE commit_id = %s FOR UPDATE",
                (str(commit_id),),
            )
            conversation = cursor.fetchone()
            if (
                conversation is None
                or str(conversation["chat_id"]) != batch.chat_id
                or str(conversation["owner_user_id"]) != batch.user_id
                or str(conversation["request_generation"]) != str(request_generation)
                or str(conversation["state"]) != "staged"
                or int(conversation["base_render_revision"])
                != batch.base_render_revision
                or _as_uuid(conversation.get("operation_id")) != attempt.operation_id
                or int(conversation["operation_execution_generation"])
                != attempt.execution_fence.execution_generation
                or int(chat.get("render_revision") or 0)
                != batch.base_render_revision
            ):
                raise StaleOccurrenceClaimError(
                    "scheduled conversation commit fence changed"
                )

            cursor.execute(
                "SELECT COUNT(*) AS count, "
                "COUNT(*) FILTER (WHERE committed_render_revision = %s) AS valid "
                "FROM saved_components WHERE conversation_commit_id = %s",
                (batch.committed_render_revision, str(commit_id)),
            )
            component_counts = cursor.fetchone()
            if int(component_counts["count"]) != int(component_counts["valid"]):
                raise StaleOccurrenceClaimError(
                    "scheduled canvas stage is incomplete"
                )
            staged_component_count = int(component_counts["count"])

            cursor.execute(
                "SELECT COUNT(*) AS count FROM messages "
                "WHERE chat_id = %s AND user_id = %s",
                (batch.chat_id, batch.user_id),
            )
            existing_message_count = int(cursor.fetchone()["count"])
            for position, message in enumerate(batch.messages):
                cursor.execute(
                    """
                    INSERT INTO messages (
                        chat_id, user_id, role, content, timestamp,
                        conversation_commit_id, commit_position,
                        committed_render_revision
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        batch.chat_id,
                        batch.user_id,
                        message.role,
                        message.content,
                        message.timestamp_ms,
                        str(commit_id),
                        position,
                        batch.committed_render_revision,
                    ),
                )

            cursor.execute(
                "DELETE FROM saved_components "
                "WHERE chat_id = %s AND user_id = %s "
                "AND conversation_commit_id IS DISTINCT FROM %s",
                (batch.chat_id, batch.user_id, str(commit_id)),
            )
            cursor.execute(
                "DELETE FROM workspace_layout WHERE chat_id = %s AND user_id = %s",
                (batch.chat_id, batch.user_id),
            )
            for layout_key, position, encoded_tree in validated_layouts:
                now_ms = batch.messages[-1].timestamp_ms
                cursor.execute(
                    """
                    INSERT INTO workspace_layout (
                        chat_id, user_id, layout_key, position, layout,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        batch.chat_id,
                        batch.user_id,
                        layout_key,
                        position,
                        encoded_tree,
                        now_ms,
                        now_ms,
                    ),
                )

            title = batch.requested_title
            if title is None and existing_message_count == 0:
                first_user_message = next(
                    (
                        message.title_source
                        for message in batch.messages
                        if message.role == "user"
                    ),
                    None,
                )
                if first_user_message is not None:
                    title = (
                        first_user_message[:30] + "..."
                        if len(first_user_message) > 30
                        else first_user_message
                    )
            cursor.execute("SELECT clock_timestamp() AS current_time")
            committed_at = cursor.fetchone()["current_time"]
            cursor.execute(
                """
                UPDATE conversation_commit
                SET state = 'committed', committed_render_revision = %s,
                    committed_at = %s
                WHERE commit_id = %s AND state = 'staged'
                  AND base_render_revision = %s
                RETURNING commit_id
                """,
                (
                    batch.committed_render_revision,
                    committed_at,
                    str(commit_id),
                    batch.base_render_revision,
                ),
            )
            if cursor.fetchone() is None:
                raise StaleOccurrenceClaimError(
                    "scheduled conversation commit lost its publication CAS"
                )
            cursor.execute(
                """
                UPDATE chats
                SET title = COALESCE(%s, title), updated_at = %s,
                    render_revision = %s, snapshot_committed_at = %s,
                    conversation_commit_id = %s, has_saved_components = %s
                WHERE id = %s AND user_id = %s AND render_revision = %s
                """,
                (
                    title,
                    batch.messages[-1].timestamp_ms,
                    batch.committed_render_revision,
                    committed_at,
                    str(commit_id),
                    bool(staged_component_count),
                    batch.chat_id,
                    batch.user_id,
                    batch.base_render_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise StaleOccurrenceClaimError(
                    "scheduled conversation revision CAS is stale"
                )
            self._mark_effect_published_cursor(
                cursor,
                attempt,
                effect_kind=effect_kind,
                effect_key=effect_key,
                payload_digest=payload_digest,
            )
            return EffectReservation("published", False, False)

    def publish_effect(
        self,
        attempt: ScheduledAttempt,
        *,
        effect_kind: str,
        effect_key: str,
        payload_digest: str,
        downstream_receipt_digest: str | None = None,
    ) -> EffectReservation:
        """Publish a reservation only under the exact creating fences."""

        self._validate_effect_identity(
            effect_kind=effect_kind,
            effect_key=effect_key,
            payload_digest=payload_digest,
        )
        if downstream_receipt_digest is not None and not _SHA256_RE.fullmatch(
            downstream_receipt_digest
        ):
            raise ValueError("downstream_receipt_digest must be lowercase SHA-256")
        if attempt.execution_fence is None:
            raise StaleOccurrenceClaimError("attempt has no execution fence")
        coordinator = self._require_coordinator()
        with coordinator.fenced_transaction(attempt.execution_fence) as cursor:
            self._assert_effect_authority(cursor, attempt)
            cursor.execute(
                """
                SELECT * FROM effect_ledger
                WHERE occurrence_id = %s AND effect_kind = %s AND effect_key = %s
                FOR UPDATE
                """,
                (str(attempt.claim.occurrence_id), effect_kind, effect_key),
            )
            existing = cursor.fetchone()
            if existing is None:
                raise StaleOccurrenceClaimError("effect was not reserved")
            if str(existing["payload_digest"]) != payload_digest:
                raise EffectIdempotencyConflictError("effect_idempotency_conflict")
            if str(existing["state"]) == "published":
                return EffectReservation("published", False, False)
            if (
                str(existing["state"]) != "reserved"
                or _as_uuid(existing.get("operation_id")) != attempt.operation_id
                or int(existing["operation_execution_generation"])
                != attempt.execution_fence.execution_generation
                or int(existing["occurrence_claim_generation"])
                != attempt.claim.claim_generation
            ):
                raise StaleOccurrenceClaimError(
                    "effect reservation belongs to another attempt"
                )
            cursor.execute(
                """
                UPDATE effect_ledger
                SET state = 'published', published_at = clock_timestamp(),
                    failed_at = NULL, failure_code = NULL,
                    downstream_receipt_digest = %s
                WHERE occurrence_id = %s AND effect_kind = %s
                  AND effect_key = %s AND state = 'reserved'
                """,
                (
                    downstream_receipt_digest,
                    str(attempt.claim.occurrence_id),
                    effect_kind,
                    effect_key,
                ),
            )
            return EffectReservation("published", False, False)

    def fail_effect(
        self,
        attempt: ScheduledAttempt,
        *,
        effect_kind: str,
        effect_key: str,
        payload_digest: str,
        failure_code: str,
    ) -> EffectReservation:
        """Mark a reservation failed only when no visible effect occurred."""

        self._validate_effect_identity(
            effect_kind=effect_kind,
            effect_key=effect_key,
            payload_digest=payload_digest,
        )
        if not _SAFE_NAME_RE.fullmatch(failure_code):
            raise ValueError("failure_code must be bounded snake_case")
        if attempt.execution_fence is None:
            raise StaleOccurrenceClaimError("attempt has no execution fence")
        coordinator = self._require_coordinator()
        with coordinator.fenced_transaction(attempt.execution_fence) as cursor:
            self._assert_effect_authority(cursor, attempt)
            cursor.execute(
                """
                UPDATE effect_ledger
                SET state = 'failed', failed_at = clock_timestamp(),
                    published_at = NULL, failure_code = %s
                WHERE occurrence_id = %s AND effect_kind = %s
                  AND effect_key = %s AND payload_digest = %s
                  AND state = 'reserved' AND operation_id = %s
                  AND operation_execution_generation = %s
                  AND occurrence_claim_generation = %s
                RETURNING state
                """,
                (
                    failure_code,
                    str(attempt.claim.occurrence_id),
                    effect_kind,
                    effect_key,
                    payload_digest,
                    str(attempt.operation_id),
                    attempt.execution_fence.execution_generation,
                    attempt.claim.claim_generation,
                ),
            )
            if cursor.fetchone() is None:
                raise StaleOccurrenceClaimError("stale_occurrence_claim")
            return EffectReservation("failed", False, False)

    def finish_attempt(
        self,
        attempt: ScheduledAttempt,
        *,
        outcome: str,
        summary: str | None = None,
        auth_ref: str | None = None,
        retryable: bool = False,
        result_code: str | None = None,
        retry_after_seconds: int = 1,
    ) -> Dict[str, Any]:
        """Commit one fenced job-run and occurrence terminal/retry state."""

        if attempt.execution_fence is None or attempt.run_id is None:
            raise StaleOccurrenceClaimError("attempt has not started")
        if outcome not in {"success", "failure", "interrupted", "skipped_auth"}:
            raise ValueError("unsupported job_run outcome")
        if summary is not None and len(summary) > 2_000:
            summary = summary[:2_000]
        if result_code is not None and not _SAFE_NAME_RE.fullmatch(result_code):
            raise ValueError("result_code must be bounded snake_case")
        if retry_after_seconds < 0 or retry_after_seconds > 86_400:
            raise ValueError("retry_after_seconds is out of range")

        if retryable:
            occurrence_state = "retryable"
            job_outcome = "failure" if outcome == "success" else outcome
            safe_code = result_code or "operation_failed"
        elif outcome == "success":
            occurrence_state = "completed"
            job_outcome = "success"
            safe_code = result_code or "success"
        else:
            occurrence_state = "failed"
            job_outcome = outcome
            safe_code = result_code or (
                "authorization_unavailable"
                if outcome == "skipped_auth"
                else "operation_failed"
            )

        coordinator = self._require_coordinator()
        with coordinator.fenced_transaction(attempt.execution_fence) as cursor:
            self._assert_effect_authority(cursor, attempt)
            cursor.execute(
                """
                UPDATE job_run
                SET ended_at = (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::BIGINT,
                    outcome = %s, summary = %s, auth_ref = %s
                WHERE id = %s AND occurrence_id = %s AND attempt_number = %s
                  AND operation_id = %s
                  AND operation_execution_generation = %s
                  AND occurrence_claim_generation = %s
                  AND outcome = 'running'
                RETURNING id
                """,
                (
                    job_outcome,
                    summary,
                    auth_ref,
                    str(attempt.run_id),
                    str(attempt.claim.occurrence_id),
                    attempt.claim.attempt_number,
                    str(attempt.operation_id),
                    attempt.execution_fence.execution_generation,
                    attempt.claim.claim_generation,
                ),
            )
            if cursor.fetchone() is None:
                raise StaleOccurrenceClaimError("job_run is no longer running")
            terminal = occurrence_state in {"completed", "failed"}
            cursor.execute(
                """
                UPDATE scheduled_occurrence
                SET state = %s, lease_token = NULL, lease_owner = NULL,
                    lease_expires_at = NULL,
                    terminal_at = CASE WHEN %s THEN clock_timestamp() ELSE NULL END,
                    next_attempt_at = CASE WHEN %s THEN
                        clock_timestamp() + (%s * INTERVAL '1 second')
                        ELSE NULL END,
                    result_code = CASE WHEN %s THEN %s ELSE NULL END,
                    last_error_code = CASE WHEN %s THEN %s ELSE NULL END,
                    updated_at = clock_timestamp()
                WHERE occurrence_id = %s AND claim_generation = %s
                  AND lease_token = %s AND current_operation_id = %s
                  AND operation_execution_generation = %s
                  AND state = 'running'
                RETURNING *
                """,
                (
                    occurrence_state,
                    terminal,
                    retryable,
                    retry_after_seconds,
                    occurrence_state == "completed",
                    safe_code,
                    occurrence_state != "completed",
                    safe_code,
                    str(attempt.claim.occurrence_id),
                    attempt.claim.claim_generation,
                    str(attempt.claim.lease_token),
                    str(attempt.operation_id),
                    attempt.execution_fence.execution_generation,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise StaleOccurrenceClaimError("stale_occurrence_claim")
            return dict(row)

    # ── Runs ─────────────────────────────────────────────────────────────

    def start_run(self, job_id: str, user_id: str, correlation_id: str) -> str:
        run_id = str(uuid.uuid4())
        self.db.execute(
            """INSERT INTO job_run (id, job_id, user_id, started_at, outcome, correlation_id)
               VALUES (?, ?, ?, ?, 'running', ?)""",
            (run_id, job_id, user_id, _now_ms(), correlation_id),
        )
        return run_id

    def finish_run(
        self,
        run_id: str,
        *,
        outcome: str,
        summary: Optional[str] = None,
        auth_ref: Optional[str] = None,
    ) -> None:
        self.db.execute(
            "UPDATE job_run SET ended_at = ?, outcome = ?, summary = ?, auth_ref = ? WHERE id = ?",
            (_now_ms(), outcome, summary, auth_ref, run_id),
        )

    def list_runs(
        self, user_id: str, job_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
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
