"""Feature 030 — scheduling recurring work from chat.

The 030 walkthrough found that asking for recurring work ("Every Monday,
compile new publications into a digest") was flatly DENIED by the chat LLM
("I cannot schedule recurring background tasks") even though feature-025
scheduled jobs exist — they were only reachable through Settings →
Personalization → Schedule, invisible from the conversation.

This module makes scheduling reachable from chat with the same consent
posture as the REST API (``scheduler/api.py`` hard-requires explicit
consent): the LLM calls the ``schedule_recurring_task`` meta-tool, the
handler VALIDATES the proposal through the existing governance/cron path and
replies with a consent card — nothing is created until the user clicks
"Create schedule" (the explicit grant), which routes through
``handle_decision`` with the exact scope-bounding rules of the REST flow.

Pattern mirrors feature 027 (``agentic_creation``): a pseudo-agent id keeps
the meta-tool outside every real-agent permission/credential gate, and the
decision card updates over ``send_ui_render(target="chat")``.
"""
import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from astralprims import Alert, Button, Card, Text
from shared.feature_flags import flags

logger = logging.getLogger("Orchestrator.SchedulingChat")

META_AGENT_ID = "__scheduler__"

#: Consent cards die with the proposal cache (in-memory, no schema): after
#: this many seconds an un-actioned proposal is refused and must be re-asked.
PROPOSAL_TTL_S = 900

_VALID_KINDS = ("one_shot", "interval", "cron")

SYSTEM_PROMPT_ADDENDUM = """
RECURRING / SCHEDULED WORK (schedule_recurring_task):
- This system DOES support scheduled and recurring background jobs. NEVER tell the user you
  cannot schedule recurring tasks.
- When the user asks for work on a schedule ("every Monday...", "daily digest", "remind me in
  2 hours", "compile X weekly"), call `schedule_recurring_task`. The user confirms via a consent
  card before anything is created — propose, don't ask permission in prose first.
- schedule_kind/schedule_expr: "interval" with "<N><unit>" (s/m/h/d, e.g. "1d", "12h");
  "cron" with a 5-field cron expression (e.g. "0 9 * * 1" = Mondays 09:00); "one_shot" with an
  ISO-8601 datetime.
- Put WHAT the job should do each run in `instruction`, phrased as a standalone request.
"""


def meta_tool_definitions() -> List[Dict[str, Any]]:
    """OpenAI-style tool definition for the scheduling meta-tool."""
    return [
        {
            "type": "function",
            "function": {
                "name": "schedule_recurring_task",
                "description": (
                    "Propose a scheduled (recurring or one-shot) background job. The user "
                    "sees a consent card with the cadence and instruction and must approve "
                    "before the job is created. Use for any 'every day/week/Monday...', "
                    "'remind me', or 'compile X on a schedule' request."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Short human name for the job"},
                        "instruction": {"type": "string", "description": "What to do on each run, phrased as a standalone request"},
                        "schedule_kind": {"type": "string", "enum": list(_VALID_KINDS)},
                        "schedule_expr": {"type": "string", "description": "interval: '<N><unit>' (s/m/h/d); cron: 5-field expression; one_shot: ISO-8601 datetime"},
                        "timezone": {"type": "string", "description": "IANA timezone, default UTC"},
                        "agent_id": {"type": "string", "description": "Optional agent whose tools the job may use (must already be enabled for the user)"},
                    },
                    "required": ["name", "instruction", "schedule_kind", "schedule_expr"],
                },
            },
        },
    ]


def should_inject(draft_agent_id: Optional[str]) -> bool:
    """Offered on normal chat turns only — same exclusions as feature 027."""
    return flags.is_enabled("scheduling_chat") and not draft_agent_id


async def _audit(user_id: str, action_type: str, description: str,
                 correlation_id: str, outcome: str = "success",
                 chat_id: Optional[str] = None,
                 inputs_meta: Optional[Dict] = None) -> None:
    """Record a ``schedule`` audit event (best-effort, never raises)."""
    try:
        from datetime import datetime, timezone

        from audit.recorder import get_recorder
        from audit.schemas import AuditEventCreate
        rec = get_recorder()
        if rec is None:
            return
        await rec.record(AuditEventCreate(
            actor_user_id=user_id or "unknown",
            auth_principal=user_id or "unknown",
            event_class="schedule",
            action_type=action_type,
            description=description[:1024],
            conversation_id=chat_id,
            correlation_id=correlation_id,
            outcome=outcome,
            inputs_meta=inputs_meta or {},
            started_at=datetime.now(timezone.utc),
        ))
    except Exception:
        logger.debug("scheduling_chat: audit record failed (%s)", action_type, exc_info=True)


def _proposals(orch) -> Dict[str, Dict[str, Any]]:
    """Lazy per-process proposal cache: proposal_id -> validated args."""
    if not hasattr(orch, "_schedule_proposals"):
        orch._schedule_proposals = {}
    return orch._schedule_proposals


