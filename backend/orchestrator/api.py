"""
REST API routes for the AstralBody backend.

Provides HTTP endpoints that mirror the WebSocket actions, enabling
any frontend (PHP, Flutter, other JS frameworks) to interact with
the orchestrator without implementing the WebSocket protocol.

WebSocket remains the primary channel for real-time features (streaming
chat responses, live status updates). These REST endpoints provide
request/response access for CRUD operations.
"""
import time
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse

from orchestrator.models import (
    ChatMessageRequest, ChatMessageResponse,
    ChatListResponse, ChatSummary,
    ChatCreateResponse,
    ChatDetailResponse, ChatDetail, ChatMessage,
    DeleteResponse,
    ComponentSaveRequest, ComponentSaveResponse, SavedComponent,
    ComponentListResponse,
    ComponentCombineRequest, ComponentCondenseRequest, ComponentCombineResponse,
    AgentListResponse, AgentInfo, AgentTool,
    AgentPermissionsRequest, AgentPermissionsResponse,
    DashboardResponse,
    ErrorResponse,
)
from orchestrator.auth import get_current_user_id, require_user_id

logger = logging.getLogger("API")

# =============================================================================
# Helpers
# =============================================================================

def _get_orchestrator(request: Request):
    """Retrieve the shared Orchestrator instance from app state."""
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        # Walk up to parent app if mounted as sub-app
        root_app = getattr(request.app, "_root_app", None) or request.app
        orch = getattr(root_app.state, "orchestrator", None)
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return orch


# =============================================================================
# Chat Router
# =============================================================================

chat_router = APIRouter(prefix="/api/chats", tags=["Chat"])


