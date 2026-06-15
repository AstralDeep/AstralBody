"""Feature 027 — agentic agent/tool creation from chat.

Implements the orchestrator meta-tools (``create_capability``,
``extend_agent``) per contracts/agentic-creation.md. When the chat LLM
determines no offered tool can serve the user's request, it calls a
meta-tool; the handler auto-creates a draft through the existing 012
lifecycle, self-tests it, and returns an in-chat card with
approve / refine / discard decisions. Nothing reaches the live fleet
without explicit user approval (spec FR-002); live-agent revisions
re-pass the security gate before a backed-up, rollback-safe swap
(FR-006).

Audit: one correlation_id per capability gap — the draft id (a uuid4)
— pairing ``lifecycle.gap_detected`` with the terminal lifecycle events
(event_class ``agent_lifecycle``).
"""
import asyncio
import hashlib
import json
import logging
import os
import shutil
import time
from typing import Any, Dict, List, Optional

from astralprims import Alert, Button, Card, Text
from shared.feature_flags import flags
from shared.protocol import MCPResponse

logger = logging.getLogger("Orchestrator.AgenticCreation")

META_AGENT_ID = "__orchestrator__"

SELF_TEST_TIMEOUT_S = 120          # A11 bound per attempt
SELF_TEST_MAX_AUTO_REFINES = 1     # A11 bound on auto-refine retries

SYSTEM_PROMPT_ADDENDUM = """
CAPABILITY GAPS (create_capability / extend_agent):
- If NO available tool can serve the user's request, call `create_capability` to build a new
  agent for it (the system generates, security-checks, and self-tests a draft; the user approves
  before anything goes live). Restate the user's request verbatim in `user_request`.
- This INCLUDES requests for a persistent tool the user wants to UPDATE or maintain over time
  (e.g. "build me a budget tracker I can update each month") — a one-off static dashboard or
  sample-data mockup does NOT serve such a request; call `create_capability` instead.
- To ADD a tool to an agent the user already owns, call `extend_agent` instead.
- Do NOT call these when a suitable tool exists but is disabled or permission-restricted (you
  will see a "restricted" tool error if you try it) — in that case tell the user to enable it
  under Settings → Agents & permissions.
- Call `create_capability` at most once per distinct missing capability; if a draft already
  exists for it the system will point at the existing draft.
"""