def human_cadence(schedule_kind: str, schedule_expr: str, tz: str) -> str:
    """Plain-language cadence line for the consent card."""
    if schedule_kind == "interval":
        return f"every {schedule_expr} ({tz})"
    if schedule_kind == "cron":
        return f"on the cron schedule `{schedule_expr}` ({tz})"
    return f"once, at {schedule_expr} ({tz})"


def _validate_proposal(orch, user_id: str, args: Dict[str, Any]):
    """Server-side validation of the LLM-supplied proposal.

    Returns (cleaned_args, next_run_ms) or raises ValueError with a
    user-readable message. Reuses the EXACT governance/cron validators the
    REST create path uses (``scheduler/api.py``) so chat cannot schedule
    anything the API would refuse.
    """
    from agentic_settings import (SCHEDULE_MAX_ACTIVE_JOBS_PER_USER,
                                  SCHEDULE_MIN_INTERVAL_SECONDS)
    from scheduler.cron import ScheduleError, compute_next_run_ms
    from scheduler.governance import GovernanceError, validate_new_job
    from scheduler.store import ScheduledJobStore

    name = str(args.get("name") or "").strip()[:120]
    instruction = str(args.get("instruction") or "").strip()[:2000]
    schedule_kind = str(args.get("schedule_kind") or "").strip()
    schedule_expr = str(args.get("schedule_expr") or "").strip()[:100]
    tz = str(args.get("timezone") or "UTC").strip()[:64]
    agent_id = (str(args.get("agent_id")).strip() or None) if args.get("agent_id") else None

    if not name or not instruction:
        raise ValueError("A job needs both a name and an instruction.")
    if schedule_kind not in _VALID_KINDS:
        raise ValueError(f"schedule_kind must be one of {_VALID_KINDS}.")
    if not schedule_expr:
        raise ValueError("schedule_expr is required.")
    if agent_id:
        if agent_id not in getattr(orch, "agent_cards", {}) or orch._is_draft_agent(agent_id):
            raise ValueError(f"Unknown agent '{agent_id}' — omit agent_id or use a live agent.")

    store = ScheduledJobStore(orch.history.db)
    try:
        validate_new_job(
            active_job_count=store.count_active(user_id),
            max_active=SCHEDULE_MAX_ACTIVE_JOBS_PER_USER,
            schedule_kind=schedule_kind,
            schedule_expr=schedule_expr,
            min_interval_seconds=SCHEDULE_MIN_INTERVAL_SECONDS,
        )
        next_run = compute_next_run_ms(schedule_kind, schedule_expr, tz,
                                       int(time.time() * 1000))
    except (GovernanceError, ScheduleError) as exc:
        raise ValueError(str(exc)) from exc

    cleaned = {"name": name, "instruction": instruction,
               "schedule_kind": schedule_kind, "schedule_expr": schedule_expr,
               "timezone": tz, "agent_id": agent_id}
    return cleaned, next_run


async def handle_meta_tool(orch, tool_name: str, args: Dict[str, Any], *,
                           user_id: str, chat_id: Optional[str], websocket):
    """Dispatch the scheduling meta-tool: validate, cache a proposal, return
    the consent card. Nothing is persisted until the user approves."""
    from shared.protocol import MCPResponse

    if tool_name != "schedule_recurring_task":
        return MCPResponse(error={"message": f"Unknown scheduling tool '{tool_name}'",
                                  "retryable": False})
    try:
        cleaned, next_run = await asyncio.to_thread(
            _validate_proposal, orch, user_id, args or {})
    except ValueError as exc:
        alert = Alert(message=f"That schedule cannot be created: {exc}",
                      variant="warning").to_dict()
        return MCPResponse(error={"message": str(exc), "retryable": False},
                           ui_components=[alert])

    proposal_id = uuid.uuid4().hex
    _proposals(orch)[proposal_id] = {
        "user_id": user_id, "chat_id": chat_id, "args": cleaned,
        "created_at": time.time(),
    }
    await _audit(user_id, "schedule.proposed",
                 f"Chat proposed scheduled job '{cleaned['name']}'",
                 correlation_id=proposal_id, chat_id=chat_id,
                 inputs_meta={"kind": cleaned["schedule_kind"],
                              "expr": cleaned["schedule_expr"]})
    logger.info("schedule proposal %s user=%s name=%r kind=%s expr=%s",
                proposal_id, user_id, cleaned["name"], cleaned["schedule_kind"],
                cleaned["schedule_expr"])

    agent_line = (f"Uses agent: {cleaned['agent_id']} (with only the permissions "
                  "you currently grant it)." if cleaned["agent_id"]
                  else "Runs without agent tools (plain assistant run).")
    card = Card(title=f"⏰ Schedule proposal: {cleaned['name']}", content=[
        Text(content=cleaned["instruction"]),
        Text(content=(f"Runs {human_cadence(cleaned['schedule_kind'], cleaned['schedule_expr'], cleaned['timezone'])}. "
                      f"{agent_line} Results are delivered in-app to this chat. "
                      "Nothing is scheduled until you approve."),
             variant="caption"),
        Button(label="Create schedule", action="schedule_decision",
               payload={"proposal_id": proposal_id, "decision": "approve"}),
        Button(label="Cancel", action="schedule_decision", variant="secondary",
               payload={"proposal_id": proposal_id, "decision": "discard"}),
    ]).to_dict()
    return MCPResponse(
        result={"status": "proposed", "proposal_id": proposal_id,
                "message": "Consent card shown — the user must approve before the job exists."},
        ui_components=[card],
    )


