"""
REST API routes for the AstralBody backend.

Provides HTTP endpoints that mirror the WebSocket actions, enabling
any frontend (PHP, Flutter, other JS frameworks) to interact with
the orchestrator without implementing the WebSocket protocol.

WebSocket remains the primary channel for real-time features (streaming
chat responses, live status updates). These REST endpoints provide
request/response access for CRUD operations.
"""
import asyncio
import base64
import json
import os
import time
import logging
from typing import Any, Dict, Optional

import aiohttp
import websockets as ws_client
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse, Response

from orchestrator.models import (
    ChatMessageRequest, ChatMessageResponse,
    ChatListResponse, ChatSummary,
    ChatCreateRequest, ChatCreateResponse,
    ChatDetailResponse, ChatDetail, ChatMessage,
    DeleteResponse,
    ComponentSaveRequest, ComponentSaveResponse, SavedComponent,
    ComponentListResponse,
    ComponentCombineRequest, ComponentCondenseRequest, ComponentCombineResponse,
    AgentListResponse, AgentInfo, AgentTool,
    AgentPermissionsRequest, AgentPermissionsResponse,
    AgentVisibilityRequest,
    ToolSelectionResponse, ToolSelectionUpdate,
    AgentEnabledUpdate, AgentEnabledResponse,
    CredentialSetRequest, CredentialListResponse, CredentialDeleteResponse,
    DashboardResponse,
    ErrorResponse,
    DraftAgentCreateRequest, DraftAgentRefineRequest, AdminReviewRequest,
    DraftAgentResponse, DraftAgentListResponse,
)
from orchestrator.auth import get_current_user_id, require_user_id, get_current_user_payload

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
    description=(
        "Creates a new empty chat session and returns its ID. "
        "Feature 013 / FR-006: pass `agent_id` in the body to bind the new "
        "chat to a specific agent so the UI can render the active-agent "
        "indicator. Omit to leave the chat unbound."
    ),
)
async def create_chat(
    request: Request,
    body: Optional[ChatCreateRequest] = None,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    agent_id = body.agent_id if body is not None else None
    chat_id = orch.history.create_chat(user_id=user_id, agent_id=agent_id)
    return ChatCreateResponse(chat_id=chat_id, agent_id=agent_id)


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


@chat_router.get(
    "/{chat_id}/steps",
    summary="Load persistent step entries for a chat",
    description=(
        "Feature 014 — returns the chronological sequence of step entries "
        "(tool calls / agent hand-offs / orchestrator phases) recorded for "
        "this chat. Used by the frontend on initial chat load and on "
        "WebSocket reconnect to rehydrate the in-chat step trail. All "
        "fields are PHI-redacted on the way out (defense-in-depth)."
    ),
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_chat_steps(
    request: Request,
    chat_id: str,
    response: Response,
    user_id: str = Depends(require_user_id),
):
    """Return all chat_steps rows for ``chat_id``, redacted and ordered.

    Read-time healing: any row with ``status='in_progress'`` older than
    30 seconds for which no active task exists is reported as
    ``status='interrupted'`` (FR-021 reconnect path). The healing is not
    persisted on this read; an orphaned-row sweep happens elsewhere.
    """
    orch = _get_orchestrator(request)

    # Ownership + existence check (matches the get_chat pattern).
    chat = orch.history.get_chat(chat_id, user_id=user_id)
    if not chat:
        # Try to differentiate "exists for another user" vs "does not exist".
        cross_user = orch.history.db.fetch_one(
            "SELECT 1 FROM chats WHERE id = ? LIMIT 1", (chat_id,)
        )
        if cross_user is not None:
            raise HTTPException(status_code=403, detail="Chat not owned by user")
        raise HTTPException(status_code=404, detail="Chat not found")

    response.headers["Cache-Control"] = "no-store"

    try:
        from shared.phi_redactor import redact

        rows = orch.history.db.fetch_all(
            "SELECT * FROM chat_steps WHERE chat_id = ? AND user_id = ? "
            "ORDER BY started_at ASC, id ASC",
            (chat_id, user_id),
        )

        # Read-time healing: orphan in-progress rows older than 30 s when
        # there is no active task on this chat — only mutate the response,
        # not the DB.
        import time as _time
        now_ms = int(_time.time() * 1000)
        active = orch.task_manager.get_active_task(chat_id)

        steps = []
        for row in rows:
            row = dict(row)
            status_value = row.get("status")
            if (
                status_value == "in_progress"
                and active is None
                and now_ms - int(row.get("started_at", 0)) > 30_000
            ):
                status_value = "interrupted"
            # Defense-in-depth re-redaction on every field that could
            # ever contain PHI.
            args_text, _ = redact(row.get("args_truncated"), kind="args")
            result_text, _ = redact(row.get("result_summary"), kind="result")
            error_text, _ = redact(row.get("error_message"), kind="error")
            steps.append({
                "id": row["id"],
                "chat_id": row["chat_id"],
                "turn_message_id": row.get("turn_message_id"),
                "kind": row["kind"],
                "name": row["name"],
                "status": status_value,
                "args_truncated": args_text,
                "args_was_truncated": bool(row.get("args_was_truncated", False)),
                "result_summary": result_text,
                "result_was_truncated": bool(row.get("result_was_truncated", False)),
                "error_message": error_text,
                "started_at": row["started_at"],
                "ended_at": row.get("ended_at"),
            })
        return {"chat_id": chat_id, "steps": steps}
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover — defensive
        logger.error("Failed to load chat steps: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load steps")


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


@chat_router.get(
    "/{chat_id}/usage",
    summary="Get LLM token usage for a chat",
    description="Returns accumulated LLM token usage (prompt, completion, total) for a conversation.",
)
async def get_chat_usage(
    request: Request,
    chat_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    usage = orch.token_usage.get(chat_id, {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })
    return JSONResponse(content={"chat_id": chat_id, "usage": usage})


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
    description="Returns all agents currently connected to the orchestrator, including their tools, capabilities, and ownership info.",
)
async def list_agents(
    request: Request,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    db = orch.history.db
    ownership_map = {o["agent_id"]: o for o in db.get_all_agent_ownership()}
    # Feature 013 follow-up: resolve the requesting user's per-agent
    # disabled list once so every row in the response carries it.
    disabled_set = set(db.get_user_disabled_agents(user_id))
    agents = []
    for agent_id, card in orch.agent_cards.items():
        # Hide draft agents that aren't live yet
        if orch._is_draft_agent(agent_id):
            continue
        ownership = ownership_map.get(agent_id, {})
        agents.append(AgentInfo(
            id=card.agent_id,
            name=card.name,
            description=card.description,
            tools=[
                AgentTool(name=s.id, description=s.description, input_schema=s.input_schema)
                for s in card.skills
            ],
            security_flags=orch.security_flags.get(agent_id, {}),
            status="connected",
            owner_email=ownership.get("owner_email"),
            is_public=bool(ownership.get("is_public", False)),
            disabled=agent_id in disabled_set,
        ))
    return AgentListResponse(agents=agents)


@agent_router.get(
    "/{agent_id}/permissions",
    response_model=AgentPermissionsResponse,
    summary="Get agent scope permissions",
    description="Returns the current user's scope-based permissions for the specified agent.",
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
    # Feature 013 / FR-015: on first read after the migration ships, lazily
    # backfill per-tool rows from the legacy scope state so users don't
    # have to re-toggle previously consented permissions. Idempotent —
    # subsequent reads insert nothing.
    try:
        orch.tool_permissions.backfill_per_tool_rows(user_id, agent_id)
    except Exception as e:  # pragma: no cover — defensive logging only
        logger.warning(f"Per-tool backfill failed for user={user_id} agent={agent_id}: {e}")
    available_tools = [s.id for s in card.skills]
    tool_descriptions = {s.id: s.description for s in card.skills}
    scopes = orch.tool_permissions.get_agent_scopes(user_id, agent_id)
    tool_scope_map = orch.tool_permissions.get_tool_scope_map(agent_id)
    permissions = orch.tool_permissions.get_effective_permissions(
        user_id, agent_id, available_tools
    )
    per_tool_permissions = orch.tool_permissions.get_effective_tool_permissions(
        user_id, agent_id
    )
    tool_overrides = orch.tool_permissions.get_tool_overrides(user_id, agent_id)
    return AgentPermissionsResponse(
        agent_id=agent_id,
        agent_name=card.name,
        scopes=scopes,
        tool_scope_map=tool_scope_map,
        permissions=permissions,
        per_tool_permissions=per_tool_permissions,
        tool_overrides=tool_overrides,
        tool_descriptions=tool_descriptions,
        security_flags=orch.security_flags.get(agent_id, {}),
    )


@agent_router.put(
    "/{agent_id}/permissions",
    response_model=AgentPermissionsResponse,
    summary="Update agent scope permissions",
    description="Update the current user's scope-based permissions for the specified agent. Scopes: tools:read, tools:write, tools:search, tools:system.",
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

    tool_scope_map = orch.tool_permissions.get_tool_scope_map(agent_id)
    legacy_payload = body.per_tool_permissions is None and (
        body.scopes is not None or body.tool_overrides is not None
    )

    # Feature 013 / preferred shape: per-tool, per-kind toggles.
    if body.per_tool_permissions is not None:
        # Validate every (tool, kind) pair is applicable to that tool
        # (FR-014). Reject the whole payload on any mismatch so partial
        # writes never leave a half-applied state.
        for tool_name, kind_map in body.per_tool_permissions.items():
            required = tool_scope_map.get(tool_name)
            if required is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Tool '{tool_name}' is not registered for agent '{agent_id}'.",
                )
            for kind in kind_map.keys():
                if kind != required:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Permission kind '{kind}' does not apply to tool "
                            f"'{tool_name}' (required: '{required}')."
                        ),
                    )
        for tool_name, kind_map in body.per_tool_permissions.items():
            for kind, enabled in kind_map.items():
                orch.tool_permissions.set_tool_permission(
                    user_id, agent_id, tool_name, kind, bool(enabled)
                )
        # Mirror up to the agent_scopes layer so the legacy filter path
        # remains coherent: a scope is enabled at the legacy layer iff at
        # least one tool of that kind is now enabled per-tool.
        scope_state = orch.tool_permissions.get_agent_scopes(user_id, agent_id)
        derived: Dict[str, bool] = {**scope_state}
        per_tool = orch.tool_permissions.get_effective_tool_permissions(user_id, agent_id)
        for tool_name, kind_map in per_tool.items():
            for kind, enabled in kind_map.items():
                if enabled:
                    derived[kind] = True
        orch.tool_permissions.set_agent_scopes(user_id, agent_id, derived)

    # Legacy shape for transitional clients — write scopes, then reflect
    # the change into per-tool rows so the new model stays in sync.
    elif legacy_payload:
        if body.scopes is not None:
            orch.tool_permissions.set_agent_scopes(user_id, agent_id, body.scopes)
        if body.tool_overrides is not None:
            orch.tool_permissions.set_tool_overrides(user_id, agent_id, body.tool_overrides)
        # Re-derive per-tool rows from the new scope+override state.
        for tool_name, required_scope in tool_scope_map.items():
            scope_enabled = orch.tool_permissions.is_scope_enabled(
                user_id, agent_id, required_scope
            )
            override_disabled = (body.tool_overrides or {}).get(tool_name, True) is False
            orch.tool_permissions.set_tool_permission(
                user_id, agent_id, tool_name, required_scope,
                bool(scope_enabled and not override_disabled),
            )
        logger.warning(
            "Legacy scope-shaped permissions update accepted for user=%s agent=%s "
            "(legacy_scope_update=true)",
            user_id,
            agent_id,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Request body must include either 'per_tool_permissions' or 'scopes'.",
        )

    available_tools = [s.id for s in card.skills]
    tool_descriptions = {s.id: s.description for s in card.skills}
    scopes = orch.tool_permissions.get_agent_scopes(user_id, agent_id)
    permissions = orch.tool_permissions.get_effective_permissions(
        user_id, agent_id, available_tools
    )
    per_tool_permissions = orch.tool_permissions.get_effective_tool_permissions(
        user_id, agent_id
    )
    tool_overrides = orch.tool_permissions.get_tool_overrides(user_id, agent_id)
    logger.info(
        "Agent permissions updated: user=%s agent=%s shape=%s tools_changed=%d",
        user_id,
        agent_id,
        "per_tool" if body.per_tool_permissions is not None else "legacy_scope",
        len(body.per_tool_permissions or {}),
    )
    return AgentPermissionsResponse(
        agent_id=agent_id,
        agent_name=card.name,
        scopes=scopes,
        tool_scope_map=tool_scope_map,
        permissions=permissions,
        per_tool_permissions=per_tool_permissions,
        tool_overrides=tool_overrides,
        tool_descriptions=tool_descriptions,
        security_flags=orch.security_flags.get(agent_id, {}),
    )


# ── Feature 013: User Tool-Selection Preference ──────────────────────────
# Per-user, per-agent in-chat tool-picker selection. Persisted as a JSON
# value under user_preferences.tool_selection.<agent_id>. The orchestrator
# narrows the LLM's tool list to this subset on each chat dispatch.

user_router = APIRouter(prefix="/api/users/me", tags=["User"])


@user_router.get(
    "/tool-selection",
    response_model=ToolSelectionResponse,
    summary="Get the current user's saved tool selection for an agent",
    description=(
        "Feature 013 / FR-024: returns the in-chat tool-picker subset the "
        "user previously saved for the given agent. `selected_tools=null` "
        "means no narrowing — orchestrator falls back to the full "
        "permission-allowed set."
    ),
)
async def get_user_tool_selection(
    request: Request,
    agent_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    if agent_id not in orch.agent_cards:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    selected = orch.history.db.get_user_tool_selection(user_id, agent_id)
    return ToolSelectionResponse(agent_id=agent_id, selected_tools=selected)


@user_router.put(
    "/tool-selection",
    response_model=ToolSelectionResponse,
    summary="Save the current user's tool selection for an agent",
    description=(
        "Feature 013 / FR-024. Empty arrays are rejected (FR-021 — UI gate). "
        "The list MUST be a strict subset of the agent's permission-allowed "
        "tools; tools blocked by scope/per-tool permissions are rejected."
    ),
)
async def set_user_tool_selection(
    request: Request,
    body: ToolSelectionUpdate,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    card = orch.agent_cards.get(body.agent_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Agent '{body.agent_id}' not found")
    # FR-021 defensive check — UI blocks send when zero, but a stray
    # empty PUT still must be rejected.
    if not body.selected_tools:
        raise HTTPException(
            status_code=400, detail="empty_selection_not_allowed"
        )
    agent_tool_ids = {s.id for s in card.skills}
    invalid = [t for t in body.selected_tools if t not in agent_tool_ids]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Tools not part of agent '{body.agent_id}': {invalid}",
        )
    blocked = [
        t for t in body.selected_tools
        if not orch.tool_permissions.is_tool_allowed(user_id, body.agent_id, t)
    ]
    if blocked:
        raise HTTPException(
            status_code=400,
            detail=f"Tools blocked by scope/per-tool permissions: {blocked}",
        )
    orch.history.db.set_user_tool_selection(user_id, body.agent_id, body.selected_tools)
    logger.info(
        "Tool selection updated: user=%s agent=%s tools=%d action=set",
        user_id,
        body.agent_id,
        len(body.selected_tools),
    )
    return ToolSelectionResponse(
        agent_id=body.agent_id,
        selected_tools=body.selected_tools,
    )


@user_router.delete(
    "/tool-selection",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset the current user's tool selection for an agent",
    description=(
        "Feature 013 / FR-025: clears the saved selection so subsequent "
        "queries fall back to the agent's full permission-allowed set."
    ),
)
async def clear_user_tool_selection(
    request: Request,
    agent_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    if agent_id not in orch.agent_cards:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    cleared = orch.history.db.clear_user_tool_selection(user_id, agent_id)
    logger.info(
        "Tool selection updated: user=%s agent=%s action=reset cleared=%s",
        user_id,
        agent_id,
        cleared,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@user_router.put(
    "/agent-enabled",
    response_model=AgentEnabledResponse,
    summary="Toggle the user's per-agent disabled state",
    description=(
        "Feature 013 follow-up: per-user, agent-wide on/off switch. "
        "Disabling an agent removes it from the orchestrator's chat "
        "dispatch for THIS user only — scopes/per-tool permissions "
        "are NOT modified, so re-enabling resumes the prior state. "
        "Other users are unaffected."
    ),
)
async def set_user_agent_enabled(
    request: Request,
    body: AgentEnabledUpdate,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    if body.agent_id not in orch.agent_cards:
        raise HTTPException(status_code=404, detail=f"Agent '{body.agent_id}' not found")
    orch.history.db.set_user_agent_disabled(user_id, body.agent_id, not body.enabled)
    logger.info(
        "Agent enabled state updated: user=%s agent=%s enabled=%s",
        user_id,
        body.agent_id,
        body.enabled,
    )
    return AgentEnabledResponse(agent_id=body.agent_id, enabled=body.enabled)


# ── Agent Visibility ──────────────────────────────────────────────────


@agent_router.put(
    "/{agent_id}/visibility",
    summary="Toggle agent public/private visibility",
    description="Set whether an agent is publicly available or private. Only the agent owner can change visibility.",
)
async def set_agent_visibility(
    request: Request,
    agent_id: str,
    body: AgentVisibilityRequest,
    payload: dict = Depends(get_current_user_payload),
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    db = orch.history.db
    ownership = db.get_agent_ownership(agent_id)
    if not ownership:
        raise HTTPException(status_code=404, detail=f"No ownership record for agent '{agent_id}'")
    # Only the owner can change visibility
    user_email = payload.get("email", "")
    if ownership["owner_email"] != user_email:
        raise HTTPException(status_code=403, detail="Only the agent owner can change visibility")
    db.set_agent_visibility(agent_id, body.is_public)
    return {"agent_id": agent_id, "is_public": body.is_public}


# ── Agent Credentials ──────────────────────────────────────────────────


@agent_router.get(
    "/{agent_id}/credentials",
    response_model=CredentialListResponse,
    summary="List stored credential keys for an agent",
    description="Returns the names of stored credentials (never the values) and the agent's declared credential requirements.",
)
async def get_agent_credentials(
    request: Request,
    agent_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    card = orch.agent_cards.get(agent_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    keys = orch.credential_manager.list_credential_keys(user_id, agent_id)
    required = getattr(card, 'metadata', {}).get("required_credentials", []) if hasattr(card, 'metadata') else []
    return CredentialListResponse(
        agent_id=agent_id,
        agent_name=card.name,
        credential_keys=keys,
        required_credentials=required,
    )


@agent_router.put(
    "/{agent_id}/credentials",
    response_model=CredentialListResponse,
    summary="Set credentials for an agent",
    description="Store one or more encrypted credentials for the specified agent. Values are encrypted at rest.",
)
async def set_agent_credentials(
    request: Request,
    agent_id: str,
    body: CredentialSetRequest,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    card = orch.agent_cards.get(agent_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    orch.credential_manager.set_bulk_credentials(user_id, agent_id, body.credentials)
    keys = orch.credential_manager.list_credential_keys(user_id, agent_id)
    required = getattr(card, 'metadata', {}).get("required_credentials", []) if hasattr(card, 'metadata') else []
    response = CredentialListResponse(
        agent_id=agent_id,
        agent_name=card.name,
        credential_keys=keys,
        required_credentials=required,
    )

    # Save-time credential probe (FR-008): if the agent exposes a
    # `_credentials_check` tool, invoke it immediately so the user gets a
    # success/auth-failed/unreachable verdict back in the same response.
    skill_names = {getattr(s, "name", None) for s in getattr(card, "skills", [])}
    if "_credentials_check" in skill_names:
        try:
            creds = orch.credential_manager.get_agent_credentials_encrypted(user_id, agent_id)
            args: Dict[str, Any] = {}
            if creds:
                args["_credentials"] = creds
                args["_credentials_encrypted"] = True
            mcp_resp = await orch._dispatch_tool_call(
                agent_id=agent_id,
                tool_name="_credentials_check",
                args=args,
                timeout=5.0,
                ui_websocket=None,
            )
            verdict = "unreachable"
            detail = None
            if mcp_resp is None:
                verdict, detail = "unreachable", "no response from agent"
            elif mcp_resp.error:
                verdict, detail = "unreachable", mcp_resp.error.get("message")
            elif isinstance(mcp_resp.result, dict):
                verdict = mcp_resp.result.get("credential_test", "unexpected")
                detail = mcp_resp.result.get("detail")
            response.credential_test = verdict
            response.credential_test_detail = detail
        except Exception as e:
            # A failed probe must not block the credential save; surface it as unreachable.
            response.credential_test = "unreachable"
            response.credential_test_detail = f"Credential probe failed: {e}"

    return response


@agent_router.delete(
    "/{agent_id}/credentials/{credential_key}",
    response_model=CredentialDeleteResponse,
    summary="Delete a credential",
    description="Remove a single stored credential for the specified agent.",
)
async def delete_agent_credential(
    request: Request,
    agent_id: str,
    credential_key: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    card = orch.agent_cards.get(agent_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    orch.credential_manager.delete_credential(user_id, agent_id, credential_key)
    return CredentialDeleteResponse(message=f"Credential '{credential_key}' deleted for agent '{agent_id}'")


# ── LinkedIn OAuth Flow ──────────────────────────────────────────────────

def _get_public_base_url(request: Request) -> str:
    """Determine the public-facing base URL, respecting reverse proxy headers."""
    # Check for explicit env var override first
    override = os.environ.get("PUBLIC_BASE_URL")
    if override:
        return override.rstrip("/")

    # Check X-Forwarded-* headers (set by reverse proxies like nginx)
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")

    if forwarded_host:
        scheme = forwarded_proto or request.url.scheme
        return f"{scheme}://{forwarded_host}"

    # Fallback to request base URL
    return str(request.base_url).rstrip("/")


@agent_router.get(
    "/{agent_id}/oauth/authorize",
    summary="Start OAuth authorization flow",
    description="Returns the OAuth authorization URL. The frontend opens this in a popup/tab for user consent.",
)
async def oauth_authorize(
    request: Request,
    agent_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    card = orch.agent_cards.get(agent_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    # Get stored client credentials
    client_id = orch.credential_manager.get_credential(user_id, agent_id, "LINKEDIN_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=400, detail="LINKEDIN_CLIENT_ID not configured. Save it in credentials first.")

    # Build the redirect URI using the public-facing URL
    base_url = _get_public_base_url(request)
    redirect_uri = f"{base_url}/api/agents/{agent_id}/oauth/callback"

    # State encodes user_id for the callback
    import secrets
    import json as _json
    state_token = secrets.token_urlsafe(16)
    state_data = _json.dumps({"user_id": user_id, "agent_id": agent_id, "nonce": state_token})

    # Store state temporarily for validation
    orch.credential_manager.set_credential(user_id, agent_id, "_oauth_state", state_data, e2e=False)

    from agents.linkedin.linkedin_api import build_authorization_url
    auth_url = build_authorization_url(client_id, redirect_uri, state=state_data)

    return {"authorization_url": auth_url, "redirect_uri": redirect_uri}


@agent_router.get(
    "/{agent_id}/oauth/callback",
    response_class=HTMLResponse,
    summary="OAuth callback handler",
    description="Handles the redirect from LinkedIn after user consent. Exchanges the auth code for tokens.",
)
async def oauth_callback(
    request: Request,
    agent_id: str,
    code: str = Query(default=None),
    state: str = Query(default=None),
    error: str = Query(default=None),
    error_description: str = Query(default=None),
):
    # Error from LinkedIn
    if error:
        return HTMLResponse(
            content=_oauth_result_page(False, f"LinkedIn authorization failed: {error_description or error}"),
            status_code=200,
        )

    if not code:
        return HTMLResponse(
            content=_oauth_result_page(False, "No authorization code received from LinkedIn."),
            status_code=200,
        )

    # Parse state to find user_id
    import json as _json
    try:
        state_data = _json.loads(state) if state else {}
    except (ValueError, TypeError):
        state_data = {}

    user_id = state_data.get("user_id")
    if not user_id:
        return HTMLResponse(
            content=_oauth_result_page(False, "Invalid OAuth state — missing user context."),
            status_code=200,
        )

    orch = _get_orchestrator(request)

    # Get client credentials
    client_id = orch.credential_manager.get_credential(user_id, agent_id, "LINKEDIN_CLIENT_ID")
    client_secret = orch.credential_manager.get_credential(user_id, agent_id, "LINKEDIN_CLIENT_SECRET")
    if not client_id or not client_secret:
        return HTMLResponse(
            content=_oauth_result_page(False, "Client ID or Secret not found in stored credentials."),
            status_code=200,
        )

    # Build redirect_uri (must match what was sent in the authorize request)
    base_url = _get_public_base_url(request)
    redirect_uri = f"{base_url}/api/agents/{agent_id}/oauth/callback"

    # Exchange code for token
    from agents.linkedin.linkedin_api import exchange_code_for_token
    import time as _time

    token_data = exchange_code_for_token(client_id, client_secret, code, redirect_uri)
    if not token_data or "access_token" not in token_data:
        return HTMLResponse(
            content=_oauth_result_page(False, "Failed to exchange authorization code for access token."),
            status_code=200,
        )

    # Store the token(s) as credentials
    creds_to_store = {
        "LINKEDIN_ACCESS_TOKEN": token_data["access_token"],
    }
    expires_in = token_data.get("expires_in")
    if expires_in:
        creds_to_store["LINKEDIN_TOKEN_EXPIRES_AT"] = str(int(_time.time()) + int(expires_in))
    if token_data.get("refresh_token"):
        creds_to_store["LINKEDIN_REFRESH_TOKEN"] = token_data["refresh_token"]

    orch.credential_manager.set_bulk_credentials(user_id, agent_id, creds_to_store, e2e=False)

    # Fetch and store LinkedIn profile name for display purposes
    try:
        import requests as _requests
        profile_resp = _requests.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
            timeout=10,
        )
        if profile_resp.ok:
            profile = profile_resp.json()
            profile_meta = {}
            if profile.get("name"):
                profile_meta["LINKEDIN_PROFILE_NAME"] = profile["name"]
            if profile.get("email"):
                profile_meta["LINKEDIN_PROFILE_EMAIL"] = profile["email"]
            if profile.get("sub"):
                profile_meta["LINKEDIN_PROFILE_ID"] = profile["sub"]
            if profile_meta:
                orch.credential_manager.set_bulk_credentials(user_id, agent_id, profile_meta, e2e=False)
                logger.info(f"Stored LinkedIn profile info: {profile.get('name')}")
    except Exception as e:
        logger.warning(f"Failed to fetch LinkedIn profile after OAuth: {e}")

    # Clean up state
    orch.credential_manager.delete_credential(user_id, agent_id, "_oauth_state")

    logger.info(f"LinkedIn OAuth complete for user={user_id} agent={agent_id}, token expires_in={expires_in}")

    return HTMLResponse(
        content=_oauth_result_page(True, "LinkedIn authorization successful! You can close this window."),
        status_code=200,
    )


@agent_router.get(
    "/{agent_id}/oauth/status",
    summary="Check OAuth connection status",
    description="Returns whether the agent has a valid OAuth token and the connected profile info.",
)
async def oauth_status(
    request: Request,
    agent_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    cm = orch.credential_manager

    access_token = cm.get_credential(user_id, agent_id, "LINKEDIN_ACCESS_TOKEN")
    if not access_token:
        return {"connected": False}

    import time as _time
    expires_at_str = cm.get_credential(user_id, agent_id, "LINKEDIN_TOKEN_EXPIRES_AT")
    expired = False
    expires_at = None
    if expires_at_str:
        try:
            expires_at = float(expires_at_str)
            expired = _time.time() > expires_at
        except (ValueError, TypeError):
            pass

    profile_name = cm.get_credential(user_id, agent_id, "LINKEDIN_PROFILE_NAME")
    profile_email = cm.get_credential(user_id, agent_id, "LINKEDIN_PROFILE_EMAIL")

    return {
        "connected": True,
        "expired": expired,
        "profile_name": profile_name,
        "profile_email": profile_email,
        "expires_at": expires_at,
    }


def _oauth_result_page(success: bool, message: str) -> str:
    """Generate a simple HTML page for the OAuth callback result."""
    color = "#22c55e" if success else "#ef4444"
    icon = "&#10003;" if success else "&#10007;"
    return f"""<!DOCTYPE html>
<html><head><title>LinkedIn Authorization</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; background: #0f1219; color: #e2e8f0;
       display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
.card {{ background: #1a1f2e; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px;
         padding: 2rem; text-align: center; max-width: 400px; }}
.icon {{ font-size: 3rem; color: {color}; margin-bottom: 1rem; }}
p {{ font-size: 0.9rem; opacity: 0.8; }}
</style></head>
<body><div class="card">
<div class="icon">{icon}</div>
<h2>{message}</h2>
<p>This window will close automatically.</p>
</div>
<script>
// Notify the parent window and close after a delay
if (window.opener) {{
    window.opener.postMessage({{ type: "linkedin_oauth_complete", success: {"true" if success else "false"} }}, "*");
}}
setTimeout(() => window.close(), 2000);
</script>
</body></html>"""


# =============================================================================
# Draft Agent Router
# =============================================================================

draft_router = APIRouter(prefix="/api/agents/drafts", tags=["Draft Agents"])


def _get_lifecycle(request: Request):
    """Retrieve the AgentLifecycleManager from app state."""
    orch = _get_orchestrator(request)
    lifecycle = getattr(orch, 'lifecycle_manager', None)
    if lifecycle is None:
        raise HTTPException(status_code=503, detail="Agent lifecycle manager not initialized")
    return lifecycle


def _find_user_websocket(orch, user_id: str):
    """Find the WebSocket connection for a given user_id (for progress updates)."""
    for ws, session in orch.ui_sessions.items():
        if session.get("user_id") == user_id:
            return ws
    return None


def _parse_json_field(value):
    """Parse a JSON string field, returning None if empty/null."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return __import__('json').loads(value)
        except (ValueError, TypeError):
            return value
    return value


def _backfill_validation_tools(validation_report: dict, slug: str, orch) -> dict:
    """Backfill 'tools' into a validation report from the orchestrator's agent cards."""
    if not validation_report or validation_report.get("tools"):
        return validation_report  # already has tools or no report
    agent_id = f"{slug.replace('_', '-')}-1"
    card = orch.agent_cards.get(agent_id) if orch else None
    if not card:
        return validation_report
    tools = []
    for skill in card.skills:
        schema = skill.input_schema or {}
        props = schema.get("properties", {})
        required = schema.get("required", []) if isinstance(schema.get("required"), list) else []
        params = []
        for pname, pinfo in props.items():
            if isinstance(pinfo, dict):
                params.append({
                    "name": pname,
                    "type": pinfo.get("type", "any"),
                    "description": pinfo.get("description", ""),
                    "required": pname in required,
                })
        tools.append({
            "name": skill.id,
            "description": skill.description or "",
            "scope": getattr(skill, "scope", "tools:read") or "tools:read",
            "parameters": params,
        })
    validation_report["tools"] = tools
    return validation_report


def _draft_to_response(draft: dict, orch=None) -> DraftAgentResponse:
    """Convert a raw draft dict to a DraftAgentResponse with parsed JSON fields."""
    validation_report = _parse_json_field(draft.get("validation_report"))
    if validation_report and orch:
        validation_report = _backfill_validation_tools(
            validation_report, draft["agent_slug"], orch
        )
    return DraftAgentResponse(
        id=draft["id"],
        user_id=draft["user_id"],
        agent_name=draft["agent_name"],
        agent_slug=draft["agent_slug"],
        description=draft["description"],
        tools_spec=_parse_json_field(draft.get("tools_spec")),
        skill_tags=_parse_json_field(draft.get("skill_tags")),
        packages=_parse_json_field(draft.get("packages")),
        status=draft["status"],
        generation_log=_parse_json_field(draft.get("generation_log")),
        security_report=_parse_json_field(draft.get("security_report")),
        validation_report=validation_report,
        error_message=draft.get("error_message"),
        port=draft.get("port"),
        review_notes=draft.get("review_notes"),
        reviewed_by=draft.get("reviewed_by"),
        refinement_history=_parse_json_field(draft.get("refinement_history")),
        required_credentials=_parse_json_field(draft.get("required_credentials")),
        created_at=draft.get("created_at"),
        updated_at=draft.get("updated_at"),
    )


@draft_router.get(
    "",
    response_model=DraftAgentListResponse,
    summary="List draft agents",
    description="Returns all draft agents belonging to the current user.",
)
async def list_drafts(
    request: Request,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    drafts = orch.history.db.get_user_draft_agents(user_id)
    return DraftAgentListResponse(
        drafts=[_draft_to_response(d, orch) for d in drafts]
    )


@draft_router.post(
    "",
    response_model=DraftAgentResponse,
    summary="Create a draft agent",
    description="Creates a new draft agent with the given specification. Does not generate code yet.",
)
async def create_draft(
    request: Request,
    body: DraftAgentCreateRequest,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    lifecycle = _get_lifecycle(request)
    try:
        draft = await lifecycle.create_draft(
            user_id=user_id,
            agent_name=body.agent_name,
            description=body.description,
            tools_spec=[t.model_dump() for t in body.tools] if body.tools else None,
            skill_tags=body.skill_tags,
            packages=body.packages,
        )
        return _draft_to_response(draft, orch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@draft_router.get(
    "/pending-review",
    response_model=DraftAgentListResponse,
    summary="List drafts pending admin review",
    description="Admin endpoint: returns all draft agents awaiting review.",
)
async def list_pending_review(
    request: Request,
    user_id: str = Depends(require_user_id),
    payload: dict = Depends(get_current_user_payload),
):
    roles = payload.get("roles", []) if payload else []
    if "admin" not in roles:
        raise HTTPException(status_code=403, detail="Admin role required")

    orch = _get_orchestrator(request)
    drafts = orch.history.db.get_pending_review_drafts()
    return DraftAgentListResponse(
        drafts=[_draft_to_response(d, orch) for d in drafts]
    )


@draft_router.get(
    "/{draft_id}",
    response_model=DraftAgentResponse,
    summary="Get draft agent details",
)
async def get_draft(
    request: Request,
    draft_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    draft = orch.history.db.get_draft_agent(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft agent not found")
    if draft["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your draft agent")
    return _draft_to_response(draft, orch)


@draft_router.delete(
    "/{draft_id}",
    response_model=DeleteResponse,
    summary="Delete a draft agent",
    description="Stops the agent process, removes files, and deletes the record.",
)
async def delete_draft(
    request: Request,
    draft_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    draft = orch.history.db.get_draft_agent(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft agent not found")
    if draft["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your draft agent")

    lifecycle = _get_lifecycle(request)
    deleted = await lifecycle.delete_draft(draft_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete draft agent")
    return DeleteResponse(message="Draft agent deleted successfully")


@draft_router.post(
    "/{draft_id}/generate",
    response_model=DraftAgentResponse,
    summary="Generate agent code",
    description="Triggers LLM code generation for the draft agent. Progress updates are sent via WebSocket.",
)
async def generate_draft(
    request: Request,
    draft_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    draft = orch.history.db.get_draft_agent(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft agent not found")
    if draft["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your draft agent")

    lifecycle = _get_lifecycle(request)
    # Find user's WebSocket for progress updates
    ws = _find_user_websocket(orch, user_id)
    result = await lifecycle.generate_code(draft_id, websocket=ws)
    return _draft_to_response(result, orch)


@draft_router.post(
    "/{draft_id}/refine",
    response_model=DraftAgentResponse,
    summary="Refine agent via chat",
    description="Refines the agent's tool implementations based on a natural language message.",
)
async def refine_draft(
    request: Request,
    draft_id: str,
    body: DraftAgentRefineRequest,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    draft = orch.history.db.get_draft_agent(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft agent not found")
    if draft["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your draft agent")

    lifecycle = _get_lifecycle(request)
    ws = _find_user_websocket(orch, user_id)
    result = await lifecycle.refine_agent(draft_id, body.message, websocket=ws)
    return _draft_to_response(result, orch)


@draft_router.post(
    "/{draft_id}/test",
    response_model=DraftAgentResponse,
    summary="Start draft agent for testing",
    description="Launches the draft agent subprocess. The orchestrator will auto-discover it.",
)
async def test_draft(
    request: Request,
    draft_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    draft = orch.history.db.get_draft_agent(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft agent not found")
    if draft["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your draft agent")

    lifecycle = _get_lifecycle(request)
    ws = _find_user_websocket(orch, user_id)
    try:
        result = await lifecycle.start_draft_agent(draft_id, websocket=ws)
        return _draft_to_response(result, orch)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@draft_router.post(
    "/{draft_id}/stop",
    response_model=DraftAgentResponse,
    summary="Stop testing draft agent",
)
async def stop_draft(
    request: Request,
    draft_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    draft = orch.history.db.get_draft_agent(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft agent not found")
    if draft["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your draft agent")

    lifecycle = _get_lifecycle(request)
    await lifecycle.stop_draft_agent(draft_id)
    orch.history.db.update_draft_agent(draft_id, status="generated")
    updated = orch.history.db.get_draft_agent(draft_id)
    return _draft_to_response(updated, orch)


@draft_router.post(
    "/{draft_id}/approve",
    response_model=DraftAgentResponse,
    summary="Approve draft agent",
    description="Runs comprehensive security analysis. Auto-approves if clean, sends to admin review if high-severity findings.",
)
async def approve_draft(
    request: Request,
    draft_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    draft = orch.history.db.get_draft_agent(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft agent not found")
    if draft["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your draft agent")

    lifecycle = _get_lifecycle(request)
    ws = _find_user_websocket(orch, user_id)
    result = await lifecycle.approve_agent(draft_id, websocket=ws)
    return _draft_to_response(result, orch)


@draft_router.post(
    "/{draft_id}/review",
    response_model=DraftAgentResponse,
    summary="Admin review: approve or reject",
    description="Admin endpoint to approve or reject a draft agent pending review.",
)
async def admin_review(
    request: Request,
    draft_id: str,
    body: AdminReviewRequest,
    user_id: str = Depends(require_user_id),
    payload: dict = Depends(get_current_user_payload),
):
    roles = payload.get("roles", []) if payload else []
    if "admin" not in roles:
        raise HTTPException(status_code=403, detail="Admin role required")

    lifecycle = _get_lifecycle(request)
    ws = None  # Could look up draft owner's WS for notification
    try:
        result = await lifecycle.admin_review(
            draft_id, body.decision, admin_user_id=user_id,
            notes=body.notes, websocket=ws
        )
        return _draft_to_response(result, orch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Draft Agent Credentials ─────────────────────────────────────────────────

@draft_router.get(
    "/{draft_id}/credentials",
    summary="Get credential status for a draft agent",
    description="Returns required credentials and which ones the user has already stored.",
)
async def get_draft_credentials(
    request: Request,
    draft_id: str,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    draft = orch.history.db.get_draft_agent(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft agent not found")
    if draft["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your draft agent")

    agent_id = f"{draft['agent_slug'].replace('_', '-')}-1"
    stored_keys = orch.credential_manager.list_credential_keys(user_id, agent_id)
    required = json.loads(draft.get("required_credentials") or "[]")

    return {
        "draft_id": draft_id,
        "agent_id": agent_id,
        "required_credentials": required,
        "stored_credential_keys": stored_keys,
    }


@draft_router.put(
    "/{draft_id}/credentials",
    summary="Set credentials for a draft agent",
    description="Store encrypted credentials for a draft agent before testing.",
)
async def set_draft_credentials(
    request: Request,
    draft_id: str,
    body: CredentialSetRequest,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    draft = orch.history.db.get_draft_agent(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft agent not found")
    if draft["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your draft agent")

    agent_id = f"{draft['agent_slug'].replace('_', '-')}-1"
    orch.credential_manager.set_bulk_credentials(user_id, agent_id, body.credentials)
    stored_keys = orch.credential_manager.list_credential_keys(user_id, agent_id)
    required = json.loads(draft.get("required_credentials") or "[]")

    return {
        "draft_id": draft_id,
        "agent_id": agent_id,
        "required_credentials": required,
        "stored_credential_keys": stored_keys,
    }


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
async def get_dashboard(
    request: Request,
    user_id: str = Depends(require_user_id),
):
    orch = _get_orchestrator(request)
    agents = []
    total_tools = 0
    for agent_id, card in orch.agent_cards.items():
        available_tools = [s.id for s in card.skills]
        permissions = orch.tool_permissions.get_effective_permissions(
            user_id, agent_id, available_tools
        )
        total_tools += sum(1 for v in permissions.values() if v)
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
        total_tools=total_tools,
    )


# =============================================================================
# Voice Router  (STT / TTS proxy to Speaches.ai)
# =============================================================================

voice_router = APIRouter(prefix="/api/voice", tags=["Voice"])


@voice_router.post("/transcribe", summary="Speech-to-text via Speaches.ai")
async def transcribe_audio(
    file: UploadFile = File(...),
    user_id: str = Depends(require_user_id),
):
    """Accept an audio file, forward it to the Speaches STT endpoint, return transcribed text."""
    speaches_url = os.getenv("SPEACHES_URL")
    if not speaches_url:
        raise HTTPException(status_code=503, detail="SPEACHES_URL not configured")

    stt_model = os.getenv("SPEACHES_STT_MODEL", "Systran/faster-whisper-large-v3")
    audio_bytes = await file.read()

    try:
        form = aiohttp.FormData()
        form.add_field("file", audio_bytes, filename=file.filename or "audio.webm", content_type=file.content_type or "audio/webm")
        form.add_field("model", stt_model)

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{speaches_url}/v1/audio/transcriptions", data=form) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"Speaches STT error {resp.status}: {body}")
                    raise HTTPException(status_code=502, detail=f"Speaches STT error: {body}")
                result = await resp.json()
                return JSONResponse(content=result)
    except aiohttp.ClientError as e:
        logger.error(f"Speaches STT connection error: {e}")
        raise HTTPException(status_code=502, detail=f"Cannot reach Speaches server: {e}")


def _truncate_for_speech(text: str, max_chars: int = 300) -> str:
    """Truncate text at a sentence boundary for natural-sounding TTS."""
    if len(text) <= max_chars:
        return text
    # Find the last sentence-ending punctuation within the limit
    truncated = text[:max_chars]
    for end in (". ", "! ", "? "):
        idx = truncated.rfind(end)
        if idx > 50:  # ensure at least some content
            return truncated[: idx + 1]
    # Fallback: cut at last space
    idx = truncated.rfind(" ")
    return (truncated[:idx] if idx > 50 else truncated) + "."


@voice_router.post("/speak", summary="Text-to-speech via Speaches.ai")
async def text_to_speech(
    request: Request,
    user_id: str = Depends(require_user_id),
):
    """Accept text, truncate for brevity, stream audio from Speaches TTS."""
    from fastapi.responses import StreamingResponse

    speaches_url = os.getenv("SPEACHES_URL")
    if not speaches_url:
        raise HTTPException(status_code=503, detail="SPEACHES_URL not configured")

    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")

    voice = body.get("voice", "af_heart")
    tts_model = os.getenv("SPEACHES_TTS_MODEL", "speaches-ai/Kokoro-82M-v1.0-ONNX-int8")

    # Fast truncation instead of slow LLM summarization
    text = _truncate_for_speech(text)
    logger.info(f"TTS request: {len(text)} chars, model={tts_model}")

    try:
        payload = {"model": tts_model, "input": text, "voice": voice}
        session = aiohttp.ClientSession()
        resp = await session.post(f"{speaches_url}/v1/audio/speech", json=payload)

        if resp.status != 200:
            err = await resp.text()
            await resp.release()
            await session.close()
            logger.error(f"Speaches TTS error {resp.status}: {err}")
            raise HTTPException(status_code=502, detail=f"Speaches TTS error: {err}")

        content_type = resp.headers.get("Content-Type", "audio/mpeg")

        async def stream_audio():
            try:
                async for chunk in resp.content.iter_chunked(4096):
                    yield chunk
            finally:
                await resp.release()
                await session.close()

        return StreamingResponse(stream_audio(), media_type=content_type)
    except aiohttp.ClientError as e:
        logger.error(f"Speaches TTS connection error: {e}")
        raise HTTPException(status_code=502, detail=f"Cannot reach Speaches server: {e}")


@voice_router.websocket("/stream")
async def voice_stream(ws: WebSocket):
    """
    Real-time voice streaming proxy to Speaches Realtime API.

    Protocol (frontend -> this endpoint):
    - Frontend sends binary audio frames (PCM16 16kHz mono)
    - This proxy base64-encodes them and forwards as OpenAI Realtime
      `input_audio_buffer.append` events to Speaches.
    - Transcription events from Speaches are forwarded back as JSON.

    Frontend should listen for:
    - {"type": "transcription.delta", "text": "partial..."}
    - {"type": "transcription.done", "text": "final transcription"}
    - {"type": "speech.started"}
    - {"type": "speech.stopped"}
    - {"type": "error", "message": "..."}
    """
    await ws.accept()

    speaches_url = os.getenv("SPEACHES_URL", "").strip()
    if not speaches_url:
        await ws.send_json({"type": "error", "message": "Speech server not configured"})
        await ws.close()
        return

    stt_model = os.getenv("SPEACHES_STT_MODEL", "Systran/faster-whisper-large-v3")

    # Build the Speaches Realtime WebSocket URL
    scheme = "wss" if speaches_url.startswith("https") else "ws"
    host = speaches_url.replace("https://", "").replace("http://", "")
    realtime_url = f"{scheme}://{host}/v1/realtime?model={stt_model}&intent=transcription"

    speaches_ws = None
    try:
        speaches_ws = await ws_client.connect(realtime_url)
        logger.info(f"Voice stream: connected to Speaches Realtime at {realtime_url}")

        async def forward_speaches_to_client():
            """Read events from Speaches and forward simplified events to the frontend."""
            try:
                async for message in speaches_ws:
                    try:
                        event = json.loads(message)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    event_type = event.get("type", "")
                    logger.debug(f"Voice stream: Speaches event: {event_type}")

                    if event_type == "input_audio_buffer.speech_started":
                        await ws.send_json({"type": "speech.started"})

                    elif event_type == "input_audio_buffer.speech_stopped":
                        await ws.send_json({"type": "speech.stopped"})

                    elif event_type == "conversation.item.input_audio_transcription.completed":
                        transcript = event.get("transcript", "")
                        await ws.send_json({"type": "transcription.done", "text": transcript})

                    elif "transcription" in event_type and "delta" in event_type:
                        delta = event.get("delta", "")
                        if delta:
                            await ws.send_json({"type": "transcription.delta", "text": delta})

                    elif event_type == "error":
                        err_msg = event.get("error", {}).get("message", "Unknown error")
                        err_type = event.get("error", {}).get("type", "")
                        # Speaches returns "Not Found" when no speech is detected
                        # in the committed audio — translate to a clean "no speech" event
                        if err_msg == "Not Found" or (err_type == "invalid_request_error" and "not found" in err_msg.lower()):
                            await ws.send_json({"type": "transcription.done", "text": ""})
                        else:
                            await ws.send_json({"type": "error", "message": err_msg})

            except (ws_client.exceptions.ConnectionClosed, Exception) as e:
                logger.debug(f"Voice stream: Speaches connection closed: {e}")

        # Start the Speaches -> client forwarding task
        forward_task = asyncio.create_task(forward_speaches_to_client())

        # Read binary audio from the frontend and forward to Speaches
        try:
            while True:
                data = await ws.receive()

                if data["type"] == "websocket.disconnect":
                    break

                logger.debug(f"Voice stream: received frame type={data.get('type')}, has_bytes={'bytes' in data and bool(data.get('bytes'))}, has_text={'text' in data and bool(data.get('text'))}")
                if "bytes" in data and data["bytes"]:
                    # Frontend sends raw audio bytes -> encode to base64 for OpenAI Realtime protocol
                    audio_b64 = base64.b64encode(data["bytes"]).decode("ascii")
                    await speaches_ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": audio_b64,
                    }))
                elif "text" in data and data["text"]:
                    # Frontend may send JSON control messages
                    try:
                        ctrl = json.loads(data["text"])
                        ctrl_type = ctrl.get("type", "")
                        if ctrl_type == "stop":
                            # Commit the audio buffer to trigger final transcription
                            await speaches_ws.send(json.dumps({
                                "type": "input_audio_buffer.commit",
                            }))
                    except json.JSONDecodeError:
                        pass

        except WebSocketDisconnect:
            logger.debug("Voice stream: frontend disconnected")
        finally:
            forward_task.cancel()
            try:
                await forward_task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.error(f"Voice stream: failed to connect to Speaches Realtime: {e}")
        try:
            await ws.send_json({"type": "error", "message": f"Cannot connect to speech server: {e}"})
        except Exception:
            pass
    finally:
        if speaches_ws:
            try:
                await speaches_ws.close()
            except Exception:
                pass
        try:
            await ws.close()
        except Exception:
            pass


# =============================================================================
# Task Router — Re-Act task state inspection
# =============================================================================

task_router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


@task_router.get(
    "/{chat_id}",
    summary="Get active task state",
    description="Returns the current Re-Act task state for a chat session.",
)
async def get_task_state(chat_id: str, request: Request):
    orch = _get_orchestrator(request)
    task = orch.task_manager.get_active_task(chat_id)
    if task:
        return task.to_dict()
    # No active task — check for most recent completed task
    all_tasks = orch.task_manager.get_chat_tasks(chat_id)
    if all_tasks:
        latest = max(all_tasks, key=lambda t: t.updated_at)
        return latest.to_dict()
    return {"state": "none", "chat_id": chat_id}
