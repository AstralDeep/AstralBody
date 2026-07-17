"""Executes a due scheduled job under fresh, scope-bounded authority (feature 025, US5).

⚠️ Touches the security-critical offline-grant path — covered by the T057 review.

Per run (FR-021/FR-024/SC-008):
  1. start a ``job_run`` (correlation id for audit grouping),
  2. validate + mint a fresh access token from the offline grant; on any
     revocation/expiry/refresh failure → record ``skipped_auth``, pause the job,
     notify in-app, and STOP (never run with stale authority),
  3. intersect the job's consented scopes with the user's CURRENT scopes,
  4. execute the instruction as a normal chat turn via ``BackgroundTaskManager``
     + ``VirtualWebSocket`` so outputs persist to chat history (in-app only),
  5. finish the run, recompute ``next_run_at`` (or complete one-shots), and emit
     an in-app ``notification``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Optional

from orchestrator.work_admission import WorkAdmissionCoordinator
from orchestrator.tool_permissions import VALID_SCOPES

from .cron import compute_next_run_ms
from .store import (
    EffectIdempotencyConflictError,
    ScheduledAttempt,
    StaleOccurrenceClaimError,
)

logger = logging.getLogger("scheduler.runner")

_EFFECT_KIND_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REVIEWED_EFFECT_KINDS = frozenset(
    {
        "audit_record",
        "chat_history",
        "chat_message",
        "downstream_request",
        "history_publish",
        "maintenance_output",
        "notification",
    }
)


class HandlerIdempotencyBoundary(str, Enum):
    """Reviewed durable boundaries eligible for unattended execution."""

    ASTRALDEEP_TRANSACTION = "astraldeep_transaction"
    DOWNSTREAM_IDEMPOTENCY_KEY = "downstream_idempotency_key"


@dataclass(frozen=True)
class ScheduledHandlerDeclaration:
    """Static unattended-handler eligibility declaration."""

    supports_unattended: bool
    idempotency_boundary: HandlerIdempotencyBoundary | None
    effect_kinds: tuple[str, ...]

    def __post_init__(self) -> None:
        boundary = self.idempotency_boundary
        if boundary is not None and not isinstance(
            boundary, HandlerIdempotencyBoundary
        ):
            raise ValueError("idempotency_boundary must be a reviewed boundary")
        if not self.effect_kinds:
            raise ValueError("effect_kinds must contain a reviewed effect_kind")
        if len(set(self.effect_kinds)) != len(self.effect_kinds):
            raise ValueError("duplicate effect_kind is not allowed")
        for effect_kind in self.effect_kinds:
            if (
                not _EFFECT_KIND_RE.fullmatch(effect_kind)
                or effect_kind not in _REVIEWED_EFFECT_KINDS
            ):
                raise ValueError("effect_kind is not a reviewed safe name")


@dataclass(frozen=True)
class HandlerEligibilityDecision:
    """Non-sensitive schedule-acceptance decision."""

    eligible: bool
    code: str | None
    retryable: bool


def assess_unattended_handler(
    declaration: ScheduledHandlerDeclaration | None,
) -> HandlerEligibilityDecision:
    """Fail closed unless the handler declares a reviewed effect boundary."""

    if (
        declaration is None
        or not declaration.supports_unattended
        or declaration.idempotency_boundary is None
    ):
        return HandlerEligibilityDecision(False, "handler_not_idempotent", False)
    return HandlerEligibilityDecision(True, None, False)


@dataclass(frozen=True)
class OccurrenceRunResult:
    """Safe result consumed by the fenced scheduler loop."""

    outcome: str
    summary: str | None
    auth_ref: str | None
    retryable: bool
    result_code: str | None
    retry_after_seconds: int = 1


_DEFAULT_HANDLER_DECLARATIONS = MappingProxyType(
    {
        "scheduled_chat": ScheduledHandlerDeclaration(
            supports_unattended=True,
            idempotency_boundary=HandlerIdempotencyBoundary.ASTRALDEEP_TRANSACTION,
            effect_kinds=("chat_history", "notification", "audit_record"),
        ),
        "dreaming": ScheduledHandlerDeclaration(
            supports_unattended=True,
            idempotency_boundary=HandlerIdempotencyBoundary.ASTRALDEEP_TRANSACTION,
            effect_kinds=("maintenance_output", "audit_record"),
        ),
    }
)
_UNREVIEWED_MUTATING_SCOPES = frozenset({"tools:write", "tools:execute"})

# ``VALID_SCOPES`` is the canonical scope vocabulary (six entries since 027/039
# added tools:files and tools:execute), imported from tool_permissions so a
# scheduled job never silently loses a scope the user actually granted. The
# stale four-entry copy that used to live here dropped tools:files/tools:execute,
# pausing legitimate jobs with a false "permissions no longer enabled" notice
# and 400-ing the REST create path.

#: Honest, actionable copy per authority-skip reason (056 FR-013).
_SKIP_SUMMARY = {
    "missing_consent": "no durable authorization on record",
    "revoked_or_expired": "authorization revoked or expired",
    "mint_failed": "could not refresh authorization",
    "empty_scopes": "consented scopes no longer granted",
}
_SKIP_BODY = {
    "missing_consent": (
        "It has no durable authorization to run while you are "
        "signed out. Re-confirm the schedule to grant it."
    ),
    "revoked_or_expired": (
        "Its authorization expired or was revoked. Re-confirm to resume."
    ),
    "mint_failed": "Could not refresh its authorization. Re-confirm to resume.",
    "empty_scopes": (
        "The permissions it was granted are no longer enabled for "
        "that agent. Re-enable them (or re-confirm) to resume."
    ),
}


def _intersect_scopes(
    consented: List[str], current_enabled: Dict[str, bool]
) -> List[str]:
    """Authority can never exceed the user's CURRENT scopes (SC-008)."""
    return [s for s in consented if s in VALID_SCOPES and current_enabled.get(s, False)]


