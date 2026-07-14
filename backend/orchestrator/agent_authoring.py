"""BYO agent authoring orchestration (feature 058, T009 + T016).

The create→analyze→generate→deliver flow for a user-authored agent. The load-
bearing property is STRUCTURAL: the 057 Analyze gate runs BEFORE ``generate_code``
so a constitution-violating draft produces NO code and never goes live
(FR-003/SC-004). On a passing Analyze the draft is generated (static code gates
run inside the lifecycle), the ``user_agent`` row is marked ``validated``, and the
bundle is DELIVERED to the owner's desktop host — never Popen'd on the
orchestrator (SC-002). The desktop host then runs it and dials back in over the
tunnel (register → go_live).

This module is the minimal one-shot path; the full 5-phase Specify→Clarify→Plan→
Tasks→Analyze chrome flow builds on the same orchestration.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Orchestrator.AgentAuthoring")


def slug_agent_id(agent_name: str, owner_user_id: str) -> str:
    """Owner-namespaced, collision-resistant agent id from a display name.

    Never starts with ``__`` (reserved) and includes an owner hash so two users'
    identically-named agents never collide (Constitution H)."""
    base = re.sub(r"[^a-z0-9]+", "-", (agent_name or "agent").lower()).strip("-") or "agent"
    owner_tag = re.sub(r"[^a-z0-9]+", "", (owner_user_id or "").lower())[:8] or "user"
    return f"ua-{base[:32]}-{owner_tag}"


def _bundle_files(draft: Dict[str, Any]) -> Dict[str, str]:
    """Extract the generated 3-file agent bundle from a completed draft, for
    delivery to the host. Defensive: reads the known generated-code fields; the
    exact shape is finalized against the live generator during host integration."""
    files = draft.get("files") or draft.get("generated_files")
    if isinstance(files, dict) and files:
        return {str(k): str(v) for k, v in files.items()}
    # Fall back to a single-file bundle if the lifecycle exposes code inline.
    code = draft.get("agent_code") or draft.get("code")
    slug = draft.get("agent_slug") or "agent"
    if code:
        return {f"{slug}_agent.py": str(code)}
    return {}


async def author_and_deliver(
    orch, *, user_id: str, agent_name: str, description: str,
    declared_tools: Optional[List[Any]] = None,
    declared_scopes: Optional[List[str]] = None,
    declared_egress: Optional[List[str]] = None,
    plan: Optional[Dict[str, Any]] = None,
    agent_id: Optional[str] = None, chat_id: Optional[str] = None,
    websocket=None,
) -> Dict[str, Any]:
    """Run the BYO create→analyze→generate→deliver flow. Returns a status dict:

    - ``analyze_failed`` (+ ``violations``): the drafted spec violates the agent
      constitution; **no code was generated** (FR-003).
    - ``generation_failed`` (+ ``error``): Analyze passed but code generation or
      the static code gates failed.
    - ``delivered`` / ``no_host``: the validated bundle was pushed to the owner's
      desktop host (or no host was online to receive it).
    """
    from orchestrator import agent_analyze, user_agents as ua
    from orchestrator.agent_constitution import AGENT_CONSTITUTION_VERSION

    tool_names = [t.get("name") if isinstance(t, dict) else t
                  for t in (declared_tools or [])]
    tool_names = [str(t) for t in tool_names if t]
    agent_id = agent_id or slug_agent_id(agent_name, user_id)

    # ── Analyze gate (T016) — BEFORE any generation. ──────────────────────────
    spec = {
        "display_name": agent_name, "description": description,
        "agent_id": agent_id, "owner_user_id": user_id,
        "declared_tools": tool_names, "declared_scopes": declared_scopes or [],
        "declared_egress": declared_egress, "plan": plan or {},
    }
    result = agent_analyze.check(
        spec, constitution_version=AGENT_CONSTITUTION_VERSION, db=orch.history.db)
    if not result.passed:
        logger.info("byo authoring: Analyze blocked %s (%d violations) — no code generated",
                    agent_id, len(result.violations))
        return {"status": "analyze_failed", "agent_id": agent_id,
                "constitution_version": result.constitution_version,
                "violations": [
                    {"principle": v.principle, "title": v.title,
                     "plain_language": v.plain_language, "offending_field": v.offending_field}
                    for v in result.violations]}

    # Register the user_agent row (authoring) before generation.
    await asyncio.to_thread(
        ua.create_user_agent, orch.history.db, agent_id=agent_id,
        owner_user_id=user_id, display_name=agent_name, draft_id=None,
        declared_tools=tool_names, declared_scopes=declared_scopes or [],
        declared_egress=declared_egress)

    # ── Generate (static code gates run inside the lifecycle). ────────────────
    lifecycle = orch.lifecycle_manager
    draft = await lifecycle.create_draft(
        user_id=user_id, agent_name=agent_name, description=description,
        tools_spec=[{"name": n, "description": ""} for n in tool_names])
    draft_id = draft["id"]
    await asyncio.to_thread(orch.history.db.update_draft_agent, draft_id,
                            origin="byo_client")
    gen = await lifecycle.generate_code(draft_id, websocket=websocket)
    if (gen or {}).get("status") in ("error", "rejected"):
        return {"status": "generation_failed", "agent_id": agent_id,
                "draft_id": draft_id, "error": (gen or {}).get("error_message")}

    # ── Validated → deliver to the host (NEVER Popen on the orchestrator). ─────
    await asyncio.to_thread(
        ua.mark_validated, orch.history.db, agent_id, AGENT_CONSTITUTION_VERSION,
        declared_tools=tool_names, declared_scopes=declared_scopes or [])
    files = _bundle_files(gen or {})
    delivered = await orch.deliver_agent_bundle(
        user_id, agent_id, files, AGENT_CONSTITUTION_VERSION)
    logger.info("byo authoring: delivered %s to %d host socket(s)", agent_id, delivered)
    return {"status": "delivered" if delivered else "no_host",
            "agent_id": agent_id, "draft_id": draft_id, "delivered_to": delivered}