@chat_router.get(
    "",
    response_model=ChatListResponse,
    summary="List recent chats",
    description="Returns a list of recent chat sessions for the authenticated user, ordered by most recent first.",
)
async def list_chats(
    request: Request,
    limit: int = 20,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    chats = orch.history.get_recent_chats(limit=limit, user_id=user_id)
    return ChatListResponse(chats=[ChatSummary(**c) for c in chats])


@chat_router.post(
    "",
    response_model=ChatCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat",
    description="Creates a new empty chat session and returns its ID.",
)
async def create_chat(
    request: Request,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    chat_id = orch.history.create_chat(user_id=user_id)
    return ChatCreateResponse(chat_id=chat_id)


@chat_router.get(
    "/{chat_id}",
    response_model=ChatDetailResponse,
    summary="Load a chat",
    description="Returns full chat details including all messages.",
    responses={404: {"model": ErrorResponse}},
)
async def get_chat(
    request: Request,
    chat_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    chat = orch.history.get_chat(chat_id, user_id=user_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return ChatDetailResponse(chat=ChatDetail(**chat))


@chat_router.delete(
    "/{chat_id}",
    response_model=DeleteResponse,
    summary="Delete a chat",
    description="Deletes a chat session and all its messages.",
    responses={404: {"model": ErrorResponse}},
)
async def delete_chat(
    request: Request,
    chat_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    orch.history.delete_chat(chat_id, user_id=user_id)
    return DeleteResponse(message=f"Chat {chat_id} deleted")


@chat_router.post(
    "/{chat_id}/messages",
    response_model=ChatMessageResponse,
    summary="Send a chat message",
    description=(
        "Sends a message in the specified chat. This endpoint **acknowledges** the message immediately. "
        "The actual response (LLM tool routing, UI components) will stream back over the WebSocket connection. "
        "Connect to `ws://<host>:<port>/ws` and register to receive streaming results."
    ),
    responses={404: {"model": ErrorResponse}},
)
async def send_message(
    request: Request,
    chat_id: str,
    body: ChatMessageRequest,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)

    # Ensure chat exists
    if not orch.history.get_chat(chat_id, user_id=user_id):
        orch.history.create_chat(chat_id, user_id=user_id)

    # Save the user message to history
    msg_to_save = body.display_message if body.display_message else body.message
    orch.history.add_message(chat_id, "user", msg_to_save, user_id=user_id)

    # Try to dispatch the message for processing via the orchestrator.
    # If a WebSocket client is connected for this user, results stream to them.
    # If not, results are still saved to history.
    dispatched = False
    try:
        import asyncio
        for ws in orch.ui_clients:
            if ws in orch.ui_sessions:
                ws_user_id = orch.ui_sessions[ws].get("sub", "legacy")
                if ws_user_id == user_id:
                    asyncio.create_task(
                        orch.handle_chat_message(ws, body.message, chat_id, body.display_message, user_id=user_id)
                    )
                    dispatched = True
                    break

        if not dispatched:
            asyncio.create_task(
                orch.handle_chat_message(None, body.message, chat_id, body.display_message, user_id=user_id)
            )
    except Exception as e:
        logger.warning(f"Could not dispatch chat message for async processing: {e}")

    return ChatMessageResponse(
        chat_id=chat_id,
        status="accepted",
        message="Message received. Results will stream via WebSocket." if dispatched
               else "Message received. No WebSocket client connected — results will be saved to history.",
    )


# =============================================================================
# Component Router
# =============================================================================

component_router = APIRouter(prefix="/api", tags=["Components"])


@component_router.get(
    "/chats/{chat_id}/components",
    response_model=ComponentListResponse,
    summary="Get saved components for a chat",
    description="Returns all saved UI components for the specified chat session.",
)
async def get_components(
    request: Request,
    chat_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    components = orch.history.get_saved_components(chat_id, user_id=user_id)
    return ComponentListResponse(components=[SavedComponent(**c) for c in components])


@component_router.post(
    "/chats/{chat_id}/components",
    response_model=ComponentSaveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a component",
    description="Save a UI component to the specified chat session.",
)
async def save_component(
    request: Request,
    chat_id: str,
    body: ComponentSaveRequest,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    component_id = orch.history.save_component(
        chat_id,
        body.component_data,
        body.component_type,
        body.title,
        user_id=user_id,
    )
    return ComponentSaveResponse(
        component=SavedComponent(
            id=component_id,
            chat_id=chat_id,
            component_data=body.component_data,
            component_type=body.component_type,
            title=body.title or body.component_type.replace("_", " ").title(),
            created_at=int(time.time() * 1000),
        )
    )


@component_router.delete(
    "/components/{component_id}",
    response_model=DeleteResponse,
    summary="Delete a saved component",
    responses={404: {"model": ErrorResponse}},
)
async def delete_component(
    request: Request,
    component_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    success = orch.history.delete_component(component_id, user_id=user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Component not found")
    return DeleteResponse(message=f"Component {component_id} deleted")


@component_router.post(
    "/components/combine",
    response_model=ComponentCombineResponse,
    summary="Combine two components",
    description="Uses LLM to merge two saved components into a single cohesive component.",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def combine_components(
    request: Request,
    body: ComponentCombineRequest,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    source = orch.history.get_component_by_id(body.source_id, user_id=user_id)
    target = orch.history.get_component_by_id(body.target_id, user_id=user_id)

    if not source or not target:
        raise HTTPException(status_code=404, detail="One or both components not found")

    result = await orch._combine_components_llm([source, target], mode="combine")

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    chat_id = source["chat_id"]
    new_components = orch.history.replace_components(
        [body.source_id, body.target_id],
        result["components"],
        chat_id,
        user_id=user_id,
    )
    return ComponentCombineResponse(
        removed_ids=[body.source_id, body.target_id],
        new_components=[SavedComponent(**c) for c in new_components],
    )


@component_router.post(
    "/components/condense",
    response_model=ComponentCombineResponse,
    summary="Condense multiple components",
    description="Uses LLM to reduce multiple saved components into fewer cohesive components.",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def condense_components(
    request: Request,
    body: ComponentCondenseRequest,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    components = []
    for cid in body.component_ids:
        comp = orch.history.get_component_by_id(cid, user_id=user_id)
        if comp:
            components.append(comp)

    if len(components) < 2:
        raise HTTPException(status_code=400, detail="Not enough valid components found (need at least 2)")

    result = await orch._combine_components_llm(components, mode="condense")

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    chat_id = components[0]["chat_id"]
    new_components = orch.history.replace_components(
        body.component_ids,
        result["components"],
        chat_id,
        user_id=user_id,
    )
    return ComponentCombineResponse(
        removed_ids=body.component_ids,
        new_components=[SavedComponent(**c) for c in new_components],
    )


# =============================================================================
# Agent Router
# =============================================================================

agent_router = APIRouter(prefix="/api/agents", tags=["Agents"])


@agent_router.get(
    "",
    response_model=AgentListResponse,
    summary="List connected agents",
    description="Returns all agents currently connected to the orchestrator, including their tools and capabilities.",
)
async def list_agents(request: Request):
    orch = _get_orchestrator(request)
    agents = []
    for agent_id, card in orch.agent_cards.items():
        agents.append(AgentInfo(
            id=card.agent_id,
            name=card.name,
            description=card.description,
            tools=[
                AgentTool(name=s.id, description=s.description, input_schema=s.input_schema)
                for s in card.skills
            ],
            status="connected",
        ))
    return AgentListResponse(agents=agents)


@agent_router.get(
    "/{agent_id}/permissions",
    response_model=AgentPermissionsResponse,
    summary="Get agent tool permissions",
    description="Returns the current user's per-tool permissions for the specified agent.",
)
async def get_agent_permissions(
    request: Request,
    agent_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    card = orch.agent_cards.get(agent_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    available_tools = [s.id for s in card.skills]
    tool_descriptions = {s.id: s.description for s in card.skills}
    permissions = orch.tool_permissions.get_effective_permissions(
        user_id, agent_id, available_tools
    )
    return AgentPermissionsResponse(
        agent_id=agent_id,
        agent_name=card.name,
        permissions=permissions,
        tool_descriptions=tool_descriptions,
    )


@agent_router.put(
    "/{agent_id}/permissions",
    response_model=AgentPermissionsResponse,
    summary="Update agent tool permissions",
    description="Update the current user's per-tool permissions for the specified agent. Set tool_name to true (allowed) or false (blocked).",
)
async def set_agent_permissions(
    request: Request,
    agent_id: str,
    body: AgentPermissionsRequest,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    card = orch.agent_cards.get(agent_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    orch.tool_permissions.set_bulk_permissions(user_id, agent_id, body.permissions)
    available_tools = [s.id for s in card.skills]
    tool_descriptions = {s.id: s.description for s in card.skills}
    updated_permissions = orch.tool_permissions.get_effective_permissions(
        user_id, agent_id, available_tools
    )
    return AgentPermissionsResponse(
        agent_id=agent_id,
        agent_name=card.name,
        permissions=updated_permissions,
        tool_descriptions=tool_descriptions,
    )


# =============================================================================
# Dashboard Router
# =============================================================================

dashboard_router = APIRouter(prefix="/api", tags=["System"])


@dashboard_router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Get system dashboard",
    description="Returns system configuration including connected agents and total tool count.",
)
async def get_dashboard(request: Request):
    orch = _get_orchestrator(request)
    agents = []
    for agent_id, card in orch.agent_cards.items():
        agents.append(AgentInfo(
            id=card.agent_id,
            name=card.name,
            tools=[
                AgentTool(name=s.id, description=s.description)
                for s in card.skills
            ],
            status="connected",
        ))
    return DashboardResponse(
        agents=agents,
        total_tools=sum(len(c) for c in orch.agent_capabilities.values()),
    )