class JobRunner:
    def __init__(
        self,
        orchestrator,
        store,
        offline_grants,
        *,
        handler_declarations: Dict[str, ScheduledHandlerDeclaration] | None = None,
    ) -> None:
        self.orch = orchestrator
        self.store = store
        self.grants = offline_grants
        self._coordinator: WorkAdmissionCoordinator | None = None
        self._handler_declarations = dict(
            _DEFAULT_HANDLER_DECLARATIONS
            if handler_declarations is None
            else handler_declarations
        )
        # 056 FR-013 (notification fatigue): job ids already notified about an
        # authority skip. Pausing the job is the structural collapse (a paused
        # job is not "due" again), but this makes the one-notification-per-
        # paused-job rule hold even if a job re-fires while still un-consented.
        # Cleared when the job next runs successfully.
        self._skip_notified: set = set()

    def bind_execution_context(
        self,
        *,
        coordinator: WorkAdmissionCoordinator,
        store,
    ) -> None:
        """Bind the same coordinator/store used by the durable scheduler loop."""

        if self._coordinator is not None and self._coordinator is not coordinator:
            raise RuntimeError("cannot replace the scheduler operation coordinator")
        if store is not self.store:
            raise RuntimeError("scheduler runner/store binding mismatch")
        self._coordinator = coordinator

    def assess_job(self, job: Dict[str, Any]) -> HandlerEligibilityDecision:
        """Resolve one job's static declaration before materialization."""

        handler_kind = job.get("handler_kind")
        if handler_kind is None:
            handler_kind = (
                "dreaming"
                if job.get("agent_id") == "__dreaming__"
                else "scheduled_chat"
            )
        declaration = self._handler_declarations.get(str(handler_kind))
        decision = assess_unattended_handler(declaration)
        if not decision.eligible:
            return decision
        consented_scopes = {
            str(scope) for scope in (job.get("consented_scopes") or [])
        }
        if (
            str(handler_kind) == "scheduled_chat"
            and consented_scopes.intersection(_UNREVIEWED_MUTATING_SCOPES)
        ):
            return HandlerEligibilityDecision(
                False,
                "handler_downstream_idempotency_unreviewed",
                False,
            )
        return decision

    @staticmethod
    def _job_type(job: Dict[str, Any]) -> str:
        return (
            "dreaming"
            if job.get("agent_id") == "__dreaming__"
            else "scheduled_chat"
        )

    def _observe_scheduler(
        self,
        event: str,
        job: Dict[str, Any],
        *,
        result_code: str | None = None,
    ) -> None:
        """Record one bounded scheduler event without affecting execution."""

        observability = getattr(self.orch, "runtime_observability", None)
        if observability is None:
            return
        try:
            observability.record_scheduler(
                event,
                job_type=self._job_type(job),
                result_code=result_code,
            )
        except Exception:
            logger.debug("scheduler observability rejected an event", exc_info=True)

    def _observe_effect(
        self,
        event: str,
        *,
        effect_kind: str,
        result_code: str | None = None,
    ) -> None:
        """Record one bounded effect event without exposing an effect key."""

        observability = getattr(self.orch, "runtime_observability", None)
        if observability is None:
            return
        try:
            observability.record_effect(
                event,
                effect_kind=effect_kind,
                result_code=result_code,
            )
        except Exception:
            logger.debug("scheduler effect observability rejected an event", exc_info=True)

    async def _notify(
        self,
        user_id: str,
        *,
        level: str,
        title: str,
        body: str,
        job_id: Optional[str],
        chat_id: Optional[str],
    ) -> None:
        """Best-effort in-app notification (FR-022). No external channel exists."""
        try:
            await self.orch.notify_user(
                user_id,
                {
                    "type": "notification",
                    "level": level,
                    "source": "schedule",
                    "job_id": job_id,
                    "chat_id": chat_id,
                    "title": title,
                    "body": body,
                },
            )
        except Exception:  # pragma: no cover - notification is best-effort
            logger.debug("scheduler notify failed (non-fatal)", exc_info=True)

    async def _run_dreaming(self, job: Dict[str, Any], correlation_id: str) -> str:
        """Run a per-user dreaming consolidation sweep (025 T053). No grant needed."""
        user_id = job["user_id"]
        job_id = job["id"]
        run_id = self.store.start_run(job_id, user_id, correlation_id)
        outcome = "success"
        summary = None
        try:
            from personalization.phi_gate import get_phi_gate

            from dreaming.consolidation import run_sweep

            repo = self.orch.personalization_service.repo
            # Defense in depth: honor a since-flipped dreaming_enabled flag.
            profile = repo.get_profile(user_id) or {}
            if not bool(profile.get("dreaming_enabled", True)):
                self.store.finish_run(
                    run_id, outcome="skipped", summary="dreaming disabled"
                )
                self.store.set_status(user_id, job_id, "paused")
                return "skipped"
            sweep = run_sweep(repo, get_phi_gate(), user_id, trigger="scheduled")
            summary = (
                f"Consolidated {sweep.get('promoted_count', 0)} of "
                f"{sweep.get('candidates_considered', 0)} signals."
            )
        except Exception as exc:
            logger.exception("dreaming sweep failed", extra={"job_id": job_id})
            outcome = "failure"
            summary = f"error: {exc}"

        self.store.finish_run(
            run_id, outcome=outcome, summary=summary, auth_ref=correlation_id
        )

        import time

        now_ms = int(time.time() * 1000)
        next_run = compute_next_run_ms(
            job["schedule_kind"],
            job["schedule_expr"],
            job.get("timezone", "UTC"),
            now_ms,
        )
        completed = next_run is None
        self.store.update_after_run(
            job_id, last_run_at=now_ms, next_run_at=next_run, completed=completed
        )
        return outcome

    @staticmethod
    def _effect_digest(*, job: Dict[str, Any], effect_kind: str) -> str:
        """Hash normalized effect identity without persisting instruction data."""

        instruction_digest = hashlib.sha256(
            str(job.get("instruction") or "").encode("utf-8")
        ).hexdigest()
        normalized = json.dumps(
            {
                "effect_kind": effect_kind,
                "job_id": str(job["id"]),
                "target_chat_id": job.get("target_chat_id"),
                "instruction_sha256": instruction_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    async def _notify_occurrence(
        self,
        attempt: ScheduledAttempt,
        *,
        level: str,
        title: str,
        body: str,
    ) -> None:
        """Deliver one deduplicated transient notification for an occurrence."""

        digest = hashlib.sha256(
            json.dumps(
                {"level": level, "title": title, "body": body},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        reservation = await asyncio.to_thread(
            self.store.reserve_effect,
            attempt,
            effect_kind="notification",
            effect_key="completion",
            payload_digest=digest,
        )
        self._observe_effect(
            "reserved" if reservation.state == "reserved" else "deduplicated",
            effect_kind="notification",
        )
        if reservation.state == "published" or reservation.ambiguous:
            return
        await self._notify(
            str(attempt.job["user_id"]),
            level=level,
            title=title,
            body=body,
            job_id=str(attempt.job["id"]),
            chat_id=attempt.job.get("target_chat_id"),
        )
        await asyncio.to_thread(
            self.store.publish_effect,
            attempt,
            effect_kind="notification",
            effect_key="completion",
            payload_digest=digest,
        )
        self._observe_effect("published", effect_kind="notification")

    async def _run_dreaming_occurrence(
        self, attempt: ScheduledAttempt
    ) -> OccurrenceRunResult:
        job = attempt.job
        digest = self._effect_digest(job=job, effect_kind="maintenance_output")
        reservation = await asyncio.to_thread(
            self.store.reserve_effect,
            attempt,
            effect_kind="maintenance_output",
            effect_key="consolidation",
            payload_digest=digest,
        )
        self._observe_effect(
            "reserved" if reservation.state == "reserved" else "deduplicated",
            effect_kind="maintenance_output",
        )
        if reservation.state == "published":
            self._observe_scheduler(
                "terminal", job, result_code="success"
            )
            return OccurrenceRunResult(
                "success",
                "Dreaming output already published",
                str(attempt.operation_id),
                False,
                "success",
            )
        if reservation.ambiguous:
            self._observe_scheduler(
                "terminal", job, result_code="effect_outcome_ambiguous"
            )
            return OccurrenceRunResult(
                "failure",
                "Prior dreaming effect outcome is ambiguous; it was not repeated",
                str(attempt.operation_id),
                False,
                "effect_outcome_ambiguous",
            )
        try:
            from personalization.phi_gate import get_phi_gate

            from dreaming.consolidation import run_sweep

            repo = self.orch.personalization_service.repo
            profile = repo.get_profile(str(job["user_id"])) or {}
            if not bool(profile.get("dreaming_enabled", True)):
                await asyncio.to_thread(
                    self.store.fail_effect,
                    attempt,
                    effect_kind="maintenance_output",
                    effect_key="consolidation",
                    payload_digest=digest,
                    failure_code="dreaming_disabled",
                )
                self._observe_effect(
                    "failed",
                    effect_kind="maintenance_output",
                    result_code="dreaming_disabled",
                )
                self.store.set_status(str(job["user_id"]), str(job["id"]), "paused")
                self._observe_scheduler(
                    "terminal", job, result_code="dreaming_disabled"
                )
                return OccurrenceRunResult(
                    "failure",
                    "Dreaming is disabled",
                    str(attempt.operation_id),
                    False,
                    "dreaming_disabled",
                )
            sweep = await asyncio.to_thread(
                run_sweep,
                repo,
                get_phi_gate(),
                str(job["user_id"]),
                trigger="scheduled",
            )
            summary = (
                f"Consolidated {sweep.get('promoted_count', 0)} of "
                f"{sweep.get('candidates_considered', 0)} signals."
            )
        except Exception:
            logger.exception("dreaming sweep failed", extra={"job_id": str(job["id"])})
            # The output boundary may have partially committed.  Keep the
            # reservation ambiguous so recovery never blindly repeats it.
            self._observe_scheduler(
                "terminal", job, result_code="operation_failed"
            )
            return OccurrenceRunResult(
                "failure",
                "Dreaming sweep failed",
                str(attempt.operation_id),
                False,
                "operation_failed",
            )
        await asyncio.to_thread(
            self.store.publish_effect,
            attempt,
            effect_kind="maintenance_output",
            effect_key="consolidation",
            payload_digest=digest,
        )
        self._observe_effect("published", effect_kind="maintenance_output")
        self._observe_scheduler("terminal", job, result_code="success")
        return OccurrenceRunResult(
            "success", summary, str(attempt.operation_id), False, "success"
        )

    async def run_occurrence(
        self,
        attempt: ScheduledAttempt,
        *,
        claim_lost: asyncio.Event,
    ) -> OccurrenceRunResult:
        """Execute one started occurrence without ever re-emitting ambiguity."""

        decision = self.assess_job(attempt.job)
        if not decision.eligible:
            self._observe_scheduler(
                "terminal",
                attempt.job,
                result_code=decision.code or "handler_not_idempotent",
            )
            return OccurrenceRunResult(
                "failure",
                "Scheduled handler does not provide an idempotency boundary",
                str(attempt.operation_id),
                False,
                decision.code,
            )
        if claim_lost.is_set():
            self._observe_scheduler(
                "claim_lost", attempt.job, result_code="claim_lost"
            )
            raise StaleOccurrenceClaimError("stale_occurrence_claim")
        if attempt.claim.attempt_number > 1:
            self._observe_scheduler(
                "claim_recovered", attempt.job, result_code="claim_recovered"
            )
        if attempt.job.get("agent_id") == "__dreaming__":
            return await self._run_dreaming_occurrence(attempt)

        job = attempt.job
        user_id = str(job["user_id"])
        job_id = str(job["id"])
        from orchestrator.chain_authority import AuthoritySkip, MachineTurnAuthority

        authority = await MachineTurnAuthority(self.orch, self.grants).derive(
            user_id=user_id,
            agent_id=job.get("agent_id"),
            consented_scopes=list(job.get("consented_scopes") or []),
            grant_id=job.get("offline_grant_id"),
            turn_class="scheduled_job",
        )
        if isinstance(authority, AuthoritySkip):
            already_notified = job_id in self._skip_notified
            self.store.set_status(user_id, job_id, "paused")
            if not already_notified:
                self._skip_notified.add(job_id)
                await self._notify_occurrence(
                    attempt,
                    level="warning",
                    title=f"Scheduled job paused: {job['name']}",
                    body=_SKIP_BODY.get(
                        authority.reason,
                        "Its authorization is no longer valid. Re-confirm to resume.",
                    ),
                )
            self._observe_scheduler(
                "terminal", job, result_code="authorization_unavailable"
            )
            return OccurrenceRunResult(
                "skipped_auth",
                _SKIP_SUMMARY.get(authority.reason, authority.reason),
                str(attempt.operation_id),
                False,
                "authorization_unavailable",
            )

        # A job without an explicitly selected chat owns a stable UUID4 chat
        # equal to its already-UUID4 job identity. This keeps fallback chats
        # compatible with the canonical conversation locator/snapshot wire.
        effect_key = str(job.get("target_chat_id") or job["id"])
        digest = self._effect_digest(job=job, effect_kind="chat_history")
        try:
            reservation = await asyncio.to_thread(
                self.store.reserve_atomic_chat_effect,
                attempt,
                effect_key=effect_key,
                payload_digest=digest,
            )
        except EffectIdempotencyConflictError:
            self._observe_effect(
                "conflict",
                effect_kind="chat_history",
                result_code="effect_idempotency_conflict",
            )
            self._observe_scheduler(
                "terminal", job, result_code="effect_idempotency_conflict"
            )
            raise
        self._observe_effect(
            "reserved" if reservation.state == "reserved" else "deduplicated",
            effect_kind="chat_history",
        )
        if reservation.state == "published":
            self._observe_scheduler(
                "terminal", job, result_code="success"
            )
            return OccurrenceRunResult(
                "success",
                "Scheduled output was already published",
                str(attempt.operation_id),
                False,
                "success",
            )
        if reservation.ambiguous:
            self._observe_effect(
                "deduplicated",
                effect_kind="chat_history",
                result_code="effect_outcome_ambiguous",
            )
            self._observe_scheduler(
                "terminal", job, result_code="effect_outcome_ambiguous"
            )
            return OccurrenceRunResult(
                "failure",
                "A prior output may already be visible; the handler was not repeated",
                str(attempt.operation_id),
                False,
                "effect_outcome_ambiguous",
            )
        try:
            summary = await self.orch.run_scheduled_turn(
                user_id=user_id,
                chat_id=job.get("target_chat_id"),
                instruction=str(job["instruction"]),
                agent_id=job.get("agent_id"),
                access_token=authority.access_token,
                allowed_scopes=authority.allowed_scopes,
                correlation_id=str(attempt.claim.occurrence_id),
                authority=authority,
                scheduled_attempt=attempt,
                scheduled_store=self.store,
                effect_kind="chat_history",
                effect_key=effect_key,
                payload_digest=digest,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            try:
                from llm_config import LLMUnavailable

                llm_unavailable = isinstance(exc, LLMUnavailable)
            except Exception:  # pragma: no cover - defensive import guard
                llm_unavailable = False
            logger.exception("scheduled job execution failed", extra={"job_id": job_id})
            result_code = "llm_unavailable" if llm_unavailable else "operation_failed"
            self._observe_scheduler("terminal", job, result_code=result_code)
            return OccurrenceRunResult(
                "failure",
                "System AI was unavailable"
                if llm_unavailable
                else "Scheduled turn failed",
                str(attempt.operation_id),
                True,
                result_code,
            )

        if claim_lost.is_set():
            self._observe_scheduler(
                "claim_lost", job, result_code="claim_lost"
            )
            raise StaleOccurrenceClaimError("stale_occurrence_claim")
        self._observe_effect("published", effect_kind="chat_history")
        self._skip_notified.discard(job_id)
        await self._notify_occurrence(
            attempt,
            level="success",
            title=f"{job['name']} is ready",
            body=(summary or "Your scheduled task finished.")[:200],
        )
        self._observe_scheduler("terminal", job, result_code="success")
        return OccurrenceRunResult(
            "success", summary, str(attempt.operation_id), False, "success"
        )

    async def run_job(self, job: Dict[str, Any]) -> str:
        """Execute one due job. Returns the run outcome."""
        user_id = job["user_id"]
        job_id = job["id"]
        correlation_id = str(uuid.uuid4())

        # 030 (025 T053): dreaming/consolidation jobs run a local sweep — no
        # offline grant or delegated authority needed (in-DB, non-PHI, no
        # external calls). Routed before the grant gate below.
        if job.get("agent_id") == "__dreaming__":
            return await self._run_dreaming(job, correlation_id)

        run_id = self.store.start_run(job_id, user_id, correlation_id)

        # 1-3. Authority (056 US2, FR-012/FR-013): ONE shared derivation seam —
        # validate the durable consent (revocation re-checked HERE, not only at
        # expiry), mint a fresh token for THIS run, and narrow to
        # (consented ∩ the user's CURRENT grants). Any failure is fail-closed:
        # zero real-agent dispatch, a recorded skipped_auth outcome, the job
        # paused, and ONE actionable notification (collapsed — a paused job
        # does not re-notify on every firing).
        agent_id = job.get("agent_id")
        from orchestrator.chain_authority import AuthoritySkip, MachineTurnAuthority

        authority = await MachineTurnAuthority(self.orch, self.grants).derive(
            user_id=user_id,
            agent_id=agent_id,
            consented_scopes=list(job.get("consented_scopes") or []),
            grant_id=job.get("offline_grant_id"),
            turn_class="scheduled_job",
        )
        if isinstance(authority, AuthoritySkip):
            already_notified = job_id in self._skip_notified
            self.store.finish_run(
                run_id,
                outcome="skipped_auth",
                summary=_SKIP_SUMMARY.get(authority.reason, authority.reason),
            )
            self.store.set_status(user_id, job_id, "paused")
            logger.warning(
                "scheduler.authority_skip",
                extra={
                    "job_id": job_id,
                    "user_id": user_id,
                    "reason": authority.reason,
                    "notified": not already_notified,
                },
            )
            if not already_notified:
                self._skip_notified.add(job_id)
                # Notification fatigue (spec edge case): notify on the
                # TRANSITION into paused, not once per scheduled firing.
                await self._notify(
                    user_id,
                    level="warning",
                    title=f"Scheduled job paused: {job['name']}",
                    body=_SKIP_BODY.get(
                        authority.reason,
                        "Its authorization is no longer valid. Re-confirm to resume.",
                    ),
                    job_id=job_id,
                    chat_id=job.get("target_chat_id"),
                )
            return "skipped_auth"

        access_token = authority.access_token
        allowed_scopes = authority.allowed_scopes

        # 4. Execute as a background chat turn (in-app delivery via VirtualWebSocket).
        outcome = "success"
        summary = None
        llm_unavailable = False
        try:
            # 056 US2: the derived root is threaded INTO the turn (it used to be
            # dropped here), so real-agent tools dispatch delegated under the
            # user's consent in production, and any hop the turn starts mints
            # children off that root.
            summary = await self.orch.run_scheduled_turn(
                user_id=user_id,
                chat_id=job.get("target_chat_id"),
                instruction=job["instruction"],
                agent_id=agent_id,
                access_token=access_token,
                allowed_scopes=allowed_scopes,
                correlation_id=correlation_id,
                authority=authority,
            )
        except Exception as exc:
            # Feature 054 (FR-020): a run whose AI was unavailable is a
            # FAILURE, reported honestly — never the old silent "success".
            try:
                from llm_config import LLMUnavailable

                llm_unavailable = isinstance(exc, LLMUnavailable)
            except Exception:  # pragma: no cover - defensive import guard
                llm_unavailable = False
            if llm_unavailable:
                logger.warning(
                    "scheduled job skipped: system_llm_unconfigured",
                    extra={"job_id": job_id},
                )
                outcome = "failure"
                summary = "llm_unavailable: no system AI credential configured"
            else:
                logger.exception(
                    "scheduled job execution failed", extra={"job_id": job_id}
                )
                outcome = "failure"
                summary = f"error: {exc}"

        self.store.finish_run(
            run_id, outcome=outcome, summary=summary, auth_ref=correlation_id
        )

        # 5. Reschedule (or complete one-shot) and notify.
        import time

        now_ms = int(time.time() * 1000)
        next_run = compute_next_run_ms(
            job["schedule_kind"],
            job["schedule_expr"],
            job.get("timezone", "UTC"),
            now_ms,
        )
        completed = job["schedule_kind"] == "one_shot" or next_run is None
        self.store.update_after_run(
            job_id, last_run_at=now_ms, next_run_at=next_run, completed=completed
        )

        # 030 FR-017: structured observability for scheduled runs.
        logger.info(
            "scheduler.run_finished",
            extra={
                "job_id": job_id,
                "user_id": user_id,
                "outcome": outcome,
                "correlation_id": correlation_id,
                "next_run_at": next_run,
            },
        )

        if outcome == "success":
            # A healthy run re-arms the skip notification for this job.
            self._skip_notified.discard(job_id)
            await self._notify(
                user_id,
                level="success",
                title=f"{job['name']} is ready",
                body=(summary or "Your scheduled task finished.")[:200],
                job_id=job_id,
                chat_id=job.get("target_chat_id"),
            )
        elif llm_unavailable:
            # Feature 054 (US4-AS1): the owner is told the AI was unavailable
            # — the run must never read as "finished".
            await self._notify(
                user_id,
                level="error",
                title=f"Scheduled job failed: {job['name']}",
                body=(
                    "The AI was unavailable — the task did not run. "
                    "An admin needs to configure the System LLM "
                    "in settings."
                ),
                job_id=job_id,
                chat_id=job.get("target_chat_id"),
            )
        return outcome
