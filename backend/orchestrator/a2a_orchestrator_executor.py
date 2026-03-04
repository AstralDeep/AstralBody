"""
Orchestrator A2A Executor — Exposes the orchestrator as an A2A-compliant agent.

External A2A clients can discover the orchestrator at /a2a/.well-known/agent-card.json
and send messages via JSON-RPC at /a2a/. The orchestrator routes messages through its
LLM-powered tool selection and returns aggregated results.
"""
import asyncio
import os
import uuid
import logging
from typing import Optional

from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import (
    AgentCard as A2AAgentCard,
    AgentCapabilities,
    AgentSkill as A2AAgentSkill,
    AgentProvider,
    Part,
    TextPart,
    DataPart,
    Message as A2AMessage,
    Role,
    SecurityScheme,
)

from shared.a2a_bridge import extract_text_from_a2a_message, a2a_message_to_mcp_request
from shared.a2a_security import A2ASecurityValidator

logger = logging.getLogger("OrchestratorA2AExecutor")


class OrchestratorA2AExecutor(AgentExecutor):
    """Wraps the orchestrator's routing logic as an A2A AgentExecutor.

    External A2A clients can send natural language messages which get routed
    through the orchestrator's LLM tool selection, or direct tool calls
    via DataPart.
    """

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.security_validator = A2ASecurityValidator()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        try:
            await updater.start_work()

            message = context.message
            if not message:
                await updater.failed(
                    message=self._msg("No message provided", context.task_id)
                )
                return

            # Check for direct tool call
            mcp_request = a2a_message_to_mcp_request(message)
            if mcp_request:
                await self._execute_direct_tool(mcp_request, updater, context)
                return

            # Natural language: extract text and route through available tools
            text = extract_text_from_a2a_message(message)
            if not text.strip():
                # Return list of all available tools
                await self._list_all_tools(updater, context)
                return

            # Route through LLM tool selection
            await self._execute_natural_language(text, updater, context)

        except Exception as e:
            logger.error(f"Orchestrator A2A execute error: {e}", exc_info=True)
            await updater.failed(
                message=self._msg(str(e), context.task_id)
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()

    async def _execute_direct_tool(self, mcp_request, updater, context):
        """Execute a direct tool call via the orchestrator's dual-transport dispatch."""
        tool_name = mcp_request.params.get("name", "")
        arguments = mcp_request.params.get("arguments", {})

        # Find which agent owns this tool
        tool_to_agent = {}
        for agent_id, caps in self.orchestrator.agent_capabilities.items():
            for cap in caps:
                tool_to_agent[cap["name"]] = agent_id

        agent_id = tool_to_agent.get(tool_name)
        if not agent_id:
            await updater.failed(
                message=self._msg(f"No agent found for tool '{tool_name}'", context.task_id)
            )
            return

        result = await self.orchestrator.execute_tool_and_wait(agent_id, tool_name, arguments)

        if result and result.error:
            error_msg = result.error.get("message", "Tool failed") if isinstance(result.error, dict) else str(result.error)
            parts = [Part(root=TextPart(text=f"Error: {error_msg}"))]
            if result.ui_components:
                parts.append(Part(root=DataPart(data={"_ui_components": result.ui_components})))
            await updater.failed(message=A2AMessage(
                message_id=str(uuid.uuid4()), role=Role.agent,
                parts=parts, task_id=context.task_id,
            ))
        else:
            parts = []
            if result and result.result is not None:
                if isinstance(result.result, dict):
                    parts.append(Part(root=DataPart(data=result.result)))
                else:
                    parts.append(Part(root=TextPart(text=str(result.result))))
            if result and result.ui_components:
                parts.append(Part(root=DataPart(
                    data={"_ui_components": result.ui_components},
                    metadata={"type": "ui_components"},
                )))
            if not parts:
                parts.append(Part(root=TextPart(text="OK")))

            msg = A2AMessage(
                message_id=str(uuid.uuid4()), role=Role.agent,
                parts=parts, task_id=context.task_id,
            )
            await updater.complete(message=msg)

    async def _execute_natural_language(self, text, updater, context):
        """Route a natural language message through the LLM for tool selection."""
        # For now, return the available tools as a helpful response
        # Full LLM routing requires a user session which A2A callers may not have
        await self._list_all_tools(updater, context, intro_text=f"Received: {text}\n\nAvailable tools:")

    async def _list_all_tools(self, updater, context, intro_text="Available tools:"):
        """Return all available tools across all agents."""
        all_tools = []
        for agent_id, caps in self.orchestrator.agent_capabilities.items():
            card = self.orchestrator.agent_cards.get(agent_id)
            agent_name = card.name if card else agent_id
            for cap in caps:
                all_tools.append({
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "name": cap["name"],
                    "description": cap.get("description", ""),
                })

        parts = [
            Part(root=TextPart(text=intro_text)),
            Part(root=DataPart(data={"tools": all_tools})),
        ]
        msg = A2AMessage(
            message_id=str(uuid.uuid4()), role=Role.agent,
            parts=parts, task_id=context.task_id,
        )
        await updater.complete(message=msg)

    @staticmethod
    def _msg(text: str, task_id: str) -> A2AMessage:
        return A2AMessage(
            message_id=str(uuid.uuid4()), role=Role.agent,
            parts=[Part(root=TextPart(text=text))], task_id=task_id,
        )


def build_orchestrator_a2a_card(orchestrator) -> A2AAgentCard:
    """Build an official A2A AgentCard for the orchestrator.

    Aggregates all connected agent skills into the orchestrator's card.
    """
    port = int(os.getenv("ORCHESTRATOR_PORT", 9001))
    host = os.getenv("HOST", "0.0.0.0")
    authority = os.getenv("VITE_KEYCLOAK_AUTHORITY", "")

    skills = []
    for agent_id, caps in orchestrator.agent_capabilities.items():
        card = orchestrator.agent_cards.get(agent_id)
        for cap in caps:
            skill_tags = ["agent:" + agent_id]
            if card:
                for s in card.skills:
                    if s.id == cap["name"] and s.scope:
                        skill_tags.append(f"scope:{s.scope}")
            skills.append(A2AAgentSkill(
                id=cap["name"],
                name=cap["name"],
                description=cap.get("description", ""),
                tags=skill_tags,
            ))

    security_schemes = None
    security = None
    if authority:
        security_schemes = {
            "keycloak_oidc": SecurityScheme(
                type="openIdConnect",
                openIdConnectUrl=f"{authority}/.well-known/openid-configuration",
            )
        }
        security = [{"keycloak_oidc": ["tools:read", "tools:write", "tools:search", "tools:system"]}]

    return A2AAgentCard(
        name="AstralBody Orchestrator",
        description="Multi-agent orchestrator with LLM-powered tool routing. Routes requests to specialized agents.",
        url=f"http://{host}:{port}/a2a",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True),
        skills=skills if skills else [A2AAgentSkill(
            id="chat", name="chat",
            description="Send a natural language message for LLM-powered routing",
            tags=["routing"],
        )],
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["application/json"],
        protocol_version="0.3.0",
        preferred_transport="JSONRPC",
        provider=AgentProvider(
            organization="AstralBody",
            url=os.getenv("PUBLIC_BASE_URL", "http://localhost:5173"),
        ),
        security_schemes=security_schemes,
        security=security,
    )


def setup_orchestrator_a2a(app, orchestrator):
    """Mount the A2A JSON-RPC endpoint on the orchestrator's FastAPI app."""
    from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
    from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
    from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore

    # Build card dynamically (will be refreshed on each request via card_modifier)
    initial_card = build_orchestrator_a2a_card(orchestrator)

    executor = OrchestratorA2AExecutor(orchestrator)
    task_store = InMemoryTaskStore()
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
    )

    def refresh_card(card):
        """Refresh the orchestrator's A2A card with current agent skills."""
        return build_orchestrator_a2a_card(orchestrator)

    a2a_app = A2AFastAPIApplication(
        agent_card=initial_card,
        http_handler=handler,
        card_modifier=refresh_card,
    )

    a2a_fastapi = a2a_app.build()
    app.mount("/a2a", a2a_fastapi)
