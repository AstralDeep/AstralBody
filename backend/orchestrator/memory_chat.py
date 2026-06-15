"""030-finish-soul-integration — cross-session memory from chat (025 T036).

Feature 025 shipped working memory tools (``personalization/memory_tools.py``)
and passive prompt-injected recall, but the tools were never registered with the
orchestrator, so the assistant could not actually *use* them on request. This
module makes them reachable as LLM tool calls, mirroring ``scheduling_chat.py``
(a pseudo-agent id keeps the meta-tool outside every real-agent permission gate).

Unlike scheduling (which needs a consent card before a job is created), memory
operations are low-risk and PHI-gated, so they execute immediately and return a
small confirmation. Passive recall via the personalization prompt fragment is
unchanged — this only adds the active path.
"""
import logging
from typing import Any, Dict, List, Optional

from astralprims import Alert, Text
from shared.feature_flags import flags

logger = logging.getLogger("Orchestrator.MemoryChat")

META_AGENT_ID = "__memory__"

SYSTEM_PROMPT_ADDENDUM = """
CROSS-SESSION MEMORY (remember / memory_search / memory_get):
- This system DOES support durable, cross-session memory of NON-PHI personalization
  facts. When the user asks you to remember a preference/goal/workflow ("remember I
  prefer concise answers", "note that I work on NSF grants"), call `remember`.
- To answer "what do you know about me / my preferences", call `memory_search` (with a
  query) or `memory_get` (everything). Prefer recalling stored facts over guessing.
- Never store protected health information (PHI) — the system refuses PHI writes
  automatically; do not work around it.
"""

#: Valid memory categories (mirrors personalization.repository.MEMORY_CATEGORIES).
_CATEGORIES = ("profession", "goal", "preference", "workflow_tag", "context")


def meta_tool_definitions() -> List[Dict[str, Any]]:
    """OpenAI-style tool definitions for the memory meta-tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": "remember",
                "description": (
                    "Durably remember a NON-PHI personalization fact about the user "
                    "(a preference, goal, profession, or working-context note) so it is "
                    "recalled in future sessions. PHI is refused automatically."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string", "description": "The fact to remember, phrased succinctly"},
                        "category": {"type": "string", "enum": list(_CATEGORIES),
                                     "description": "Kind of fact (defaults to 'context')"},
                    },
                    "required": ["value"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "memory_search",
                "description": "Search the user's durable memory for facts matching a query.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "What to look for"},
                        "limit": {"type": "integer", "description": "Max results (default 10)"},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "memory_get",
                "description": "Return everything currently remembered about the user.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


def should_inject(draft_agent_id: Optional[str]) -> bool:
    """Offered on normal chat turns only — same exclusions as feature 027/030 scheduling."""
    return flags.is_enabled("memory_chat") and not draft_agent_id


def _memory_tools(orch):
    """Lazily build a MemoryTools bound to the orchestrator's personalization repo."""
    cached = getattr(orch, "_memory_tools", None)
    if cached is not None:
        return cached
    from personalization.memory_tools import MemoryTools
    repo = orch.personalization_service.repo
    tools = MemoryTools(repo)
    orch._memory_tools = tools
    return tools


async def _audit(user_id: str, action_type: str, description: str,
                 outcome: str = "success", chat_id: Optional[str] = None,
                 inputs_meta: Optional[Dict] = None) -> None:
    """Record a ``personalization`` audit event (best-effort, never raises)."""
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
            event_class="personalization",
            action_type=action_type,
            description=description[:1024],
            conversation_id=chat_id,
            outcome=outcome,
            inputs_meta=inputs_meta or {},
            started_at=datetime.now(timezone.utc),
        ))
    except Exception:
        logger.debug("memory_chat: audit record failed (%s)", action_type, exc_info=True)


async def handle_meta_tool(orch, tool_name: str, args: Dict[str, Any], *,
                           user_id: str, chat_id: Optional[str], websocket):
    """Dispatch a memory meta-tool call. Executes immediately (PHI-gated) and
    returns a result + a small confirmation component. No consent card."""
    from shared.protocol import MCPResponse

    args = args or {}
    tools = _memory_tools(orch)

    if tool_name == "remember":
        value = str(args.get("value") or "").strip()
        category = str(args.get("category") or "context").strip()
        res = tools.remember(user_id, category, value)
        if res.get("stored"):
            await _audit(user_id, "memory.remember",
                         f"Remembered a {res.get('category')} fact", chat_id=chat_id,
                         inputs_meta={"category": res.get("category"), "memory_id": res.get("id")})
            comp = Alert(message="Got it — I'll remember that.", variant="success").to_dict()
            return MCPResponse(result={"status": "stored", **res}, ui_components=[comp])
        # Refused (PHI or empty) — surface the reason without persisting.
        await _audit(user_id, "memory.remember_refused", "Memory write refused",
                     outcome="denied", chat_id=chat_id)
        comp = Alert(message=res.get("reason", "I could not save that."),
                     variant="warning").to_dict()
        return MCPResponse(result={"status": "refused", **res}, ui_components=[comp])

    if tool_name == "memory_search":
        query = str(args.get("query") or "").strip()
        try:
            limit = int(args.get("limit") or 10)
        except (TypeError, ValueError):
            limit = 10
        items = tools.memory_search(user_id, query, limit=max(1, min(limit, 50)))
        return MCPResponse(result={"status": "ok", "count": len(items), "items": items},
                           ui_components=[_recall_component(items)])

    if tool_name == "memory_get":
        items = tools.memory_get(user_id)
        return MCPResponse(result={"status": "ok", "count": len(items), "items": items},
                           ui_components=[_recall_component(items)])

    return MCPResponse(error={"message": f"Unknown memory tool '{tool_name}'",
                              "retryable": False})


def _recall_component(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Small recall summary for the chat (server-driven; no new primitive)."""
    if not items:
        return Text(content="I don't have anything remembered about you yet.",
                    variant="caption").to_dict()
    lines = "\n".join(f"- ({it.get('category', 'context')}) {it.get('value', '')}" for it in items)
    return Text(content=f"Here's what I remember:\n{lines}").to_dict()