def meta_tool_definitions() -> List[Dict[str, Any]]:
    """OpenAI-style tool definitions for the orchestrator meta-tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": "create_capability",
                "description": (
                    "Create a new agent with the tools needed to serve the user's request "
                    "when NO available tool can — including requests for a persistent tool "
                    "the user wants to update/maintain over time, which a static dashboard "
                    "cannot serve. A draft is generated, security-checked and "
                    "self-tested; the user approves before it goes live. Do NOT use this for "
                    "capabilities that exist but are disabled/unauthorized."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name": {"type": "string", "description": "Short human name for the new agent"},
                        "description": {"type": "string", "description": "What the agent does, in plain language (at least 10 characters)"},
                        "tools_spec": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                                "required": ["name", "description"],
                            },
                            "description": "1-4 tools the agent needs",
                        },
                        "user_request": {"type": "string", "description": "The user's request, verbatim — used to self-test the new capability"},
                    },
                    "required": ["agent_name", "description", "tools_spec", "user_request"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "extend_agent",
                "description": (
                    "Add or change a tool on a live agent the user OWNS. Prepares a draft "
                    "revision; nothing changes on the live agent until the user approves and "
                    "security checks re-pass."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string", "description": "Live agent id to extend (must be owned by the user)"},
                        "instruction": {"type": "string", "description": "What to add or change, in plain language"},
                        "user_request": {"type": "string", "description": "The user's request, verbatim"},
                    },
                    "required": ["agent_id", "instruction"],
                },
            },
        },
    ]


def should_inject(draft_agent_id: Optional[str]) -> bool:
    """Meta-tools are offered on normal chat turns only (D1).

    Excluded: draft-test sessions (the draft's own tools are under test) and
    turns where the feature flag is off. Text-only turns are excluded at the
    call site (feature 008 semantics preserved).
    """
    return flags.is_enabled("agentic_creation") and not draft_agent_id


def gap_fingerprint(agent_name: str, tools_spec: Optional[List[Dict]] = None,
                    extra: str = "") -> str:
    """Stable fingerprint of a requested capability (FR-007 dedup key)."""
    names = sorted((t.get("name") or "").strip().lower() for t in (tools_spec or []))
    basis = "|".join([(agent_name or "").strip().lower(), *names, (extra or "").strip().lower()])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------

async def _audit(user_id: str, action_type: str, description: str,
                 correlation_id: str, outcome: str = "success",
                 chat_id: Optional[str] = None, agent_id: Optional[str] = None,
                 inputs_meta: Optional[Dict] = None) -> None:
    """Record an ``agent_lifecycle`` audit event (best-effort, never raises)."""
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
            agent_id=agent_id,
            event_class="agent_lifecycle",
            action_type=action_type,
            description=description[:1024],
            conversation_id=chat_id,
            correlation_id=correlation_id,
            outcome=outcome,
            inputs_meta=inputs_meta or {},
            started_at=datetime.now(timezone.utc),
        ))
    except Exception:
        logger.debug("agentic: audit record failed (%s)", action_type, exc_info=True)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _summarize_outputs(outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Distill a VirtualWebSocket capture into a self-test verdict."""
    tools_called: List[str] = []
    error_messages: List[str] = []
    component_count = 0
    text_preview = ""
    for frame in outputs:
        ftype = frame.get("type")
        if ftype == "chat_step":
            step = frame.get("step") or {}
            if step.get("kind") == "tool_call" and step.get("name"):
                if step["name"] not in tools_called:
                    tools_called.append(step["name"])
        elif ftype in ("ui_render", "ui_update"):
            for comp in frame.get("components") or []:
                if not isinstance(comp, dict):
                    continue
                # Fallback tool attribution: tool-produced components carry
                # _source_tool tags even when chat_step frames are absent.
                src_tool = comp.get("_source_tool")
                if src_tool and src_tool not in tools_called:
                    tools_called.append(src_tool)
                if comp.get("type") == "alert" and comp.get("variant") == "error":
                    error_messages.append(str(comp.get("message", ""))[:200])
                else:
                    component_count += 1
                    if not text_preview and comp.get("type") == "card":
                        for child in comp.get("content") or []:
                            if isinstance(child, dict) and child.get("type") == "text":
                                text_preview = str(child.get("content", ""))[:280]
                                break
    passed = component_count > 0 and not error_messages
    summary = (
        f"{len(tools_called)} tool(s) exercised, {component_count} component(s) produced"
        + (f"; errors: {error_messages[0]}" if error_messages else "")
    )
    return {
        "status": "passed" if passed else "failed",
        "summary": summary,
        "tools_called": tools_called,
        "errors": error_messages[:3],
        "evidence": text_preview,
        "tested_at": int(time.time() * 1000),
    }


async def _self_test_draft(orch, draft: Dict[str, Any], user_request: str,
                           user_id: str, attachments=None) -> Dict[str, Any]:
    """Run the user's originating request as a draft-test chat turn.

    Executes on a ``VirtualWebSocket`` (audit-attributable, no real socket)
    in an isolated chat so the user's conversation is not polluted. Bounded
    by ``SELF_TEST_TIMEOUT_S`` (A11).

    Feature 031: ``attachments`` lets an auto-created *parser* draft self-test
    against the exact uploaded file that triggered its creation — the structured
    attachment block is injected so the draft's ``parse_<ext>`` tool runs on the
    real file.
    """
    from orchestrator.async_tasks import BackgroundTask, VirtualWebSocket

    test_chat_id = orch.history.create_chat(user_id=user_id)
    task = BackgroundTask(task_id=f"selftest-{draft['id'][:8]}", chat_id=test_chat_id,
                          user_id=user_id)
    vws = VirtualWebSocket(task)
    try:
        await asyncio.wait_for(
            orch.handle_chat_message(
                vws, user_request, test_chat_id,
                user_id=user_id, draft_agent_id=draft["id"],
                attachments=attachments,
            ),
            timeout=SELF_TEST_TIMEOUT_S,
        )
        return _summarize_outputs(task.outputs)
    except asyncio.TimeoutError:
        return {"status": "timeout", "summary": f"Self-test exceeded {SELF_TEST_TIMEOUT_S}s",
                "tools_called": [], "errors": ["timeout"], "evidence": "",
                "tested_at": int(time.time() * 1000)}
    except Exception as exc:
        logger.exception("agentic: self-test crashed for draft %s", draft["id"])
        return {"status": "failed", "summary": f"Self-test error: {exc}",
                "tools_called": [], "errors": [str(exc)[:200]], "evidence": "",
                "tested_at": int(time.time() * 1000)}


# ---------------------------------------------------------------------------
# In-chat cards
# ---------------------------------------------------------------------------

def _decision_buttons(draft_id: str, revision: bool = False) -> List[Dict[str, Any]]:
    approve_action = "revision_apply" if revision else "draft_approve"
    discard_action = "revision_discard" if revision else "draft_discard"
    approve_label = "Apply to live agent" if revision else "Approve"
    return [
        Button(label=approve_label, action=approve_action, payload={"draft_id": draft_id}).to_dict(),
        Button(label="Refine", action="draft_refine", payload={"draft_id": draft_id}).to_dict(),
        Button(label="Discard", action=discard_action, payload={"draft_id": draft_id}).to_dict(),
    ]


def creation_card(draft: Dict[str, Any], self_test: Dict[str, Any],
                  revision: bool = False, note: str = "") -> Dict[str, Any]:
    """The approve/refine/discard card presented in chat (US1 scenarios 2-3)."""
    status = self_test.get("status", "unknown")
    verdict = {"passed": "✓ Self-test passed", "failed": "✗ Self-test failed",
               "timeout": "✗ Self-test timed out"}.get(status, "Self-test pending")
    lines = [
        Text(content=draft.get("description", ""), variant="caption").to_dict(),
        Text(content=f"**{verdict}** — {self_test.get('summary', '')}", variant="markdown").to_dict(),
    ]
    if self_test.get("evidence"):
        lines.append(Text(content=f"Preview: {self_test['evidence']}", variant="caption").to_dict())
    if note:
        lines.append(Text(content=note, variant="caption").to_dict())
    what = "Draft revision" if revision else "Draft agent"
    return Card(
        # Stable author identity (030): every state of this draft's card
        # carries the same id, so decision outcomes REPLACE the actionable
        # card on the canvas instead of leaving stale Approve/Refine/Discard
        # buttons clickable after a decision was already made.
        id=f"draft-card-{draft['id']}",
        title=f"{what}: {draft.get('agent_name', 'unnamed')}",
        content=lines + _decision_buttons(draft["id"], revision=revision),
    ).to_dict()


def _error_card(message: str) -> Dict[str, Any]:
    return Alert(message=message, variant="error").to_dict()


# ---------------------------------------------------------------------------
# Meta-tool dispatch
# ---------------------------------------------------------------------------

async def handle_meta_tool(orch, tool_name: str, args: Dict[str, Any], *,
                           user_id: str, chat_id: Optional[str],
                           websocket=None) -> MCPResponse:
    """Entry point for ``__orchestrator__`` pseudo-agent tool calls."""
    try:
        if tool_name == "create_capability":
            return await _create_capability(orch, args, user_id=user_id,
                                            chat_id=chat_id, websocket=websocket)
        if tool_name == "extend_agent":
            return await _extend_agent(orch, args, user_id=user_id,
                                       chat_id=chat_id, websocket=websocket)
        return MCPResponse(error={"message": f"Unknown meta-tool: {tool_name}", "retryable": False})
    except Exception as exc:
        logger.exception("agentic: meta-tool %s failed", tool_name)
        card = _error_card(
            "Creating the capability failed unexpectedly. You can retry, rephrase the "
            "request, or create the agent manually under Settings → Agents & permissions."
        )
        return MCPResponse(
            result={"status": "error", "detail": str(exc)[:300]},
            ui_components=[card],
        )


async def _create_capability(orch, args: Dict[str, Any], *, user_id: str,
                             chat_id: Optional[str], websocket=None) -> MCPResponse:
    agent_name = (args.get("agent_name") or "").strip()
    description = (args.get("description") or "").strip()
    tools_spec = args.get("tools_spec") or []
    user_request = (args.get("user_request") or description).strip()
    if not agent_name or len(description) < 10 or not tools_spec:
        return MCPResponse(error={
            "message": "create_capability needs agent_name, a description (≥10 chars) and tools_spec",
            "retryable": False})
    tools_spec = tools_spec[:4]

    fingerprint = gap_fingerprint(agent_name, tools_spec)
    existing = orch.history.db.find_gap_draft(user_id, chat_id or "", fingerprint)
    if existing:
        # FR-007: route repeat requests to the staged draft, never duplicate.
        self_test = json.loads(existing.get("self_test") or "{}")
        card = creation_card(existing, self_test,
                             note="This capability is already staged — decide on the existing draft.")
        return MCPResponse(
            result={"status": "duplicate", "draft_id": existing["id"],
                    "draft_status": existing.get("status")},
            ui_components=[card],
        )

    lifecycle = orch.lifecycle_manager
    draft = await lifecycle.create_draft(
        user_id=user_id, agent_name=agent_name, description=description,
        tools_spec=[{"name": t.get("name", ""), "description": t.get("description", "")}
                    for t in tools_spec],
    )
    draft_id = draft["id"]
    orch.history.db.update_draft_agent(
        draft_id, origin="auto_chat", source_chat_id=chat_id or "",
        gap_fingerprint=fingerprint,
    )
    await _audit(user_id, "lifecycle.gap_detected",
                 f"Capability gap: {agent_name} — auto-creating draft",
                 correlation_id=draft_id, outcome="in_progress", chat_id=chat_id,
                 inputs_meta={"gap_fingerprint": fingerprint, "draft_id": draft_id})

    # Generate + start + self-test (≤1 auto-refine on failure — A11).
    draft = await lifecycle.generate_code(draft_id, websocket=websocket)
    if draft.get("status") in ("error", "rejected"):
        await _audit(user_id, "lifecycle.auto_created", "Generation failed",
                     correlation_id=draft_id, outcome="failure", chat_id=chat_id,
                     agent_id=None, inputs_meta={"draft_id": draft_id})
        card = creation_card(draft, {"status": "failed",
                                     "summary": draft.get("error_message") or "generation failed"},
                             note="Generation failed — Refine to retry with guidance, or Discard.")
        return MCPResponse(result={"status": "generation_failed", "draft_id": draft_id},
                           ui_components=[card])

    draft = await lifecycle.start_draft_agent(draft_id, websocket=websocket)
    self_test = await _self_test_draft(orch, draft, user_request, user_id)

    refines = 0
    while self_test["status"] != "passed" and refines < SELF_TEST_MAX_AUTO_REFINES:
        refines += 1
        failure = "; ".join(self_test.get("errors") or [self_test.get("summary", "failed")])
        logger.info("agentic: self-test failed for %s — auto-refine %d (%s)",
                    draft_id, refines, failure[:120])
        draft = await lifecycle.refine_agent(
            draft_id, f"The self-test failed: {failure}. Fix the tools so this request "
                      f"succeeds: {user_request}", websocket=websocket)
        if draft.get("status") == "error":
            break
        draft = await lifecycle.start_draft_agent(draft_id, websocket=websocket)
        self_test = await _self_test_draft(orch, draft, user_request, user_id)

    self_test["auto_refines"] = refines
    orch.history.db.update_draft_agent(draft_id, self_test=json.dumps(self_test))
    await _audit(user_id, "lifecycle.auto_created",
                 f"Auto-created draft '{agent_name}' ({draft_id})",
                 correlation_id=draft_id, chat_id=chat_id,
                 inputs_meta={"draft_id": draft_id, "gap_fingerprint": fingerprint})
    await _audit(user_id, "lifecycle.self_test",
                 f"Self-test {self_test['status']}: {self_test['summary']}",
                 correlation_id=draft_id,
                 outcome="success" if self_test["status"] == "passed" else "failure",
                 chat_id=chat_id, inputs_meta={"draft_id": draft_id})

    card = creation_card(orch.history.db.get_draft_agent(draft_id) or draft, self_test)
    return MCPResponse(
        result={"status": "created", "draft_id": draft_id,
                "self_test": self_test["status"],
                "next": "user must approve, refine, or discard via the buttons"},
        ui_components=[card],
    )


# ---------------------------------------------------------------------------
# Live-agent revision (extend_agent → staged draft → gated swap)
# ---------------------------------------------------------------------------

def _live_agent_dir_and_draft(orch, agent_id: str):
    """Resolve a live, lifecycle-managed agent's draft row + directory."""
    lifecycle = orch.lifecycle_manager
    row = lifecycle._get_draft_by_agent_id(agent_id)
    if not row or row.get("status") != "live":
        return None, None
    agent_dir = os.path.join(lifecycle._agents_dir, row["agent_slug"])
    return row, agent_dir


async def _extend_agent(orch, args: Dict[str, Any], *, user_id: str,
                        chat_id: Optional[str], websocket=None) -> MCPResponse:
    agent_id = (args.get("agent_id") or "").strip()
    instruction = (args.get("instruction") or "").strip()
    if not agent_id or not instruction:
        return MCPResponse(error={"message": "extend_agent needs agent_id and instruction",
                                  "retryable": False})

    # Ownership gate (FR-010): only the owner may stage a revision.
    db = orch.history.db
    ownership = db.get_agent_ownership(agent_id)
    user = db.get_user(user_id) or {}
    owner_email = user.get("email", user_id)
    if not ownership or ownership.get("owner_email") not in (owner_email, user_id):
        return MCPResponse(
            result={"status": "not_owned", "agent_id": agent_id},
            ui_components=[_error_card(
                f"You don't own '{agent_id}', so it can't be extended. You can create a "
                f"new agent with this capability instead.")],
        )

    live_row, live_dir = _live_agent_dir_and_draft(orch, agent_id)
    if live_row is None or not os.path.isdir(live_dir):
        return MCPResponse(
            result={"status": "not_revisable", "agent_id": agent_id},
            ui_components=[_error_card(
                f"'{agent_id}' is not a lifecycle-managed agent, so it can't be revised "
                f"in place. Ask me to create a new agent with this capability instead.")],
        )

    fingerprint = gap_fingerprint(agent_id, extra=instruction)
    existing = db.find_gap_draft(user_id, chat_id or "", fingerprint)
    if existing:
        self_test = json.loads(existing.get("self_test") or "{}")
        card = creation_card(existing, self_test, revision=True,
                             note="This revision is already staged — decide on it below.")
        return MCPResponse(result={"status": "duplicate", "draft_id": existing["id"]},
                           ui_components=[card])

    lifecycle = orch.lifecycle_manager
    rev = await lifecycle.create_draft(
        user_id=user_id,
        agent_name=f"{live_row['agent_name']} (revision)",
        description=f"Revision of {agent_id}: {instruction}",
    )
    rev_id = rev["id"]
    db.update_draft_agent(rev_id, origin="revision", source_chat_id=chat_id or "",
                          gap_fingerprint=fingerprint, revises_agent_id=agent_id)
    await _audit(user_id, "lifecycle.gap_detected",
                 f"Revision requested for {agent_id}: {instruction[:120]}",
                 correlation_id=rev_id, outcome="in_progress", chat_id=chat_id,
                 agent_id=agent_id, inputs_meta={"draft_id": rev_id, "revises_agent_id": agent_id})

    # Stage: refine a copy of the live agent's tools file via the generator,
    # then gate-check the staged code with the validator harness (its sample
    # executions are the revision's self-test — no clone process needed).
    rev_dir = os.path.join(lifecycle._agents_dir, rev["agent_slug"])
    try:
        live_tools = os.path.join(live_dir, "mcp_tools.py")
        with open(live_tools, "r", encoding="utf-8") as fh:
            current_code = fh.read()
        new_code = await lifecycle.generator.refine_tools_file(
            current_code=current_code, user_message=instruction,
            agent_name=live_row["agent_name"], description=live_row["description"])
        compile(new_code, "mcp_tools.py", "exec")

        os.makedirs(rev_dir, exist_ok=True)
        with open(os.path.join(rev_dir, "mcp_tools.py"), "w", encoding="utf-8") as fh:
            fh.write(new_code)

        report = lifecycle.security.analyze(new_code, filename=f"{rev['agent_slug']}/mcp_tools.py")
        validation = lifecycle.validator.validate(new_code, live_row["agent_slug"],
                                                  lifecycle._agents_dir)
        sec_blocker = getattr(report, "max_severity", None)
        sec_name = getattr(sec_blocker, "name", str(sec_blocker or "")).upper()
        passed = validation.passed and sec_name not in ("CRITICAL", "HIGH")
        self_test = {
            "status": "passed" if passed else "failed",
            "summary": (f"validator: {validation.tools_passed}/{validation.tools_tested} tools passed; "
                        f"security max severity: {sec_name or 'NONE'}"),
            "tools_called": [], "errors": [] if passed else ["gate checks failed"],
            "evidence": "", "tested_at": int(time.time() * 1000),
        }
        db.update_draft_agent(rev_id, status="generated",
                              self_test=json.dumps(self_test),
                              security_report=json.dumps(report.to_dict()),
                              validation_report=json.dumps(validation.to_dict()))
    except Exception as exc:
        logger.exception("agentic: revision staging failed for %s", agent_id)
        db.update_draft_agent(rev_id, status="error", error_message=str(exc)[:500])
        await _audit(user_id, "lifecycle.auto_created", f"Revision staging failed: {exc}",
                     correlation_id=rev_id, outcome="failure", chat_id=chat_id, agent_id=agent_id)
        return MCPResponse(result={"status": "staging_failed", "draft_id": rev_id},
                           ui_components=[_error_card(
                               "Staging the revision failed. Refine with more detail or discard it.")])

    await _audit(user_id, "lifecycle.auto_created",
                 f"Staged revision {rev_id} for {agent_id}",
                 correlation_id=rev_id, chat_id=chat_id, agent_id=agent_id)
    await _audit(user_id, "lifecycle.self_test",
                 f"Revision gate-check {self_test['status']}: {self_test['summary']}",
                 correlation_id=rev_id,
                 outcome="success" if self_test["status"] == "passed" else "failure",
                 chat_id=chat_id, agent_id=agent_id)

    card = creation_card(db.get_draft_agent(rev_id), self_test, revision=True)
    return MCPResponse(
        result={"status": "revision_staged", "draft_id": rev_id,
                "self_test": self_test["status"],
                "next": "user must apply, refine, or discard via the buttons"},
        ui_components=[card],
    )


async def apply_revision(orch, rev: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """Gate + swap a staged revision into its live agent (FR-006).

    The live agent's code changes only inside this function, and every
    failure path restores the backup before restart — a failed gate or
    restart never leaves the live agent modified.
    Returns {applied: bool, detail: str}.
    """
    lifecycle = orch.lifecycle_manager
    db = orch.history.db
    agent_id = rev.get("revises_agent_id") or ""
    live_row, live_dir = _live_agent_dir_and_draft(orch, agent_id)
    if live_row is None:
        return {"applied": False, "detail": f"Live agent {agent_id} not found"}

    rev_dir = os.path.join(lifecycle._agents_dir, rev["agent_slug"])
    staged = os.path.join(rev_dir, "mcp_tools.py")
    if not os.path.exists(staged):
        return {"applied": False, "detail": "Staged revision file missing"}
    with open(staged, "r", encoding="utf-8") as fh:
        new_code = fh.read()

    # Re-run the full gate on the staged code at apply time (it may be stale).
    report = lifecycle.security.analyze(new_code, filename=f"{live_row['agent_slug']}/mcp_tools.py")
    sec_name = getattr(getattr(report, "max_severity", None), "name", "").upper()
    validation = lifecycle.validator.validate(new_code, live_row["agent_slug"], lifecycle._agents_dir)
    if sec_name in ("CRITICAL", "HIGH") or not validation.passed:
        db.update_draft_agent(rev["id"], status="rejected",
                              error_message=f"Gate failed: security={sec_name or 'NONE'}, "
                                            f"validator {validation.tools_passed}/{validation.tools_tested}")
        await _audit(user_id, "lifecycle.rejected",
                     f"Revision {rev['id']} failed the gate — live agent unchanged",
                     correlation_id=rev["id"], outcome="failure", agent_id=agent_id)
        return {"applied": False,
                "detail": "Security/validation gate failed — the live agent is unchanged. "
                          "The revision stays editable (Refine) or can be discarded."}

    live_tools = os.path.join(live_dir, "mcp_tools.py")
    backup = live_tools + ".bak027"
    # Snapshot scopes so the restart doesn't widen them (start_draft_agent
    # re-enables all scopes for testing; live agents must keep theirs).
    scopes_snapshot = {}
    try:
        scopes_snapshot = dict(orch.tool_permissions.get_agent_scopes(user_id, agent_id) or {})
    except Exception:
        logger.debug("agentic: scope snapshot failed", exc_info=True)

    try:
        await lifecycle.stop_draft_agent(live_row["id"])
        shutil.copy2(live_tools, backup)
        with open(live_tools, "w", encoding="utf-8") as fh:
            fh.write(new_code)
        await lifecycle.start_draft_agent(live_row["id"], align_scopes=False)
        db.update_draft_agent(live_row["id"], status="live")
    except Exception as exc:
        logger.exception("agentic: revision swap failed for %s — rolling back", agent_id)
        try:
            if os.path.exists(backup):
                shutil.copy2(backup, live_tools)
            await lifecycle.start_draft_agent(live_row["id"], align_scopes=False)
            db.update_draft_agent(live_row["id"], status="live")
        except Exception:
            logger.exception("agentic: rollback restart failed for %s", agent_id)
        db.update_draft_agent(rev["id"], status="rejected", error_message=str(exc)[:500])
        await _audit(user_id, "lifecycle.revision_rolled_back",
                     f"Revision {rev['id']} swap failed; backup restored",
                     correlation_id=rev["id"], outcome="failure", agent_id=agent_id)
        return {"applied": False, "detail": "Swap failed — the previous version was restored."}
    finally:
        try:
            if scopes_snapshot:
                orch.tool_permissions.set_agent_scopes(user_id, agent_id, scopes_snapshot)
        except Exception:
            logger.debug("agentic: scope restore failed", exc_info=True)
        try:
            if os.path.exists(backup):
                os.remove(backup)
        except OSError:
            pass

    # Success: clean up the staged clone + row.
    try:
        await lifecycle.delete_draft(rev["id"])
    except Exception:
        logger.warning("agentic: revision cleanup failed for %s", rev["id"], exc_info=True)
    await _audit(user_id, "lifecycle.revision_applied",
                 f"Revision applied to {agent_id}",
                 correlation_id=rev["id"], agent_id=agent_id)
    return {"applied": True, "detail": f"Revision applied — {agent_id} restarted with the new tools."}


# ---------------------------------------------------------------------------
# Decision handlers (chat cards + drafts surface; registered via chrome_events)
# ---------------------------------------------------------------------------

def _owned_draft(orch, user_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    draft_id = str(payload.get("draft_id") or "")
    draft = orch.history.db.get_draft_agent(draft_id) if draft_id else None
    if not draft or draft.get("user_id") != user_id:
        return None
    return draft


def _decidable_draft(orch, user_id: str, roles, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Draft the caller may refine/discard: the owner, OR an admin acting on an
    auto-created attachment parser (origin ``auto_attachment``, feature 031)."""
    draft_id = str(payload.get("draft_id") or "")
    draft = orch.history.db.get_draft_agent(draft_id) if draft_id else None
    if not draft:
        return None
    if draft.get("user_id") == user_id:
        return draft
    if draft.get("origin") == "auto_attachment" and "admin" in (roles or []):
        return draft
    return None


async def _send_chat_card(orch, websocket, component: Dict[str, Any]):
    await orch.send_ui_render(websocket, [component], target="chat")


async def _replace_card_state(orch, websocket, user_id: str, draft_id: str,
                              card: Dict[str, Any]) -> None:
    """Swap the canvas decision card for its post-decision state (030).

    The creation card persists in the chat's workspace under the stable
    author id ``draft-card-<draft_id>``; upserting a card with the same id
    morphs it in place on every socket, so a decided draft can no longer be
    re-actioned from stale buttons. Best-effort: a missing active chat
    (e.g. decision made from the Drafts surface) is fine — the chat bubble
    already communicated the outcome.
    """
    try:
        chat_id = orch._ws_active_chat.get(id(websocket)) if websocket is not None else None
        if not chat_id:
            return
        card = dict(card)
        card["id"] = f"draft-card-{draft_id}"
        await orch._send_or_replace_components(websocket, [card], chat_id, user_id=user_id)
    except Exception:
        logger.debug("decision card replacement failed (non-fatal)", exc_info=True)


def _terminal_card(draft_id: str, title: str, message: str) -> Dict[str, Any]:
    """Button-less end-state card that replaces the decision card."""
    return Card(id=f"draft-card-{draft_id}", title=title, content=[
        Text(content=message, variant="caption").to_dict(),
    ]).to_dict()


async def _promote_parser_global(orch, draft, agent_id, *, approved_by):
    """Feature 031 (FR-017): promote an approved attachment parser to a global,
    public capability and mark the registry live so every user's future uploads
    of that type resolve to ``covered``. Best-effort; never raises.
    """
    try:
        from orchestrator import attachment_autoparse
        from orchestrator.attachments.parser_repo import AttachmentParserRepository

        parser_repo = AttachmentParserRepository(orch.history.db)
        row = parser_repo.get_by_draft(draft["id"]) or {}
        gap = row.get("gap_fingerprint")
        extension = row.get("extension")
        requested_by = row.get("requested_by")
        tool_name = attachment_autoparse._tool_name_for(extension)

        # Make the agent public (global), then mark the registry live.
        try:
            orch.history.db.set_agent_visibility(agent_id, True)
        except Exception:
            logger.debug("autoparse: set_agent_visibility failed", exc_info=True)
        if gap:
            parser_repo.mark_live(gap, live_agent_id=agent_id, tool_name=tool_name,
                                  approved_by=approved_by)

        # Enable the (read-only) scopes the parser needs for the originating
        # user so it's usable immediately; other users pick it up via the
        # public-catalog consent path (feature 030).
        try:
            scopes = orch.tool_permissions.scopes_required_by_tools(agent_id) or []
            grant = {s: True for s in scopes if s != "tools:write"}
            if grant and requested_by:
                orch.tool_permissions.set_agent_scopes(requested_by, agent_id, grant)
        except Exception:
            logger.debug("autoparse: scope grant failed", exc_info=True)

        # FR-017: tell the originating user the reader is ready (the file they
        # uploaded can now be read — ask again to use it).
        if requested_by:
            await attachment_autoparse._notify_user(
                orch, requested_by,
                f"The .{extension} reader is live — ask again to read your file.")
    except Exception:
        logger.exception("autoparse: global promotion failed for draft %s", draft.get("id"))


async def _h_draft_approve(orch, websocket, user_id, roles, payload):
    """Approve a draft: existing security gate → live (US1 scenario 4).

    Feature 031: auto-created attachment-parser drafts (origin
    ``auto_attachment``) require the **admin** role to approve (FR-015) and are
    promoted **globally** (public, available to all users — FR-017), not into
    the approver's private fleet. Non-admins are refused and audited.
    """
    draft_id = str(payload.get("draft_id") or "")
    raw_draft = orch.history.db.get_draft_agent(draft_id) if draft_id else None
    is_autoparse = bool(raw_draft and raw_draft.get("origin") == "auto_attachment")

    if is_autoparse:
        # Admin-only approval; the uploader (owner) cannot self-approve.
        if "admin" not in (roles or []):
            await _audit(user_id, "lifecycle.rejected",
                         f"Non-admin approval attempt on parser draft {draft_id}",
                         correlation_id=draft_id, outcome="failure")
            await _send_chat_card(orch, websocket, _error_card(
                "Approving an auto-created file parser requires the admin role."))
            return None
        draft = raw_draft
    else:
        draft = _owned_draft(orch, user_id, payload)
        if draft is None:
            await _send_chat_card(orch, websocket, _error_card("Draft not found (it may have been discarded)."))
            return None

    result = await orch.lifecycle_manager.approve_agent(draft["id"], websocket=websocket)
    status = (result or {}).get("status")
    corr = draft["id"]
    if status == "live":
        agent_id = f"{draft['agent_slug'].replace('_', '-')}-1"
        if is_autoparse:
            await _promote_parser_global(orch, draft, agent_id, approved_by=user_id)
        await _audit(user_id, "lifecycle.approved", f"Draft {draft['id']} approved → live",
                     correlation_id=corr, agent_id=agent_id)
        live_msg = ("Security checks passed. The parser is live and available to everyone — "
                    "re-upload or ask again to read that file type."
                    if is_autoparse else
                    "Security checks passed. The agent joined your fleet and is usable "
                    "right now — just ask again.")
        await _send_chat_card(orch, websocket, Card(title=f"{draft['agent_name']} is live", content=[
            Text(content=live_msg, variant="default").to_dict(),
        ]).to_dict())
        await _replace_card_state(orch, websocket, user_id, draft["id"], _terminal_card(
            draft["id"], f"✓ Approved: {draft['agent_name']}",
            "Approved and live — ask again to use it."))
    else:
        detail = (result or {}).get("error_message") or f"status: {status}"
        await _audit(user_id, "lifecycle.rejected", f"Draft {draft['id']} not promoted ({status})",
                     correlation_id=corr, outcome="failure")
        not_promoted = Card(title=f"{draft['agent_name']}: not promoted", content=[
            Text(content=f"The approval gate did not pass — {detail}. The draft stays "
                         f"editable: Refine it or Discard it.", variant="default").to_dict(),
        ] + _decision_buttons(draft["id"])).to_dict()
        await _send_chat_card(orch, websocket, not_promoted)
        await _replace_card_state(orch, websocket, user_id, draft["id"], not_promoted)
    return None


async def _h_draft_refine(orch, websocket, user_id, roles, payload):
    """Refine a draft conversationally (US1 scenario 5)."""
    draft = _decidable_draft(orch, user_id, roles, payload)
    if draft is None:
        await _send_chat_card(orch, websocket, _error_card("Draft not found (it may have been discarded)."))
        return None
    message = str(payload.get("message") or (payload.get("fields") or {}).get("message") or "").strip()
    if not message:
        # Render an inline refine-input card.
        await _send_chat_card(orch, websocket, Card(title=f"Refine {draft['agent_name']}", content=[
            {"type": "param_picker", "title": "What should change?",
             "fields": [{"name": "message", "kind": "text", "label": "Describe the fix/change"}],
             "submit_label": "Refine",
             "submit_message_template": f"Refine draft {draft['id']}: {{message}}"},
        ]).to_dict())
        return None
    result = await orch.lifecycle_manager.refine_agent(draft["id"], message, websocket=websocket)
    await _audit(user_id, "lifecycle.refined", f"Draft {draft['id']} refined",
                 correlation_id=draft["id"])
    note = ("Refined. Test it again in chat, then Approve / Discard."
            if result.get("status") != "error"
            else f"Refine failed: {result.get('error_message', 'unknown error')}")
    self_test = json.loads((orch.history.db.get_draft_agent(draft["id"]) or {}).get("self_test") or "{}")
    refreshed = creation_card(
        orch.history.db.get_draft_agent(draft["id"]) or draft, self_test,
        revision=bool(draft.get("revises_agent_id")), note=note)
    await _send_chat_card(orch, websocket, refreshed)
    # Same stable id → the canvas card morphs to the refreshed state.
    await _replace_card_state(orch, websocket, user_id, draft["id"], refreshed)
    return None


async def _h_draft_discard(orch, websocket, user_id, roles, payload):
    """Decline/discard a draft (FR-002: declined drafts are removed)."""
    draft = _decidable_draft(orch, user_id, roles, payload)
    if draft is None:
        await _send_chat_card(orch, websocket, _error_card("Draft not found (already discarded?)."))
        return None
    # Feature 031: if this is an auto-created parser, mark its registry row
    # discarded so the format can be re-attempted by a later upload.
    if draft.get("origin") == "auto_attachment":
        try:
            from orchestrator.attachments.parser_repo import (
                AttachmentParserRepository, STATUS_DISCARDED,
            )
            _pr = AttachmentParserRepository(orch.history.db)
            _row = _pr.get_by_draft(draft["id"])
            if _row:
                _pr.mark_status(_row["gap_fingerprint"], STATUS_DISCARDED)
        except Exception:
            logger.debug("autoparse: discard registry update failed", exc_info=True)
    await orch.lifecycle_manager.delete_draft(draft["id"])
    await _audit(user_id, "lifecycle.discarded", f"Draft {draft['id']} discarded",
                 correlation_id=draft["id"])
    await _send_chat_card(orch, websocket, Card(title="Draft discarded", content=[
        Text(content=f"'{draft['agent_name']}' was removed. I'll answer with existing "
                     f"capabilities where I can.", variant="default").to_dict(),
    ]).to_dict())
    await _replace_card_state(orch, websocket, user_id, draft["id"], _terminal_card(
        draft["id"], f"Discarded: {draft['agent_name']}",
        "This draft was removed — nothing went live."))
    return None


async def _h_revision_apply(orch, websocket, user_id, roles, payload):
    """Apply a staged revision to its live agent (gate → swap → rollback-safe)."""
    rev = _owned_draft(orch, user_id, payload)
    if rev is None or not rev.get("revises_agent_id"):
        await _send_chat_card(orch, websocket, _error_card("Revision not found."))
        return None
    outcome = await apply_revision(orch, rev, user_id)
    if outcome["applied"]:
        await _send_chat_card(orch, websocket, Card(title="Revision applied", content=[
            Text(content=outcome["detail"], variant="default").to_dict()]).to_dict())
        await _replace_card_state(orch, websocket, user_id, rev["id"], _terminal_card(
            rev["id"], "✓ Revision applied", outcome["detail"]))
    else:
        not_applied = Card(title="Revision not applied", content=[
            Text(content=outcome["detail"], variant="default").to_dict(),
        ] + _decision_buttons(rev["id"], revision=True)).to_dict()
        await _send_chat_card(orch, websocket, not_applied)
        await _replace_card_state(orch, websocket, user_id, rev["id"], not_applied)
    return None


async def _h_revision_discard(orch, websocket, user_id, roles, payload):
    return await _h_draft_discard(orch, websocket, user_id, roles, payload)


HANDLERS = {
    "draft_approve": _h_draft_approve,
    "draft_refine": _h_draft_refine,
    "draft_discard": _h_draft_discard,
    "revision_apply": _h_revision_apply,
    "revision_discard": _h_revision_discard,
}