async def handle_decision(orch, websocket, user_id: str, payload: Dict[str, Any]) -> None:
    """ui_event ``schedule_decision`` — the explicit user grant (or refusal).

    Approval re-derives consented scopes from the user's CURRENT grants for
    the chosen agent (never wider — the REST flow's scope-bounding rule) and
    creates the job with the same store call as ``scheduler/api.py``.
    """
    proposal_id = str(payload.get("proposal_id") or "")
    decision = str(payload.get("decision") or "")
    prop = _proposals(orch).get(proposal_id)

    async def _say(message: str, variant: str = "info"):
        await orch.send_ui_render(websocket, [Alert(message=message, variant=variant).to_dict()],
                                  target="chat")

    if not prop or prop["user_id"] != user_id:
        await _say("This schedule proposal is no longer available — ask again to recreate it.",
                   "warning")
        return
    if time.time() - prop["created_at"] > PROPOSAL_TTL_S:
        _proposals(orch).pop(proposal_id, None)
        await _say("This schedule proposal expired — ask again to recreate it.", "warning")
        return

    if decision != "approve":
        _proposals(orch).pop(proposal_id, None)
        await _audit(user_id, "schedule.discarded",
                     f"User declined scheduled job '{prop['args']['name']}'",
                     correlation_id=proposal_id, chat_id=prop.get("chat_id"))
        await _say("Cancelled — nothing was scheduled.")
        return

    args = prop["args"]
    try:
        # Re-validate at approval time (caps/cadence may have changed since
        # the proposal) and recompute the first run.
        cleaned, next_run = await asyncio.to_thread(_validate_proposal, orch, user_id, args)
    except ValueError as exc:
        _proposals(orch).pop(proposal_id, None)
        await _say(f"That schedule can no longer be created: {exc}", "warning")
        return

    consented: List[str] = []
    if cleaned["agent_id"]:
        current = await asyncio.to_thread(
            orch.tool_permissions.get_agent_scopes, user_id, cleaned["agent_id"])
        consented = sorted(s for s, on in current.items() if on)

    from scheduler.store import ScheduledJobStore
    store = ScheduledJobStore(orch.history.db)
    job = await asyncio.to_thread(
        store.create_job,
        user_id, name=cleaned["name"], instruction=cleaned["instruction"],
        schedule_kind=cleaned["schedule_kind"], schedule_expr=cleaned["schedule_expr"],
        timezone=cleaned["timezone"], consented_scopes=consented,
        agent_id=cleaned["agent_id"], target_chat_id=prop.get("chat_id"),
        next_run_at=next_run,
        offline_grant_id=None,  # granted later via Settings (consent-capture flow)
    )
    _proposals(orch).pop(proposal_id, None)
    await _audit(user_id, "schedule.create",
                 f"Created scheduled job '{cleaned['name']}' from chat consent",
                 correlation_id=proposal_id, chat_id=prop.get("chat_id"),
                 inputs_meta={"job_id": job["id"], "kind": cleaned["schedule_kind"],
                              "consented_scopes": consented})
    logger.info("schedule created from chat: job=%s user=%s name=%r",
                job["id"], user_id, cleaned["name"])

    offline_hint = (" To let it run while you are signed out, grant offline access in "
                    "Settings → Personalization → Schedule." if cleaned["agent_id"] else "")
    await orch.send_ui_render(websocket, [
        Alert(message=(f"Scheduled '{cleaned['name']}' — runs "
                       f"{human_cadence(cleaned['schedule_kind'], cleaned['schedule_expr'], cleaned['timezone'])}."
                       + offline_hint),
              variant="success").to_dict(),
        Button(label="Manage schedules", action="chrome_open",
               payload={"surface": "personalization"}, variant="secondary").to_dict(),
    ], target="chat")
    # Keep any open personalization surfaces in sync is the surface's own
    # concern; the dashboards don't show jobs, so no broadcast needed here.
    await asyncio.sleep(0)
