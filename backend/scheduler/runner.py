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

import logging
import uuid
from typing import Any, Dict, List, Optional

from .cron import compute_next_run_ms

logger = logging.getLogger("scheduler.runner")

VALID_SCOPES = ["tools:read", "tools:write", "tools:search", "tools:system"]


def _intersect_scopes(consented: List[str], current_enabled: Dict[str, bool]) -> List[str]:
    """Authority can never exceed the user's CURRENT scopes (SC-008)."""
    return [s for s in consented if s in VALID_SCOPES and current_enabled.get(s, False)]


class JobRunner:
    def __init__(self, orchestrator, store, offline_grants) -> None:
        self.orch = orchestrator
        self.store = store
        self.grants = offline_grants

    async def _notify(self, user_id: str, *, level: str, title: str, body: str,
                      job_id: Optional[str], chat_id: Optional[str]) -> None:
        """Best-effort in-app notification (FR-022). No external channel exists."""
        try:
            await self.orch.notify_user(user_id, {
                "type": "notification", "level": level, "source": "schedule",
                "job_id": job_id, "chat_id": chat_id, "title": title, "body": body,
            })
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
                self.store.finish_run(run_id, outcome="skipped", summary="dreaming disabled")
                self.store.set_status(user_id, job_id, "paused")
                return "skipped"
            sweep = run_sweep(repo, get_phi_gate(), user_id, trigger="scheduled")
            summary = (f"Consolidated {sweep.get('promoted_count', 0)} of "
                       f"{sweep.get('candidates_considered', 0)} signals.")
        except Exception as exc:
            logger.exception("dreaming sweep failed", extra={"job_id": job_id})
            outcome = "failure"
            summary = f"error: {exc}"

        self.store.finish_run(run_id, outcome=outcome, summary=summary, auth_ref=correlation_id)

        import time
        now_ms = int(time.time() * 1000)
        next_run = compute_next_run_ms(job["schedule_kind"], job["schedule_expr"],
                                       job.get("timezone", "UTC"), now_ms)
        completed = next_run is None
        self.store.update_after_run(job_id, last_run_at=now_ms, next_run_at=next_run,
                                    completed=completed)
        return outcome

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

        # 1+2. Authorization: must have a valid grant; mint a fresh token.
        grant_id = job.get("offline_grant_id")
        if not grant_id or not self.grants.is_valid(grant_id):
            self.store.finish_run(run_id, outcome="skipped_auth",
                                  summary="authorization revoked/expired")
            self.store.set_status(user_id, job_id, "paused")
            await self._notify(user_id, level="warning",
                                title=f"Scheduled job paused: {job['name']}",
                                body="Its authorization expired or was revoked. Re-confirm to resume.",
                                job_id=job_id, chat_id=job.get("target_chat_id"))
            return "skipped_auth"

        try:
            access_token = await self.grants.mint_access_token(grant_id)
        except Exception as exc:
            logger.warning("scheduler.mint_failed", extra={"job_id": job_id, "error": str(exc)})
            self.store.finish_run(run_id, outcome="skipped_auth", summary=str(exc))
            self.store.set_status(user_id, job_id, "paused")
            await self._notify(user_id, level="warning",
                                title=f"Scheduled job paused: {job['name']}",
                                body="Could not refresh its authorization. Re-confirm to resume.",
                                job_id=job_id, chat_id=job.get("target_chat_id"))
            return "skipped_auth"

        # 3. Scope intersection against the user's CURRENT scopes.
        agent_id = job.get("agent_id")
        current = {}
        if agent_id:
            try:
                current = self.orch.tool_permissions.get_agent_scopes(user_id, agent_id)
            except Exception:
                current = {}
        allowed_scopes = _intersect_scopes(list(job.get("consented_scopes") or []), current) if agent_id else []

        # 4. Execute as a background chat turn (in-app delivery via VirtualWebSocket).
        outcome = "success"
        summary = None
        llm_unavailable = False
        try:
            # SEAM (verify against orchestrator internals during T057/staging):
            # run the instruction through the normal chat path under the minted
            # delegated token + allowed_scopes, capturing output to chat history.
            summary = await self.orch.run_scheduled_turn(
                user_id=user_id,
                chat_id=job.get("target_chat_id"),
                instruction=job["instruction"],
                agent_id=agent_id,
                access_token=access_token,
                allowed_scopes=allowed_scopes,
                correlation_id=correlation_id,
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
                logger.warning("scheduled job skipped: system_llm_unconfigured",
                               extra={"job_id": job_id})
                outcome = "failure"
                summary = "llm_unavailable: no system AI credential configured"
            else:
                logger.exception("scheduled job execution failed", extra={"job_id": job_id})
                outcome = "failure"
                summary = f"error: {exc}"

        self.store.finish_run(run_id, outcome=outcome, summary=summary, auth_ref=correlation_id)

        # 5. Reschedule (or complete one-shot) and notify.
        import time
        now_ms = int(time.time() * 1000)
        next_run = compute_next_run_ms(job["schedule_kind"], job["schedule_expr"],
                                       job.get("timezone", "UTC"), now_ms)
        completed = job["schedule_kind"] == "one_shot" or next_run is None
        self.store.update_after_run(job_id, last_run_at=now_ms, next_run_at=next_run, completed=completed)

        # 030 FR-017: structured observability for scheduled runs.
        logger.info("scheduler.run_finished",
                    extra={"job_id": job_id, "user_id": user_id, "outcome": outcome,
                           "correlation_id": correlation_id, "next_run_at": next_run})

        if outcome == "success":
            await self._notify(user_id, level="success",
                                title=f"{job['name']} is ready",
                                body=(summary or "Your scheduled task finished.")[:200],
                                job_id=job_id, chat_id=job.get("target_chat_id"))
        elif llm_unavailable:
            # Feature 054 (US4-AS1): the owner is told the AI was unavailable
            # — the run must never read as "finished".
            await self._notify(user_id, level="error",
                                title=f"Scheduled job failed: {job['name']}",
                                body=("The AI was unavailable — the task did not run. "
                                      "An admin needs to configure the System LLM "
                                      "in settings."),
                                job_id=job_id, chat_id=job.get("target_chat_id"))
        return outcome
