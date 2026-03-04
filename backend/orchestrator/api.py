"""
REST API routes for the AstralBody backend.

Provides HTTP endpoints that mirror the WebSocket actions, enabling
any frontend (PHP, Flutter, other JS frameworks) to interact with
the orchestrator without implementing the WebSocket protocol.

WebSocket remains the primary channel for real-time features (streaming
chat responses, live status updates). These REST endpoints provide
request/response access for CRUD operations.
"""
import os
import time
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse

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
    AgentVisibilityRequest,
    CredentialSetRequest, CredentialListResponse, CredentialDeleteResponse,
    DashboardResponse,
    ErrorResponse,
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
    description="Returns all agents currently connected to the orchestrator, including their tools, capabilities, and ownership info.",
)
async def list_agents(request: Request):
    orch = _get_orchestrator(request)
    db = orch.history.db
    ownership_map = {o["agent_id"]: o for o in db.get_all_agent_ownership()}
    agents = []
    for agent_id, card in orch.agent_cards.items():
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
    available_tools = [s.id for s in card.skills]
    tool_descriptions = {s.id: s.description for s in card.skills}
    scopes = orch.tool_permissions.get_agent_scopes(user_id, agent_id)
    tool_scope_map = orch.tool_permissions.get_tool_scope_map(agent_id)
    permissions = orch.tool_permissions.get_effective_permissions(
        user_id, agent_id, available_tools
    )
    return AgentPermissionsResponse(
        agent_id=agent_id,
        agent_name=card.name,
        scopes=scopes,
        tool_scope_map=tool_scope_map,
        permissions=permissions,
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
    orch.tool_permissions.set_agent_scopes(user_id, agent_id, body.scopes)
    available_tools = [s.id for s in card.skills]
    tool_descriptions = {s.id: s.description for s in card.skills}
    scopes = orch.tool_permissions.get_agent_scopes(user_id, agent_id)
    tool_scope_map = orch.tool_permissions.get_tool_scope_map(agent_id)
    permissions = orch.tool_permissions.get_effective_permissions(
        user_id, agent_id, available_tools
    )
    return AgentPermissionsResponse(
        agent_id=agent_id,
        agent_name=card.name,
        scopes=scopes,
        tool_scope_map=tool_scope_map,
        permissions=permissions,
        tool_descriptions=tool_descriptions,
        security_flags=orch.security_flags.get(agent_id, {}),
    )


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
    return CredentialListResponse(
        agent_id=agent_id,
        agent_name=card.name,
        credential_keys=keys,
        required_credentials=required,
    )


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
    orch.credential_manager.set_credential(user_id, agent_id, "_oauth_state", state_data)

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

    orch.credential_manager.set_bulk_credentials(user_id, agent_id, creds_to_store)

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
                orch.credential_manager.set_bulk_credentials(user_id, agent_id, profile_meta)
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
