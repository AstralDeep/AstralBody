"""
Orchestrator — Central hub for the multi-agent system.

Responsibilities:
1. WebSocket server for UI clients (/ws) and agent connections
2. A2A agent discovery via agent cards
3. LLM-powered tool routing (chat message → tool selection)
4. Parallel MCP tool execution across agents
5. Dynamic UI assembly (combines tool outputs into cohesive layouts)
"""
import asyncio
import json
import time
import os
import sys
import logging
import re
from typing import Dict, List, Optional, Any
from dataclasses import asdict

import websockets
import websockets.exceptions
import aiohttp
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt as jose_jwt
from dotenv import load_dotenv
from openai import OpenAI
from httpx import Timeout

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from orchestrator.history import HistoryManager
from orchestrator.tool_permissions import ToolPermissionManager
from orchestrator.credential_manager import CredentialManager
from orchestrator.delegation import DelegationService
from orchestrator.tool_security import ToolSecurityAnalyzer

from shared.protocol import (
    Message, MCPRequest, MCPResponse, UIEvent, UIRender, UIUpdate,
    RegisterAgent, RegisterUI, AgentCard, AgentSkill
)
from shared.primitives import (
    Container, Text, Card, Grid, Alert, MetricCard, ProgressBar,
    Collapsible, create_ui_response
)
from rote.rote import ROTE

load_dotenv(override=False)

PORT = int(os.getenv("ORCHESTRATOR_PORT", 8001))

debug_mode = os.getenv("DEBUG", "false").lower() == "true"
log_level = logging.INFO if debug_mode else logging.WARNING

logging.basicConfig(level=log_level,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('Orchestrator')


class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Filter out uvicorn access logs for specific "poll" endpoints
        msg = record.getMessage()
        return "/.well-known/agent-card.json" not in msg

# Filter uvicorn access logs if they exist
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())


class Orchestrator:
    def __init__(self):
        self.agents: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.ui_clients: List[websockets.WebSocketServerProtocol] = []
        self.ui_sessions: Dict[websockets.WebSocketServerProtocol, Dict] = {}
        self.agent_cards: Dict[str, AgentCard] = {}
        self.agent_capabilities: Dict[str, List[Dict]] = {}
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.cancelled_sessions: Dict[str, bool] = {}  # websocket id -> cancelled flag
        self._chat_locks: Dict[int, asyncio.Lock] = {}  # per-websocket lock for chat serialization
        self._registered_events: Dict[int, asyncio.Event] = {}  # gate non-register messages until auth completes

        # A2A external agent connections (JSON-RPC transport)
        self.a2a_clients: Dict[str, Any] = {}  # agent_id -> A2A client
        self.a2a_agent_cards: Dict[str, Any] = {}  # agent_id -> official A2A AgentCard
        self.agent_urls: Dict[str, str] = {}  # agent_id -> base URL (for peer registry)

        # LLM Client
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.llm_model = os.getenv("LLM_MODEL", "meta-llama/Llama-3.2-90B-Vision-Instruct")

        if api_key and base_url:
            self.llm_client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=Timeout(180.0, connect=10.0)  # 180s for large models (DeepSeek, etc.)
            )
            logger.info(f"LLM configured: {base_url} model={self.llm_model}")
        else:
            self.llm_client = None
            logger.warning("No LLM configured — tool routing disabled")

        # History Manager
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        data_dir = os.path.join(backend_dir, 'data')
        self.history = HistoryManager(data_dir=data_dir)

        # Tool Permission Manager (RFC 8693 delegation) — backed by same PostgreSQL DB
        self.tool_permissions = ToolPermissionManager(db=self.history.db, data_dir=data_dir)

        # Per-user credential storage (encrypted API keys for agents)
        self.credential_manager = CredentialManager(db=self.history.db, data_dir=data_dir)

        # Delegation Service (RFC 8693 token exchange)
        self.delegation = DelegationService()

        # Tool Security Analyzer — proactive security review of agent tools
        self.security_analyzer = ToolSecurityAnalyzer()
        self.security_flags: Dict[str, Dict[str, Any]] = {}  # agent_id -> {tool_name: flag_dict}

        # LLM Token Usage Tracking — per-conversation accumulation
        self.token_usage: Dict[str, Dict[str, int]] = {}  # chat_id -> {prompt_tokens, completion_tokens, total_tokens}

        # ROTE — Response Output Translation Engine
        self.rote = ROTE()

        # Agent Lifecycle Manager — handles user-created draft agents
        from orchestrator.agent_lifecycle import AgentLifecycleManager
        self.lifecycle_manager = AgentLifecycleManager(db=self.history.db, orchestrator=self)

    # =========================================================================
    # AGENT MANAGEMENT
    # =========================================================================

    async def register_agent(self, websocket, msg: RegisterAgent):
        """Register a specialist agent and store its capabilities."""
        card = msg.agent_card
        if not card:
            logger.warning("RegisterAgent with no card")
            return

        if websocket is not None:
            self.agents[card.agent_id] = websocket
        self.agent_cards[card.agent_id] = card

        # Extract capabilities for routing and tool→scope mapping
        caps = []
        tool_scope_map = {}
        for skill in card.skills:
            caps.append({
                "name": skill.id,
                "description": skill.description,
                "input_schema": skill.input_schema
            })
            # Store tool→scope mapping from agent-declared scopes
            tool_scope_map[skill.id] = getattr(skill, 'scope', '') or 'tools:read'
        self.agent_capabilities[card.agent_id] = caps

        # Register tool→scope mapping in the permission manager
        self.tool_permissions.register_tool_scopes(card.agent_id, tool_scope_map)

        # Extract agent's ECIES public key for E2E credential encryption
        public_key_jwk = getattr(card, 'metadata', {}).get("public_key_jwk") if getattr(card, 'metadata', None) else None
        if public_key_jwk:
            self.credential_manager.register_agent_public_key(card.agent_id, public_key_jwk)
            logger.info(f"Registered ECIES public key for agent '{card.agent_id}'")

        logger.info(f"Agent registered: {card.agent_id} ({card.name}) with {len(caps)} tools")

        # Proactive security review: analyze all tools for threats
        raw_flags = self.security_analyzer.analyze_agent(card)
        if raw_flags:
            self.security_flags[card.agent_id] = {
                name: flag.to_dict() for name, flag in raw_flags.items()
            }
            logger.warning(
                f"Security review flagged {len(raw_flags)} tool(s) for agent "
                f"'{card.agent_id}': {list(raw_flags.keys())}"
            )
        else:
            self.security_flags[card.agent_id] = {}

        # Auto-assign ownership if this agent has no owner yet
        tool_names = [c["name"] for c in caps]
        ownership = self.history.db.get_agent_ownership(card.agent_id)
        if not ownership:
            default_owner = os.environ.get("DEFAULT_AGENT_OWNER", "")
            if default_owner:
                self.history.db.set_agent_ownership(card.agent_id, default_owner, is_public=False)
                ownership = self.history.db.get_agent_ownership(card.agent_id) or {}
                logger.info(f"Auto-assigned agent '{card.agent_id}' to {default_owner}")
            else:
                ownership = {}

        # Don't broadcast draft agents to UI — they only appear in the Drafts tab
        if self._is_draft_agent(card.agent_id):
            return

        # Notify all UI clients (include per-user scopes, tool_scope_map, and security flags)
        for ui in self.ui_clients:
            try:
                user_id = self._get_user_id(ui)
                scopes = self.tool_permissions.get_agent_scopes(user_id, card.agent_id)
                permissions = self.tool_permissions.get_effective_permissions(
                    user_id, card.agent_id, tool_names
                )
                msg = {
                    "type": "agent_registered",
                    "agent_id": card.agent_id,
                    "name": card.name,
                    "description": card.description,
                    "tools": tool_names,
                    "permissions": permissions,
                    "scopes": scopes,
                    "tool_scope_map": tool_scope_map,
                    "security_flags": self.security_flags.get(card.agent_id, {}),
                    "owner_email": ownership.get("owner_email"),
                    "is_public": bool(ownership.get("is_public", False)),
                }
                if getattr(card, 'metadata', None):
                    msg["metadata"] = card.metadata
                await self._safe_send(ui, json.dumps(msg))
            except Exception:
                pass

    async def discover_agent(self, base_url: str):
        """Discover an agent by fetching its A2A agent card and connecting via WebSocket."""
        try:
            # Fetch agent card
            card_url = f"{base_url}/.well-known/agent-card.json"
            async with aiohttp.ClientSession() as session:
                async with session.get(card_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        # Log as INFO during discovery to avoid noise during startup
                        logger.info(f"Agent card not ready yet at {card_url} (status: {resp.status})")
                        return
                    card_data = await resp.json()

            card = AgentCard.from_dict(card_data)
            agent_id = card.agent_id

            if agent_id in self.agents:
                logger.debug(f"Agent {agent_id} already connected")
                return

            # Connect via WebSocket with no size limit to allow large files
            ws_url = f"ws://{base_url.replace('http://', '').replace('https://', '')}/agent"
            ws = await websockets.connect(ws_url, max_size=50 * 1024 * 1024)

            # Listen for RegisterAgent message
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            parsed = Message.from_json(raw)
            if isinstance(parsed, RegisterAgent):
                await self.register_agent(ws, parsed)

            # Store agent URL for peer registry
            self.agent_urls[agent_id] = base_url

            # Start listening loop
            asyncio.create_task(self._agent_listen_loop(ws, agent_id))

            logger.info(f"Connected to agent: {agent_id} at {base_url}")

        except Exception as e:
            logger.debug(f"Discovery attempt to {base_url} skipped: {e}")

    async def discover_a2a_agent(self, base_url: str, notify_ui: bool = True):
        """Discover an external agent — tries WebSocket first, falls back to A2A JSON-RPC.

        Strategy:
        1. Try to connect via WebSocket (fastest, bidirectional, preferred)
        2. If WebSocket fails, fall back to official A2A protocol (JSON-RPC)
        """
        # Step 1: Try WebSocket first
        try:
            await self.discover_agent(base_url)
            # Check if WebSocket discovery succeeded
            for aid, url in self.agent_urls.items():
                if url == base_url and aid in self.agents:
                    logger.info(f"External agent at {base_url} connected via WebSocket (preferred)")
                    # Also set up A2A client as backup
                    await self._setup_a2a_client_for_agent(base_url, aid)
                    return
        except Exception as e:
            logger.debug(f"WebSocket discovery to {base_url} failed: {e}")

        # Step 2: Fall back to A2A JSON-RPC
        try:
            import httpx
            from a2a.client.card_resolver import A2ACardResolver
            from a2a.client.client_factory import ClientFactory, ClientConfig
            from shared.a2a_bridge import a2a_card_to_custom

            async with httpx.AsyncClient() as http_client:
                resolver = A2ACardResolver(http_client, base_url)
                a2a_card = await resolver.get_agent_card()

            custom_card = a2a_card_to_custom(a2a_card)
            agent_id = custom_card.agent_id

            if agent_id in self.agents or agent_id in self.a2a_clients:
                logger.debug(f"A2A agent {agent_id} already connected")
                return

            # Create persistent A2A client
            config = ClientConfig(streaming=True)
            client = await ClientFactory.connect(
                agent=a2a_card,
                client_config=config,
            )

            self.a2a_clients[agent_id] = client
            self.a2a_agent_cards[agent_id] = a2a_card
            self.agent_urls[agent_id] = base_url

            # Register via the same path as WS agents (for routing, permissions, etc.)
            register_msg = RegisterAgent(agent_card=custom_card)
            await self.register_agent(None, register_msg)

            logger.info(f"External agent discovered via A2A (WebSocket unavailable): {agent_id} at {base_url}")

        except Exception as e:
            logger.debug(f"A2A discovery to {base_url} also failed: {e}")

    async def _setup_a2a_client_for_agent(self, base_url: str, agent_id: str):
        """Set up an A2A client as backup transport for a WebSocket-connected agent."""
        try:
            import httpx
            from a2a.client.card_resolver import A2ACardResolver
            from a2a.client.client_factory import ClientFactory, ClientConfig

            a2a_url = f"{base_url}/a2a"
            async with httpx.AsyncClient() as http_client:
                resolver = A2ACardResolver(http_client, a2a_url)
                a2a_card = await resolver.get_agent_card()

            config = ClientConfig(streaming=True)
            client = await ClientFactory.connect(
                agent=a2a_card,
                client_config=config,
            )

            self.a2a_clients[agent_id] = client
            self.a2a_agent_cards[agent_id] = a2a_card
            logger.info(f"A2A backup client set up for {agent_id}")
        except Exception as e:
            logger.debug(f"A2A backup setup for {agent_id} failed (non-critical): {e}")

    async def _agent_listen_loop(self, ws, agent_id: str):
        """Listen for messages from a connected agent."""
        try:
            async for message in ws:
                await self.handle_agent_message(ws, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Agent {agent_id} disconnected")
        finally:
            if agent_id in self.agents:
                del self.agents[agent_id]
            if agent_id in self.agent_cards:
                del self.agent_cards[agent_id]
                logger.info(f"Agent {agent_id} deregistered")
            if agent_id in self.security_flags:
                del self.security_flags[agent_id]

    # =========================================================================
    # MESSAGE HANDLING
    # =========================================================================

    async def handle_agent_message(self, websocket, message: str):
        """Handle message from an agent."""
        try:
            msg = Message.from_json(message)

            if isinstance(msg, RegisterAgent):
                await self.register_agent(websocket, msg)

            elif isinstance(msg, MCPResponse):
                req_id = msg.request_id
                if req_id in self.pending_requests:
                    self.pending_requests[req_id].set_result(msg)
                else:
                    logger.warning(f"Received response for unknown request: {req_id}")

        except Exception as e:
            logger.error(f"Error handling agent message: {e}")

    async def _safe_handle_ui_message(self, websocket, message: str):
        """Wrapper that catches exceptions from fire-and-forget UI message tasks.
        Non-register messages wait for registration to complete first."""
        try:
            # Quick parse to check if this is a register_ui message
            is_register = '"register_ui"' in message
            if not is_register:
                evt = self._registered_events.get(id(websocket))
                if evt and not evt.is_set():
                    await evt.wait()
            await self.handle_ui_message(websocket, message)
        except Exception as e:
            logger.error(f"UI message task error: {e}", exc_info=True)

    async def handle_ui_message(self, websocket, message: str):
        """Handle message from a UI client."""
        try:
            msg = Message.from_json(message)

            if isinstance(msg, RegisterUI):
                token = msg.token
                user_data = None
                
                # Check for token validation (skip if not configured or in debug/dev mode if desired, but we want security)
                if token:
                    user_data = await self.validate_token(token)
                
                if user_data:
                    logger.info(f"UI registered: {user_data.get('preferred_username', 'unknown')}")
                    user_data["_raw_token"] = token  # Store raw token for RFC 8693 delegation
                    self.ui_sessions[websocket] = user_data

                    # Persist user profile to database
                    self._save_user_profile(user_data)

                    # ROTE: register device capabilities and send profile back
                    device_info = msg.device or {}
                    rote_profile = self.rote.register_device(websocket, device_info)
                    await self._safe_send(websocket, json.dumps({
                        "type": "rote_config",
                        "device_profile": rote_profile.to_dict(),
                        "speech_server_available": bool(os.getenv("SPEACHES_URL", "").strip()),
                    }))

                    # Send stored user preferences (theme, etc.)
                    user_id = user_data.get("sub", "legacy")
                    try:
                        prefs = self.history.db.get_user_preferences(user_id)
                        if prefs:
                            await self._safe_send(websocket, json.dumps({
                                "type": "user_preferences",
                                "preferences": prefs,
                            }))
                    except Exception as e:
                        logger.warning(f"Failed to load user preferences: {e}")

                    # Mark registration complete so queued messages can proceed
                    evt = self._registered_events.get(id(websocket))
                    if evt:
                        evt.set()

                    # Notify UI of success (optional, or just send dashboard)
                    await self.send_dashboard(websocket)
                else:
                    logger.warning("UI registration failed: Invalid or missing token")
                    # Ungate waiting tasks so they hit the auth check naturally
                    evt = self._registered_events.get(id(websocket))
                    if evt:
                        evt.set()
                    await self.send_ui_render(websocket, [
                        Alert(message="Authentication failed. Please log in again.", variant="error").to_json()
                    ])
                    # We might want to close, but let's let the UI handle the error alert
                    return

            elif isinstance(msg, UIEvent):
                # Ensure authenticated
                if websocket not in self.ui_sessions:
                    await self.send_ui_render(websocket, [
                        Alert(message="Unauthorized. Please refresh.", variant="error").to_json()
                    ])
                    return

                user_id = self._get_user_id(websocket)

                if msg.action == "chat_message":
                    user_message = msg.payload.get("message", "")
                    chat_id = msg.session_id or msg.payload.get("chat_id")
                    draft_agent_id = msg.payload.get("draft_agent_id")

                    # If no chat_id provided, create one
                    if not chat_id:
                        chat_id = self.history.create_chat(user_id=user_id)
                        from_message = True
                        # Inform UI about new chat ID
                        await self._safe_send(websocket, json.dumps({
                            "type": "chat_created",
                            "payload": {"chat_id": chat_id, "from_message": True}
                        }))
                    else:
                        if not self.history.get_chat(chat_id, user_id=user_id):
                            self.history.create_chat(chat_id, user_id=user_id)
                            await self._safe_send(websocket, json.dumps({
                                "type": "chat_created",
                                "payload": {"chat_id": chat_id, "from_message": True}
                            }))

                    display_message = msg.payload.get("display_message")
                    self.cancelled_sessions[id(websocket)] = False
                    # Use serialized wrapper so concurrent chat messages
                    # for the same session are processed one at a time.
                    await self._serialized_chat(
                        websocket, user_message, chat_id, display_message,
                        user_id=user_id, draft_agent_id=draft_agent_id,
                    )

                elif msg.action == "cancel_task":
                    self.cancelled_sessions[id(websocket)] = True
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "done",
                        "message": "Cancelled"
                    }))

                elif msg.action == "get_dashboard":
                    await self.send_dashboard(websocket)

                elif msg.action == "discover_agents":
                    await self.send_agent_list(websocket)

                elif msg.action == "register_external_agent":
                    # Register an external A2A agent by URL (entered by user in frontend)
                    agent_url = msg.payload.get("url", "").strip().rstrip("/")
                    if not agent_url:
                        await self.send_ui_render(websocket, [
                            Alert(message="Please provide an agent URL", variant="error").to_json()
                        ])
                    else:
                        await self._safe_send(websocket, json.dumps({
                            "type": "chat_status",
                            "status": "thinking",
                            "message": f"Discovering agent at {agent_url}..."
                        }))
                        await self.discover_a2a_agent(agent_url)
                        if any(aid for aid, card in self.agent_cards.items()
                               if card.metadata.get("a2a_url") == agent_url):
                            await self.send_agent_list(websocket)
                            await self._safe_send(websocket, json.dumps({
                                "type": "chat_status", "status": "done",
                                "message": f"External agent registered from {agent_url}"
                            }))
                        else:
                            await self.send_ui_render(websocket, [
                                Alert(message=f"Could not discover A2A agent at {agent_url}", variant="error").to_json()
                            ])
                            await self._safe_send(websocket, json.dumps({
                                "type": "chat_status", "status": "done",
                                "message": "Discovery failed"
                            }))

                elif msg.action == "get_history":
                    chats = self.history.get_recent_chats(user_id=user_id)
                    await self._safe_send(websocket, json.dumps({
                        "type": "history_list",
                        "chats": chats
                    }))

                elif msg.action == "load_chat":
                    chat_id = msg.payload.get("chat_id")
                    chat = self.history.get_chat(chat_id, user_id=user_id)
                    if chat:
                        await self._safe_send(websocket, json.dumps({
                            "type": "chat_loaded",
                            "chat": chat
                        }))
                    else:
                        await self.send_ui_render(websocket, [
                            Alert(message="Chat not found", variant="error").to_json()
                        ])

                elif msg.action == "new_chat":
                    chat_id = self.history.create_chat(user_id=user_id)
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_created",
                        "payload": {"chat_id": chat_id, "from_message": False}
                    }))

                # Saved components actions
                elif msg.action == "save_component":
                    chat_id = msg.payload.get("chat_id")
                    component_data = msg.payload.get("component_data")
                    component_type = msg.payload.get("component_type")
                    title = msg.payload.get("title")
                    
                    if not chat_id or not component_data:
                        await self.send_ui_render(websocket, [
                            Alert(message="Missing required fields for saving component", variant="error").to_json()
                        ])
                        return
                    
                    try:
                        component_id = self.history.save_component(
                            chat_id, component_data, component_type, title, user_id=user_id
                        )
                        
                        # Send success response
                        await self._safe_send(websocket, json.dumps({
                            "type": "component_saved",
                            "component": {
                                "id": component_id,
                                "chat_id": chat_id,
                                "component_data": component_data,
                                "component_type": component_type,
                                "title": title or component_type.replace('_', ' ').title(),
                                "created_at": int(time.time() * 1000)
                            }
                        }))
                        
                        # Broadcast updated chat history (each user gets their own)
                        await self._broadcast_user_history()

                    except Exception as e:
                        logger.error(f"Failed to save component: {e}")
                        await self._safe_send(websocket, json.dumps({
                            "type": "component_save_error",
                            "error": str(e)
                        }))

                elif msg.action == "get_saved_components":
                    chat_id = msg.payload.get("chat_id")
                    components = self.history.get_saved_components(chat_id, user_id=user_id)
                    await self._safe_send(websocket, json.dumps({
                        "type": "saved_components_list",
                        "components": components
                    }))

                elif msg.action == "delete_saved_component":
                    component_id = msg.payload.get("component_id")
                    if not component_id:
                        await self.send_ui_render(websocket, [
                            Alert(message="Missing component ID", variant="error").to_json()
                        ])
                        return
                    
                    success = self.history.delete_component(component_id, user_id=user_id)
                    if success:
                        await self._safe_send(websocket, json.dumps({
                            "type": "component_deleted",
                            "component_id": component_id
                        }))
                        
                        # Broadcast updated chat history (each user gets their own)
                        await self._broadcast_user_history()
                    else:
                        await self._safe_send(websocket, json.dumps({
                            "type": "component_save_error",
                            "error": "Component not found"
                        }))

                elif msg.action == "combine_components":
                    source_id = msg.payload.get("source_id")
                    target_id = msg.payload.get("target_id")
                    
                    if not source_id or not target_id:
                        await self._safe_send(websocket, json.dumps({
                            "type": "combine_error",
                            "error": "Both source and target component IDs are required"
                        }))
                        return
                    
                    source = self.history.get_component_by_id(source_id, user_id=user_id)
                    target = self.history.get_component_by_id(target_id, user_id=user_id)
                    
                    if not source or not target:
                        await self._safe_send(websocket, json.dumps({
                            "type": "combine_error",
                            "error": "One or both components not found"
                        }))
                        return
                    
                    # Send progress
                    await self._safe_send(websocket, json.dumps({
                        "type": "combine_status",
                        "status": "combining",
                        "message": f"Combining {source['title']} with {target['title']}..."
                    }))
                    
                    try:
                        result = await self._combine_components_llm(
                            [source, target],
                            mode="combine"
                        )
                        
                        if result.get("error"):
                            await websocket.send(json.dumps({
                                "type": "combine_error",
                                "error": result["error"]
                            }))
                        else:
                            chat_id = source["chat_id"]
                            new_components = self.history.replace_components(
                                [source_id, target_id],
                                result["components"],
                                chat_id,
                                user_id=user_id
                            )
                            await self._safe_send(websocket, json.dumps({
                                "type": "components_combined",
                                "removed_ids": [source_id, target_id],
                                "new_components": new_components
                            }))
                    except Exception as e:
                        logger.error(f"Combine failed: {e}", exc_info=True)
                        await self._safe_send(websocket, json.dumps({
                            "type": "combine_error",
                            "error": f"Failed to combine components: {str(e)}"
                        }))

                elif msg.action == "get_agent_permissions":
                    agent_id = msg.payload.get("agent_id")
                    if not agent_id:
                        return
                    # Build available tools list for this agent
                    card = self.agent_cards.get(agent_id)
                    if not card:
                        return
                    available_tools = [s.id for s in card.skills]
                    tool_descriptions = {s.id: s.description for s in card.skills}
                    scopes = self.tool_permissions.get_agent_scopes(user_id, agent_id)
                    tool_scope_map = self.tool_permissions.get_tool_scope_map(agent_id)
                    permissions = self.tool_permissions.get_effective_permissions(
                        user_id, agent_id, available_tools
                    )
                    tool_overrides = self.tool_permissions.get_tool_overrides(user_id, agent_id)
                    await self._safe_send(websocket, json.dumps({
                        "type": "agent_permissions",
                        "agent_id": agent_id,
                        "agent_name": card.name,
                        "scopes": scopes,
                        "tool_scope_map": tool_scope_map,
                        "permissions": permissions,
                        "tool_overrides": tool_overrides,
                        "tool_descriptions": tool_descriptions,
                        "security_flags": self.security_flags.get(agent_id, {})
                    }))

                elif msg.action == "set_agent_permissions":
                    agent_id = msg.payload.get("agent_id")
                    scopes = msg.payload.get("scopes", {})
                    tool_overrides_payload = msg.payload.get("tool_overrides")
                    if not agent_id or not isinstance(scopes, dict):
                        return
                    self.tool_permissions.set_agent_scopes(
                        user_id, agent_id, scopes
                    )
                    if isinstance(tool_overrides_payload, dict):
                        self.tool_permissions.set_tool_overrides(
                            user_id, agent_id, tool_overrides_payload
                        )
                    logger.info(f"Scopes updated: user={user_id} agent={agent_id} scopes={scopes}")
                    # Compute effective per-tool permissions from new scopes + overrides
                    card = self.agent_cards.get(agent_id)
                    available_tools = [s.id for s in card.skills] if card else []
                    permissions = self.tool_permissions.get_effective_permissions(
                        user_id, agent_id, available_tools
                    )
                    tool_overrides = self.tool_permissions.get_tool_overrides(user_id, agent_id)
                    await self._safe_send(websocket, json.dumps({
                        "type": "agent_permissions_updated",
                        "agent_id": agent_id,
                        "scopes": scopes,
                        "permissions": permissions,
                        "tool_overrides": tool_overrides
                    }))

                    # Also broadcast an updated dashboard to all UI clients for this user
                    # so their total tools count updates immediately
                    for client in self.ui_clients:
                        client_user_id = self._get_user_id(client)
                        if client_user_id == user_id:
                            asyncio.create_task(self.send_dashboard(client))


                elif msg.action == "update_device":
                    # ROTE: viewport / capability change from the frontend
                    device_info = msg.payload.get("device") or {}
                    new_profile, re_adapted = self.rote.update_device(websocket, device_info)
                    await self._safe_send(websocket, json.dumps({
                        "type": "rote_config",
                        "device_profile": new_profile.to_dict(),
                        "speech_server_available": bool(os.getenv("SPEACHES_URL", "").strip()),
                    }))
                    # If the profile changed and we have cached components, re-send them.
                    # Use UIUpdate (not UIRender) so the frontend replaces the last
                    # components in-place instead of appending a duplicate message.
                    if re_adapted is not None:
                        msg_out = UIUpdate(components=re_adapted)
                        await self._safe_send(websocket, msg_out.to_json())

                elif msg.action == "save_theme":
                    # Persist theme colors to user preferences
                    theme_data = msg.payload.get("theme")
                    if theme_data:
                        try:
                            self.history.db.set_user_preferences(user_id, {"theme": theme_data})
                        except Exception as e:
                            logger.warning(f"Failed to save theme for {user_id}: {e}")

                elif msg.action == "condense_components":
                    component_ids = msg.payload.get("component_ids", [])
                    
                    if len(component_ids) < 2:
                        await self._safe_send(websocket, json.dumps({
                            "type": "combine_error",
                            "error": "At least 2 components are required to condense"
                        }))
                        return
                    
                    components = []
                    for cid in component_ids:
                        comp = self.history.get_component_by_id(cid, user_id=user_id)
                        if comp:
                            components.append(comp)
                    
                    if len(components) < 2:
                        await self._safe_send(websocket, json.dumps({
                            "type": "combine_error",
                            "error": "Not enough valid components found"
                        }))
                        return
                    
                    await self._safe_send(websocket, json.dumps({
                        "type": "combine_status",
                        "status": "condensing",
                        "message": f"Condensing {len(components)} components..."
                    }))
                    
                    try:
                        result = await self._combine_components_llm(
                            components,
                            mode="condense"
                        )
                        
                        if result.get("error"):
                            await self._safe_send(websocket, json.dumps({
                                "type": "combine_error",
                                "error": result["error"]
                            }))
                        else:
                            chat_id = components[0]["chat_id"]
                            new_components = self.history.replace_components(
                                component_ids,
                                result["components"],
                                chat_id,
                                user_id=user_id
                            )
                            await self._safe_send(websocket, json.dumps({
                                "type": "components_condensed",
                                "removed_ids": component_ids,
                                "new_components": new_components
                            }))
                    except Exception as e:
                        logger.error(f"Condense failed: {e}", exc_info=True)
                        await self._safe_send(websocket, json.dumps({
                            "type": "combine_error",
                            "error": f"Failed to condense components: {str(e)}"
                        }))

                elif msg.action == "table_paginate":
                    # Re-invoke a tool with updated pagination params
                    tool_name = msg.payload.get("tool_name")
                    agent_id = msg.payload.get("agent_id")
                    params = msg.payload.get("params", {})

                    if not tool_name or not agent_id:
                        await self.send_ui_render(websocket, [
                            Alert(message="Missing tool_name or agent_id for pagination", variant="error").to_json()
                        ])
                        await self._safe_send(websocket, json.dumps({
                            "type": "chat_status", "status": "done", "message": ""
                        }))
                        return

                    # Inject per-user credentials (E2E encrypted — only agent can decrypt)
                    args = dict(params)
                    if user_id and agent_id:
                        creds = self.credential_manager.get_agent_credentials_encrypted(user_id, agent_id)
                        if creds:
                            args["_credentials"] = creds
                            args["_credentials_encrypted"] = True

                    try:
                        result = await self._execute_with_retry(websocket, agent_id, tool_name, args)
                        if result and result.ui_components:
                            await self.send_ui_render(websocket, result.ui_components)
                        elif result and result.error:
                            await self.send_ui_render(websocket, [
                                Alert(message=result.error.get("message", "Pagination failed"), variant="error").to_json()
                            ])
                    except Exception as e:
                        logger.error(f"table_paginate failed: {e}", exc_info=True)
                        await self.send_ui_render(websocket, [
                            Alert(message=f"Pagination failed: {e}", variant="error").to_json()
                        ])
                    finally:
                        await self._safe_send(websocket, json.dumps({
                            "type": "chat_status", "status": "done", "message": ""
                        }))

        except Exception as e:
            import traceback
            logger.error(f"Error handling UI message: {e}\n{traceback.format_exc()}")

    # =========================================================================
    # COMPONENT COMBINING (LLM-powered)
    # =========================================================================

    async def _combine_components_llm(self, components: list, mode: str = "combine") -> dict:
        """Use LLM to combine/condense UI components.
        
        Args:
            components: List of component dicts with component_data, title, etc.
            mode: 'combine' for merging 2 components, 'condense' for reducing many.
        
        Returns:
            {"components": [...]} on success, {"error": "..."} on failure.
        """
        if not self.llm_client:
            return {"error": "LLM not configured"}

        # Build the component descriptions for the prompt
        component_descriptions = []
        for i, comp in enumerate(components):
            component_descriptions.append(
                f"Component {i+1} (title: \"{comp['title']}\", type: \"{comp['component_type']}\"):\n"
                f"```json\n{json.dumps(comp['component_data'], indent=2)}\n```"
            )
        
        components_text = "\n\n".join(component_descriptions)

        schema_description = """Available UI primitive types and their JSON structure:
- "text": {type: "text", content: "...", variant: "body|h1|h2|h3|caption|markdown"}
- "card": {type: "card", title: "...", content: [...child components...]}
- "metric": {type: "metric", title: "...", value: "...", subtitle: "...", progress: 0.0-1.0, variant: "default|warning|error|success"}
- "table": {type: "table", title: "...", headers: [...], rows: [[...],...]}
- "grid": {type: "grid", columns: 2, gap: 16, children: [...child components...]}
- "container": {type: "container", children: [...child components...]}
- "list": {type: "list", items: [...], ordered: false, variant: "default|detailed"}
- "alert": {type: "alert", message: "...", title: "...", variant: "info|success|warning|error"}
- "progress": {type: "progress", value: 0.0-1.0, label: "...", show_percentage: true}
- "bar_chart": {type: "bar_chart", title: "...", labels: [...], datasets: [{label: "...", data: [...]}]}
- "line_chart": {type: "line_chart", title: "...", labels: [...], datasets: [{label: "...", data: [...]}]}
- "pie_chart": {type: "pie_chart", title: "...", labels: [...], data: [...], colors: [...]}
- "code": {type: "code", code: "...", language: "..."}
- "divider": {type: "divider"}
- "collapsible": {type: "collapsible", title: "...", content: [...child components...], default_open: false}"""

        if mode == "combine":
            prompt = f"""You are a UI component combiner. You are given 2 UI components and must merge them into a single cohesive component.

{schema_description}

RULES:
1. Analyze whether these components can be meaningfully combined.
2. If they contain RELATED data (e.g., patient data + disease chart, or multiple system metrics), combine them into a unified component using cards, grids, or tables.
3. If they are UNRELATED or incompatible, respond ONLY with: ERROR: <brief reason>
4. Preserve ALL data — do not lose any information from either component.
5. Use grid layouts to arrange related metrics side-by-side.
6. Use cards with descriptive titles to group related content.

COMPONENTS TO COMBINE:

{components_text}

Respond with ONLY valid JSON (no markdown code fences) in this format:
{{
  "components": [
    {{
      "component_data": {{...the merged component tree...}},
      "component_type": "card",
      "title": "Descriptive Title For Merged Component"
    }}
  ]
}}

Or if they cannot be combined:
ERROR: <reason>"""
        else:  # condense
            prompt = f"""You are a UI component condenser. You are given {len(components)} UI components and must combine as many as possible into fewer cohesive components.

{schema_description}

RULES:
1. Group RELATED components together (e.g., all system metrics into one dashboard card, all patient data into one view).
2. Keep UNRELATED components separate — don't force unrelated data together.
3. Preserve ALL data — do not lose any information.
4. Use grid layouts to arrange related metrics side-by-side.
5. Use cards with descriptive titles to group related content.
6. The goal is to REDUCE the total number of components while maintaining clarity.

COMPONENTS TO CONDENSE:

{components_text}

Respond with ONLY valid JSON (no markdown code fences) in this format:
{{
  "components": [
    {{
      "component_data": {{...component tree...}},
      "component_type": "card",
      "title": "Descriptive Title"
    }}
  ]
}}"""

        try:
            # Use _call_llm for built-in retries (important for transient 502s)
            llm_msg, _usage = await self._call_llm(
                None,  # no websocket needed for combine
                [
                    {"role": "system", "content": "You are a precise UI component combiner. Output ONLY valid JSON or an ERROR message. No explanations, no markdown fences."},
                    {"role": "user", "content": prompt}
                ],
                tools_desc=None,
                temperature=0.1
            )

            if not llm_msg:
                return {"error": "LLM returned no response"}
            
            content = (llm_msg.content or "").strip()
            logger.info(f"LLM combine response ({len(content)} chars): {content[:200]}...")
            
            # Check for ERROR response
            if content.upper().startswith("ERROR"):
                error_msg = content.split(":", 1)[1].strip() if ":" in content else content
                return {"error": error_msg}
            
            # Try to parse JSON
            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
            
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Try to find JSON in the response
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    return {"error": f"Failed to parse LLM response as JSON"}
            
            if "components" not in result or not isinstance(result["components"], list):
                return {"error": "LLM response missing 'components' array"}
            
            # Known valid primitive types from primitives.py
            VALID_TYPES = {
                "container", "text", "button", "card", "table", "list",
                "alert", "progress", "metric", "code", "image", "grid",
                "tabs", "divider", "input", "bar_chart", "line_chart",
                "pie_chart", "plotly_chart", "collapsible", "chart"
            }
            
            # Validate each component
            for comp in result["components"]:
                if "component_data" not in comp:
                    return {"error": "LLM response component missing 'component_data'"}
                
                # Validate the component type
                comp_data = comp["component_data"]
                comp_type = comp_data.get("type", "")
                if comp_type and comp_type not in VALID_TYPES:
                    logger.warning(f"LLM produced unknown component type '{comp_type}', wrapping in card")
                    # Wrap unknown types in a card to ensure they render
                    comp["component_data"] = {
                        "type": "card",
                        "title": comp_data.get("title", "Combined Component"),
                        "content": [comp_data] if comp_type else []
                    }
                    comp_type = "card"
                
                # Recursively validate children
                self._validate_component_tree(comp_data, VALID_TYPES)
                
                if "component_type" not in comp:
                    comp["component_type"] = comp_type or "card"
                if "title" not in comp:
                    comp["title"] = comp["component_data"].get("title", "Combined Component")
            
            return result
            
        except Exception as e:
            logger.error(f"LLM combine error: {e}", exc_info=True)
            return {"error": f"LLM error: {str(e)}"}

    def _validate_component_tree(self, node: dict, valid_types: set):
        """Recursively validate component tree, fixing invalid types."""
        if not isinstance(node, dict):
            return
        
        raw_type = node.get("type", "")
        node_type = raw_type.strip().lower()
        # Map generic 'chart' to 'plotly_chart' regardless of validity
        if node_type == "chart":
            logger.info(f"Mapping generic component type 'chart' -> 'plotly_chart'")
            node["type"] = "plotly_chart"
            node_type = "plotly_chart"  # update variable for subsequent checks
        
        if node_type and node_type not in valid_types:
            logger.warning(f"Fixing unknown component type '{node_type}' -> 'container'")
            node["type"] = "container"
        
        # Validate children arrays
        for key in ("children", "content"):
            children = node.get(key, [])
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        self._validate_component_tree(child, valid_types)
        
        # Validate tab items
        tabs = node.get("tabs", [])
        if isinstance(tabs, list):
            for tab in tabs:
                if isinstance(tab, dict):
                    for child in tab.get("content", []):
                        if isinstance(child, dict):
                            self._validate_component_tree(child, valid_types)

    def _map_file_paths(self, chat_id: str, args: Dict, user_id: str = 'legacy') -> Dict:
        """Replace original filenames in tool arguments with backend paths.
        
        Uses file mappings stored in history for the given chat.
        """
        if not chat_id:
            return args
        
        mappings = self.history.get_file_mappings(chat_id, user_id=user_id)
        if not mappings:
            return args
        
        # Build mapping dict: original_name -> backend_path
        mapping_dict = {m["original_name"]: m["backend_path"] for m in mappings}
        
        # Recursively traverse args dict and replace strings that match original names
        def replace_in_dict(obj):
            if isinstance(obj, dict):
                return {k: replace_in_dict(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_in_dict(item) for item in obj]
            elif isinstance(obj, str):
                # Check if the string matches any original name (exact match)
                for orig, backend in mapping_dict.items():
                    if obj == orig:
                        logger.info(f"Mapping file path: '{orig}' -> '{backend}'")
                        return backend
                return obj
            else:
                return obj
        
        new_args = replace_in_dict(args)
        if new_args != args:
            logger.info(f"Mapped file paths in tool arguments for chat {chat_id}")
        return new_args

    # =========================================================================
    # LLM-POWERED TOOL ROUTING
    # =========================================================================

    async def _start_heartbeat(self, websocket) -> asyncio.Task:
        """Start sending heartbeat messages every 5s to keep UI informed during long operations."""
        async def _heartbeat_loop():
            while True:
                await asyncio.sleep(5)
                try:
                    await self._safe_send(websocket, json.dumps({
                        "type": "heartbeat",
                        "timestamp": time.time()
                    }))
                except Exception:
                    break
        return asyncio.create_task(_heartbeat_loop())

    async def _serialized_chat(self, websocket, message, chat_id, display_message, *, user_id=None, draft_agent_id=None):
        """Run handle_chat_message under a per-websocket lock so messages
        are serialized but the WS receive loop is never blocked."""
        ws_id = id(websocket)
        lock = self._chat_locks.setdefault(ws_id, asyncio.Lock())
        async with lock:
            try:
                await self.handle_chat_message(
                    websocket, message, chat_id, display_message,
                    user_id=user_id, draft_agent_id=draft_agent_id,
                )
            except Exception as e:
                logger.error(f"Chat task error: {e}", exc_info=True)
                await self._safe_send(websocket, json.dumps({
                    "type": "chat_status", "status": "done",
                    "message": f"Error: {e}"
                }))

    async def handle_chat_message(self, websocket, message: str, chat_id: str, display_message: str = None, user_id: str = None, draft_agent_id: str = None):
        """Process a chat message: LLM determines which tools to call (Multi-Turn Re-Act Loop)."""
        logger.info(f"Processing chat message: '{message}' for chat_id {chat_id}")
        if user_id is None:
            user_id = self._get_user_id(websocket)
        if not message:
            logger.warning("Empty message received")
            return

        if not self.llm_client:
            await self.send_ui_render(websocket, [
                Alert(message="LLM not configured. Set OPENAI_API_KEY and OPENAI_BASE_URL.", variant="error").to_json()
            ])
            return

        # Send loading state to UI
        await self._safe_send(websocket, json.dumps({
            "type": "chat_status",
            "status": "thinking",
            "message": "Analyzing request and planning actions..."
        }))
        
        # Save User Message to History. If display_message is provided, save that instead.
        msg_to_save = display_message if display_message else message
        self.history.add_message(chat_id, "user", msg_to_save, user_id=user_id)

        # Capture File Upload Mapping
        upload_match = re.search(r"I have uploaded (.*?) to the backend at: `(.*?)`" , message)
        if upload_match:
            original_name = upload_match.group(1)
            backend_path = upload_match.group(2)
            logger.info(f"Captured file upload mapping: {original_name} -> {backend_path}")
            self.history.add_file_mapping(chat_id, original_name, backend_path, user_id=user_id)

        # Async title summarization for new chats
        chat_data = self.history.get_chat(chat_id, user_id=user_id)
        if chat_data and len(chat_data.get("messages", [])) == 1:
            asyncio.create_task(self.summarize_chat_title(chat_id, msg_to_save, user_id=user_id))

        # Build tool definitions from registered agents
        # Filter by user's per-agent tool permissions (RFC 8693 delegation)
        # Draft test chats: only expose the draft agent's tools
        if draft_agent_id:
            logger.info(f"Draft test chat — filtering tools to agent: {draft_agent_id}")
        else:
            logger.info(f"Building tool definitions from {len(self.agent_cards)} agents...")
        tools_desc = []
        tool_to_agent = {}  # Map tool name → agent_id

        for agent_id, card in self.agent_cards.items():
            if agent_id not in self.agents:
                continue

            # Draft test: only include tools from the draft agent being tested
            if draft_agent_id and agent_id != draft_agent_id:
                continue

            for skill in card.skills:
                # System-level security block (overrides user permissions)
                agent_flags = self.security_flags.get(agent_id, {})
                if skill.id in agent_flags and agent_flags[skill.id].get("blocked"):
                    logger.debug(f"Tool '{skill.id}' system-blocked (security) for agent={agent_id}")
                    continue

                # Check if the user has allowed this tool for this agent
                if not self.tool_permissions.is_tool_allowed(user_id, agent_id, skill.id):
                    logger.debug(f"Tool '{skill.id}' blocked for user={user_id} agent={agent_id}")
                    continue

                schema = self._sanitize_tool_schema(skill.input_schema or {"type": "object", "properties": {}})
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": skill.id,
                        "description": skill.description,
                        "parameters": schema
                    }
                }
                tools_desc.append(tool_def)
                tool_to_agent[skill.id] = agent_id

        if not tools_desc:
            await self.send_ui_render(websocket, [
                Alert(message="No agents connected. Please wait for agents to register.", variant="warning").to_json()
            ])
            return

        try:
            # ------------------------------------------------------------------
            # SYSTEM PROMPT
            # ------------------------------------------------------------------
            # Fetch file mappings for this chat
            file_mappings = self.history.get_file_mappings(chat_id, user_id=user_id)
            file_context = ""
            if file_mappings:
                file_context = "\nFILES ACCESSED IN THIS CHAT (Original Name -> Backend Path):\n"
                for mapping in file_mappings:
                    file_context += f"- {mapping['original_name']} -> {mapping['backend_path']}\n"
                file_context += "\nIMPORTANT: You MUST use the absolute backend path (right side) when calling tools for these files. Never use just the original filename.\n"

            system_prompt = f"""You are an AI orchestrator. Your goal is to simplify complex tasks for the user by intelligently using available tools.

{file_context}

AVAILABLE TOOLS: sent in the `tools` parameter.

PROCESS (Re-Act Loop):
1. **Analyze**: Break down the user's request into logical steps.
2. **Plan & Execute**: 
   - If you need data, call the appropriate tool.
   - You can call multiple tools in parallel if they are independent.
   - If a step depends on previous output (e.g., "search patients" -> "graph their age"), wait for the first tool's result before calling the next.
3. **Observe**: You will receive the tool's output in the next turn.
4. **Iterate**: 
   - IF the task is not complete or you need more data (e.g., now you have the patients, need to graph them), call the next tool.
   - IF you have all necessary information, provide a final answer.

CRITICAL RULES:
- **VERIFY**: Check if tool outputs actually contain the data you expect before stating it exists. If a search returns 0 results, do NOT try to graph them.
- **FINAL RESPONSE**: When you have finished all actions, provide a natural language summary of what you did and what was found.
- **VISUALIZATIONS**: If the user asks for a graph, YOU MUST call the graphing tool. Do not just describe the data.
"""

            # ------------------------------------------------------------------
            # MULTI-TURN LOOP
            # ------------------------------------------------------------------
            # Fetch recent history
            history_messages = []
            chat_data = self.history.get_chat(chat_id, user_id=user_id)
            if chat_data and "messages" in chat_data:
                # Get last 10 messages (excluding the one we just added)
                raw_history = chat_data["messages"][:-1]
                for h_msg in raw_history[-10:]:
                    role = h_msg.get("role")
                    content = h_msg.get("content")
                    
                    # If content is UI component list, stringify it or summarize it
                    if isinstance(content, list):
                        # Try to find text content or just stringify the whole thing
                        content_str = json.dumps(content)
                        # Optional: limit size of historical UI components
                        if len(content_str) > 2000:
                            content_str = content_str[:2000] + "... [TRUNCATED]"
                    else:
                        content_str = str(content)
                        
                    history_messages.append({"role": role, "content": content_str})

            messages = [
                {"role": "system", "content": system_prompt},
                *history_messages,
                {"role": "user", "content": message}
            ]

            MAX_TURNS = 10
            turn_count = 0
            heartbeat_task = await self._start_heartbeat(websocket)

            while turn_count < MAX_TURNS:
                # Check for cancellation
                if self.cancelled_sessions.get(id(websocket)):
                    logger.info(f"Processing cancelled by user for chat_id {chat_id}")
                    await self.send_ui_render(websocket, [
                        Alert(message="Processing was cancelled.", variant="info").to_json()
                    ])
                    self.history.add_message(chat_id, "assistant", [
                        Alert(message="Processing was cancelled.", variant="info").to_json()
                    ], user_id=user_id)
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "done",
                        "message": ""
                    }))
                    return

                turn_count += 1
                logger.info(f"--- Turn {turn_count}/{MAX_TURNS} ---")

                # Call LLM
                llm_msg, usage = await self._call_llm(websocket, messages, tools_desc)
                self._accumulate_usage(chat_id, usage)
                if not llm_msg:
                    logger.error("LLM returned None, stopping loop.")
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "done",
                        "message": ""
                    }))
                    await self.send_ui_render(websocket, [
                        Alert(message="Failed to get a response from the AI model. Please try again.", variant="error").to_json()
                    ])
                    return

                # Check for reasoning content (DeepSeek, o1, etc.)
                reasoning = getattr(llm_msg, 'reasoning_content', None)
                if reasoning:
                    logger.info(f"LLM returned reasoning content ({len(reasoning)} chars)")
                    reasoning_components = [
                        Collapsible(title="Reasoning", content=[
                            Text(content=reasoning, variant="markdown")
                        ]).to_json()
                    ]
                    await self.send_ui_render(websocket, reasoning_components)
                    self.history.add_message(chat_id, "assistant", reasoning_components, user_id=user_id)

                # Check if LLM wants to call tools
                if llm_msg.tool_calls:
                    logger.info(f"LLM requested {len(llm_msg.tool_calls)} tool(s)")
                    
                    # Notify UI
                    tool_names = [tc.function.name for tc in llm_msg.tool_calls]
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "executing",
                        "message": f"Running: {', '.join(tool_names)}..."
                    }))

                    # Add assistant's message (with tool calls) to history
                    messages.append(llm_msg)

                    # Execute tools
                    tool_results = []
                    if len(llm_msg.tool_calls) == 1:
                        tc = llm_msg.tool_calls[0]
                        res = await self.execute_single_tool(websocket, tc, tool_to_agent, chat_id, user_id=user_id)
                        if res: tool_results.append(res)
                    else:
                        res_list = await self.execute_parallel_tools(websocket, llm_msg.tool_calls, tool_to_agent, chat_id, user_id=user_id)
                        tool_results.extend(res_list)

                    # Collect tool UI components and tag each (recursively) with source metadata
                    def _tag_source(comp, agent_id, tool_name):
                        """Recursively tag a component dict and all nested children."""
                        if not isinstance(comp, dict):
                            return
                        comp["_source_agent"] = agent_id
                        comp["_source_tool"] = tool_name
                        for key in ("content", "children"):
                            nested = comp.get(key)
                            if isinstance(nested, list):
                                for child in nested:
                                    _tag_source(child, agent_id, tool_name)

                    tool_ui_components = []
                    for i_tc, res in enumerate(tool_results):
                        if res and res.ui_components and not res.error:
                            tc = llm_msg.tool_calls[i_tc] if i_tc < len(llm_msg.tool_calls) else None
                            t_name = tc.function.name if tc else ""
                            a_id = tool_to_agent.get(t_name, "")
                            for comp in res.ui_components:
                                _tag_source(comp, a_id, t_name)
                                tool_ui_components.append(comp)

                    if tool_ui_components:
                        # Build label with agent attribution
                        tool_labels = []
                        for tn in tool_names:
                            agent_id = tool_to_agent.get(tn, "")
                            agent_name = self.agent_cards[agent_id].name if agent_id in self.agent_cards else ""
                            label = tn.replace('_', ' ').title()
                            if agent_name:
                                label = f"{agent_name}: {label}"
                            tool_labels.append(label)
                        tool_label = ', '.join(tool_labels)
                        collapsible = Collapsible(
                            title=f"Tool Results — {tool_label}",
                            content=[
                                comp if isinstance(comp, dict) else comp
                                for comp in tool_ui_components
                            ],
                            default_open=False
                        ).to_json()
                        await self.send_ui_render(websocket, [collapsible])
                        if chat_id:
                            self.history.add_message(chat_id, "assistant", [collapsible], user_id=user_id)

                    # Append tool outputs to LLM conversation history
                    for i, tc in enumerate(llm_msg.tool_calls):
                        res = tool_results[i] if i < len(tool_results) else None
                        
                        content_str = "No output"
                        if res:
                            if res.error:
                                content_str = f"Error: {res.error.get('message')}"
                            elif res.result:
                                if isinstance(res.result, dict) and "_data" in res.result:
                                    content_str = json.dumps(res.result["_data"])
                                else:
                                    content_str = json.dumps(res.result)
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.function.name,
                            "content": content_str
                        })

                    # Loop continues to next turn to let LLM analyze results
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "thinking",
                        "message": "Analyzing results..."
                    }))
                
                else:
                    # No tool calls -> Final Response
                    content = llm_msg.content or "I'm not sure how to help with that."
                    
                    parsed_components = None
                    needs_retry = False
                    error_msg = ""
                    
                    # Heuristic: if it looks like JSON containing a component
                    stripped = content.strip()
                    looks_like_json = stripped.startswith("{") or stripped.startswith("[") or "```json" in content

                    if looks_like_json:
                        raw_json = content
                        if "```json" in content:
                            match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
                            if match:
                                raw_json = match.group(1)
                            else:
                                match = re.search(r'```(.*?)```', content, re.DOTALL)
                                if match:
                                    raw_json = match.group(1).strip()
                    else:
                        # Fallback: LLM may have output text before JSON components
                        # Search for a JSON array or object containing a "type" field
                        json_match = re.search(r'(\[[\s\S]*\]|\{[\s\S]*\})\s*$', content)
                        if json_match:
                            raw_json = json_match.group(1)
                            looks_like_json = True
                            logger.info("Extracted trailing JSON from mixed text+JSON response")

                    if looks_like_json:
                        try:
                            # Try to parse and find valid components
                            # Using the same technique as the _combine_components_llm parser
                            # First try to parse directly
                            try:
                                data = json.loads(raw_json)
                            except json.JSONDecodeError:
                                # Strip markdown code fences if present
                                if raw_json.startswith("```"):
                                    raw_json = raw_json.split("\n", 1)[1] if "\n" in raw_json else raw_json[3:]
                                    if raw_json.endswith("```"):
                                        raw_json = raw_json[:-3]
                                    raw_json = raw_json.strip()

                                try:
                                    data = json.loads(raw_json)
                                except json.JSONDecodeError:
                                    # Fallback: regex search for JSON
                                    json_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', raw_json)
                                    if json_match:
                                        data = json.loads(json_match.group())
                                    else:
                                        raise
                            
                            if isinstance(data, dict):
                                # Unwrap common LLM wrapper patterns:
                                # {"components": [...]}, {"ui_components": [...]}, {"content": [...]}
                                for wrapper_key in ("components", "ui_components", "content"):
                                    if wrapper_key in data and isinstance(data[wrapper_key], list):
                                        inner = data[wrapper_key]
                                        # Verify at least one inner item looks like a component
                                        if any(isinstance(x, dict) and "type" in x for x in inner):
                                            data = inner
                                            break
                                else:
                                    data = [data]
                            
                            valid_components = []
                            if isinstance(data, list):
                                for item in data:
                                    if isinstance(item, dict) and "type" in item:
                                        # Recursively validate component structure to ensure frontend won't crash
                                        self._validate_component_tree(item, {
                                            "container", "text", "button", "card", "table", "list",
                                            "alert", "progress", "metric", "code", "image", "grid",
                                            "tabs", "divider", "input", "bar_chart", "line_chart",
                                            "pie_chart", "plotly_chart", "collapsible",
                                            "file_upload", "file_download"
                                        })
                                        valid_components.append(item)
                            
                            if valid_components:
                                parsed_components = valid_components
                            else:
                                needs_retry = True
                                error_msg = "JSON parsed successfully but no valid UI components found. Each component MUST be an object with at least a 'type' field (e.g., {'type': 'card', 'title': '...', 'content': [...]})."
                                
                        except Exception as e:
                            needs_retry = True
                            error_msg = f"Failed to parse UI components. The output is not valid JSON. Error: {str(e)}. Please respond ONLY with valid JSON, with NO surrounding text or markdown formatting."
                    
                    if needs_retry and turn_count < MAX_TURNS:
                        logger.warning(f"UI component generation failed parsing. Retrying. Error: {error_msg}")
                        messages.append(llm_msg)
                        messages.append({
                            "role": "user",
                            "content": f"SYSTEM RECOVERY ERROR: {error_msg}\nRemember, you MUST output ONLY valid JSON without Markdown formatting, enclosing explanations, or preamble. Return the complete corrected component array."
                        })
                        
                        await self._safe_send(websocket, json.dumps({
                            "type": "chat_status",
                            "status": "thinking",
                            "message": "Fixing formatting errors in UI component..."
                        }))
                        continue
                    
                    logger.info("LLM provided final response. conversation complete.")
                    
                    if parsed_components:
                        response_components = parsed_components
                    else:
                        response_components = [
                            Card(title="Analysis", content=[
                                Text(content=content, variant="markdown")
                            ]).to_json()
                        ]

                    await self.send_ui_render(websocket, response_components)

                    # Save complete interaction to history
                    self.history.add_message(chat_id, "assistant", response_components, user_id=user_id)

                    # Signal that processing is complete
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "done",
                        "message": ""
                    }))
                    return

            # If loop exits without final response — generate LLM summary
            if turn_count >= MAX_TURNS:
                logger.info(f"Max turns ({turn_count}) reached. Generating summary of tool outputs.")
                await self._safe_send(websocket, json.dumps({
                    "type": "chat_status",
                    "status": "thinking",
                    "message": "Generating summary..."
                }))

                summary_components = await self._generate_tool_summary(
                    websocket, messages, chat_id, user_id=user_id
                )
                if summary_components:
                    await self.send_ui_render(websocket, summary_components)
                    if chat_id:
                        self.history.add_message(chat_id, "assistant", summary_components, user_id=user_id)
                else:
                    # Fallback if LLM summary fails
                    await self.send_ui_render(websocket, [
                        Card(title="Summary", content=[
                            Text(content="Multiple tool operations were completed. Review the results above for details.", variant="body")
                        ]).to_json()
                    ])

                await self._safe_send(websocket, json.dumps({
                    "type": "chat_status",
                    "status": "done",
                    "message": ""
                }))

        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"WebSocket closed during chat processing for chat_id {chat_id} — client likely reconnected")
        except Exception as e:
            logger.error(f"LLM routing error: {e}", exc_info=True)
            error_text = str(e)

            # Auto-fix: if this is a draft agent test chat and the error is a bad tool schema,
            # trigger auto-fix so the agent code gets corrected automatically.
            if draft_agent_id and hasattr(self, 'lifecycle_manager') and ("invalid" in error_text.lower() and "schema" in error_text.lower()):
                logger.info(f"Bad tool schema for draft agent {draft_agent_id} — triggering auto-fix")
                try:
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status", "status": "fixing",
                        "message": f"Invalid tool schema detected — auto-fixing agent code..."
                    }))
                    fixed = await self.lifecycle_manager.auto_fix_tool_error(
                        draft_agent_id, "_schema_validation",
                        f"The agent's TOOL_REGISTRY has invalid input_schema definitions. "
                        f"The LLM API rejected the tool schemas with this error: {error_text}\n"
                        f"Common cause: using 'required': True on individual properties instead of "
                        f"a 'required': ['field1', 'field2'] array at the object level.",
                        websocket
                    )
                    if fixed:
                        await self.send_ui_render(websocket, [
                            Alert(message="Tool schema fixed. Agent restarted — please try your message again.", variant="info").to_json()
                        ])
                    else:
                        await self.send_ui_render(websocket, [
                            Alert(message="Auto-fix could not resolve the schema issue. Try refining the agent.", variant="warning").to_json()
                        ])
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status", "status": "done", "message": ""
                    }))
                except Exception as fix_err:
                    logger.warning(f"Auto-fix for schema error failed: {fix_err}")
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status", "status": "done", "message": ""
                    }))
                    await self.send_ui_render(websocket, [
                        Alert(message=f"Tool schema error and auto-fix failed: {error_text}", variant="error", title="Error").to_json()
                    ])
            else:
                # Clear the 'thinking' spinner so the UI doesn't hang
                await self._safe_send(websocket, json.dumps({
                    "type": "chat_status",
                    "status": "done",
                    "message": ""
                }))
                # Show a user-friendly error message
                if "424" in error_text or "Failed Dependency" in error_text or "Repository Not Found" in error_text:
                    error_text = f"The LLM server cannot find the configured model '{self.llm_model}'. Please verify the model name in your .env file and that the vLLM server has this model loaded."
                elif "502" in error_text or "Bad Gateway" in error_text:
                    error_text = "The AI model returned a 502 Bad Gateway error. It may be overloaded or restarting. Please try again in a moment."
                elif "504" in error_text or "Gateway Time-out" in error_text:
                    error_text = "The AI model timed out. It may be overloaded or still warming up. Please try again in a moment."
                elif "timeout" in error_text.lower():
                    error_text = "Request timed out waiting for the AI model. Please try again."
                await self.send_ui_render(websocket, [
                    Alert(message=error_text, variant="error", title="Error").to_json()
                ])
        finally:
            heartbeat_task.cancel()

    def _accumulate_usage(self, chat_id: Optional[str], usage):
        """Accumulate LLM token usage for a conversation.

        Args:
            chat_id: Conversation identifier. Skipped if None.
            usage: The ``usage`` object from an OpenAI-compatible response.
        """
        if not usage or not chat_id:
            return
        if chat_id not in self.token_usage:
            self.token_usage[chat_id] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        self.token_usage[chat_id]["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
        self.token_usage[chat_id]["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
        self.token_usage[chat_id]["total_tokens"] += getattr(usage, "total_tokens", 0) or 0
        logger.info(
            f"Token usage for chat {chat_id}: {self.token_usage[chat_id]}"
        )

    async def _call_llm(self, websocket, messages, tools_desc=None, temperature=None):
        """Helper to call LLM with retries and exponential backoff.

        Only retries on transient errors (502, 503, 504). Fails fast on
        non-transient errors like 424 (model not found) or 401 (auth).

        Returns:
            Tuple of (message, usage) where usage is the token usage object
            from the API response, or (None, None) on complete failure.
        """
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                kwargs = {
                    "model": self.llm_model,
                    "messages": messages
                }
                if tools_desc:
                    kwargs["tools"] = tools_desc
                    kwargs["tool_choice"] = "auto"
                if temperature is not None:
                    kwargs["temperature"] = temperature

                response = await asyncio.to_thread(
                    self.llm_client.chat.completions.create,
                    **kwargs
                )
                usage = getattr(response, "usage", None)
                return response.choices[0].message, usage
            except Exception as e:
                error_str = str(e)
                is_transient = any(code in error_str for code in ["502", "503", "504", "Bad Gateway", "Service Unavailable", "Connection", "timeout"])
                is_fatal = any(code in error_str for code in ["424", "401", "403", "Repository Not Found", "Invalid username"])

                logger.warning(f"LLM Attempt {attempt}/{self.MAX_RETRIES} failed: {e}")

                # Don't retry fatal errors — they won't resolve with retries
                if is_fatal:
                    logger.error(f"Fatal LLM error (no retry): {e}")
                    raise e

                if attempt == self.MAX_RETRIES:
                    raise e

                # Exponential backoff: 1s, 2s, 4s, 8s
                backoff = min(2 ** (attempt - 1), 8)
                if is_transient:
                    logger.info(f"Transient error detected, retrying in {backoff}s...")
                await asyncio.sleep(backoff)
        return None, None

    async def _generate_tool_summary(self, websocket, messages, chat_id=None, user_id=None):
        """
        Generate an LLM summary/analysis of accumulated tool results.
        Called when the Re-Act loop ends (max turns or completion) to ensure
        the user always gets a meaningful summary rather than a 'stopped' message.
        """
        if not self.llm_client:
            return None

        try:
            # Build a summary-focused prompt from the conversation so far
            summary_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are summarizing the results of tool operations that were just performed. "
                        "Provide a concise, insightful analysis of what was accomplished and the key findings. "
                        "Focus on actionable insights, important numbers, and recommendations. "
                        "Do NOT mention internal details like tool names, turn counts, or system mechanics. "
                        "Write as if you are presenting results to the user directly. "
                        "Keep it to 2-4 sentences."
                    ),
                },
            ]

            # Include relevant parts of the conversation (last several messages)
            for msg in messages[-8:]:
                if isinstance(msg, dict):
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role in ("user", "tool", "assistant") and content:
                        # Truncate long tool outputs
                        if len(str(content)) > 1500:
                            content = str(content)[:1500] + "..."
                        summary_messages.append({"role": role if role != "tool" else "user", "content": str(content)})

            summary_messages.append({
                "role": "user",
                "content": "Based on the tool results above, provide a brief summary and analysis."
            })

            response = await asyncio.to_thread(
                self.llm_client.chat.completions.create,
                model=self.llm_model,
                messages=summary_messages,
                max_tokens=300,
            )
            self._accumulate_usage(chat_id, getattr(response, "usage", None))

            summary_text = response.choices[0].message.content or ""
            summary_text = summary_text.strip()

            if summary_text:
                return [
                    Card(title="Summary", content=[
                        Text(content=summary_text, variant="body")
                    ]).to_json()
                ]

        except Exception as e:
            logger.warning(f"Failed to generate tool summary: {e}")

        return None

    # =========================================================================
    # CONSTANTS
    # =========================================================================

    MAX_RETRIES = 5
    RETRY_BACKOFF = [1.0, 2.0, 4.0, 8.0]  # exponential backoff

    async def execute_single_tool(self, websocket, tool_call, tool_to_agent: Dict, chat_id: str = None, user_id: str = None) -> Optional[MCPResponse]:
        """Execute a single tool call and render its UI components. Returns the Result object."""
        tool_name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
        except json.JSONDecodeError:
            args = {}

        # System-level security block (proactive security review)
        agent_id = tool_to_agent.get(tool_name)
        agent_flags = self.security_flags.get(agent_id, {}) if agent_id else {}
        if agent_id and tool_name in agent_flags and agent_flags[tool_name].get("blocked"):
            reason = agent_flags[tool_name].get("reason", "Security threat detected")
            err_msg = f"Tool '{tool_name}' is system-blocked: {reason}"
            logger.warning(f"Security block: agent={agent_id} tool={tool_name}")
            alert = Alert(message=err_msg, variant="error")
            await self.send_ui_render(websocket, [alert.to_json()])
            return MCPResponse(
                error={"message": err_msg, "retryable": False},
                ui_components=[alert.to_json()]
            )

        # Permission enforcement gate (RFC 8693 delegation)
        if user_id and agent_id and not self.tool_permissions.is_tool_allowed(user_id, agent_id, tool_name):
            err_msg = f"Tool '{tool_name}' is restricted for this agent. Update permissions in the sidebar to enable it."
            logger.warning(f"Permission denied: user={user_id} agent={agent_id} tool={tool_name}")
            alert = Alert(message=err_msg, variant="warning")
            await self.send_ui_render(websocket, [alert.to_json()])
            return MCPResponse(
                error={"message": err_msg, "retryable": False},
                ui_components=[alert.to_json()]
            )

        # Map file paths if chat_id provided
        if chat_id:
            args = self._map_file_paths(chat_id, args, user_id=user_id)
            args["session_id"] = chat_id
            if user_id:
                args["user_id"] = user_id

        # Inject per-user credentials (E2E encrypted — only agent can decrypt)
        if user_id and agent_id:
            creds = self.credential_manager.get_agent_credentials_encrypted(user_id, agent_id)
            if creds:
                args["_credentials"] = creds
                args["_credentials_encrypted"] = True

        if not agent_id or (agent_id not in self.agents and agent_id not in self.a2a_clients):
            err_msg = f"No agent available for tool '{tool_name}'"
            await self.send_ui_render(websocket, [
                Alert(message=err_msg, variant="error").to_json()
            ])
            return MCPResponse(error={"message": err_msg})

        # RFC 8693 delegation: generate a scoped token excluding system-blocked tools
        # The delegation token constrains what the agent can do even if it's compromised
        if user_id and agent_id:
            delegation_token = await self._get_delegation_token(websocket, agent_id, user_id)
            if delegation_token:
                args["_delegation_token"] = delegation_token

        result = await self._execute_with_retry(websocket, agent_id, tool_name, args)

        # Don't render tool results immediately — the caller (handle_chat_message)
        # batches all tool results into a single collapsible section.
        if result and result.error:
            # Errors are still shown immediately so the user knows something went wrong
            err_msg = result.error.get('message', 'Unknown error')
            await self.send_ui_render(websocket, [
                Alert(message=f"Tool '{tool_name}' failed: {err_msg}", variant="error").to_json()
            ])

            # Auto-fix: if this is a draft agent, attempt to fix the tool error automatically
            if agent_id and hasattr(self, 'lifecycle_manager'):
                try:
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status", "status": "fixing",
                        "message": f"Auto-fixing tool '{tool_name}'..."
                    }))
                    fixed = await self.lifecycle_manager.auto_fix_tool_error(
                        agent_id, tool_name, err_msg, websocket
                    )
                    if fixed:
                        logger.info(f"Auto-fix attempted for draft agent {agent_id} tool '{tool_name}'")
                        await self.send_ui_render(websocket, [
                            Alert(message=f"Auto-fix applied for '{tool_name}'. Agent restarted — try again.", variant="info").to_json()
                        ])
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status", "status": "thinking",
                        "message": "Continuing after fix..."
                    }))
                except Exception as e:
                    logger.warning(f"Auto-fix failed for {agent_id}: {e}")
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status", "status": "thinking",
                        "message": "Continuing..."
                    }))

        return result

    async def execute_parallel_tools(self, websocket, tool_calls, tool_to_agent: Dict, chat_id: str = None, user_id: str = None) -> List[Optional[MCPResponse]]:
        """Execute multiple tool calls in parallel. Returns list of Results."""
        tasks = []
        tool_names = []

        for tc in tool_calls:
            tool_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}

            # Map file paths if chat_id provided
            if chat_id:
                args = self._map_file_paths(chat_id, args, user_id=user_id)
                args["session_id"] = chat_id
                if user_id:
                    args["user_id"] = user_id

            agent_id = tool_to_agent.get(tool_name)

            # Inject per-user credentials (E2E encrypted — only agent can decrypt)
            if user_id and agent_id:
                creds = self.credential_manager.get_agent_credentials_encrypted(user_id, agent_id)
                if creds:
                    args["_credentials"] = creds
                    args["_credentials_encrypted"] = True

            # System-level security block for parallel tools
            agent_flags = self.security_flags.get(agent_id, {}) if agent_id else {}
            if agent_id and tool_name in agent_flags and agent_flags[tool_name].get("blocked"):
                reason = agent_flags[tool_name].get("reason", "Security threat detected")
                err_msg = f"Tool '{tool_name}' is system-blocked: {reason}"
                logger.warning(f"Security block (parallel): agent={agent_id} tool={tool_name}")
                async def _dummy_security_error(msg=err_msg):
                    return MCPResponse(
                        error={"message": msg, "retryable": False},
                        ui_components=[Alert(message=msg, variant="error").to_json()]
                    )
                tasks.append(_dummy_security_error())
                tool_names.append(tool_name)
                continue

            # Permission check for parallel tools
            if user_id and agent_id and not self.tool_permissions.is_tool_allowed(user_id, agent_id, tool_name):
                err_msg = f"Tool '{tool_name}' is restricted for this agent. Update permissions in the sidebar to enable it."
                logger.warning(f"Permission denied (parallel): user={user_id} agent={agent_id} tool={tool_name}")
                async def _dummy_permission_error():
                    # Return an MCPResponse with error but ALSO a UI component so it's visible in the result
                    return MCPResponse(
                        error={"message": err_msg, "retryable": False},
                        ui_components=[Alert(message=err_msg, variant="error").to_json()]
                    )
                tasks.append(_dummy_permission_error())
                tool_names.append(tool_name)
                continue

            if agent_id and (agent_id in self.agents or agent_id in self.a2a_clients):
                tasks.append(self._execute_with_retry(websocket, agent_id, tool_name, args))
                tool_names.append(tool_name)
            else:
                 # Create a dummy task that returns an error result
                 async def _dummy_error():
                     return MCPResponse(error={"message": f"No agent for {tool_name}"})
                 tasks.append(_dummy_error())
                 tool_names.append(tool_name)

        if not tasks:
            return []

        # Execute all tools concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results — don't render here, caller batches into collapsible
        final_results = []
        error_components = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                err_res = MCPResponse(error={"message": str(result)})
                final_results.append(err_res)
                error_components.append(Alert(message=f"Tool error: {str(result)}", variant="error").to_json())
            else:
                final_results.append(result)
                if result and result.error:
                    error_components.append(Alert(message=f"Tool '{tool_names[i]}' failed: {result.error.get('message')}", variant="error").to_json())

        # Only render errors immediately — successful results are batched by caller
        if error_components:
            await self.send_ui_render(websocket, error_components)

        # Auto-fix: attempt to fix draft agent tool errors
        if hasattr(self, 'lifecycle_manager'):
            for i, result in enumerate(final_results):
                if result and result.error:
                    t_name = tool_names[i] if i < len(tool_names) else None
                    a_id = tool_to_agent.get(t_name) if t_name else None
                    if a_id:
                        try:
                            await self._safe_send(websocket, json.dumps({
                                "type": "chat_status", "status": "fixing",
                                "message": f"Auto-fixing tool '{t_name}'..."
                            }))
                            await self.lifecycle_manager.auto_fix_tool_error(
                                a_id, t_name, result.error.get('message', ''), websocket
                            )
                            await self.send_ui_render(websocket, [
                                Alert(message=f"Auto-fix applied for '{t_name}'. Agent restarted — try again.", variant="info").to_json()
                            ])
                            await self._safe_send(websocket, json.dumps({
                                "type": "chat_status", "status": "thinking",
                                "message": "Continuing after fix..."
                            }))
                        except Exception as e:
                            logger.warning(f"Auto-fix failed for {a_id}: {e}")
                            await self._safe_send(websocket, json.dumps({
                                "type": "chat_status", "status": "thinking",
                                "message": "Continuing..."
                            }))

        return final_results

    async def _execute_with_retry(
        self, websocket, agent_id: str, tool_name: str, args: Dict,
        max_retries: int = None
    ) -> Optional[MCPResponse]:
        """Execute a tool call with up to max_retries attempts.

        On retryable errors, sends status updates to the UI and waits
        with exponential backoff before trying again.
        """
        if max_retries is None:
            max_retries = self.MAX_RETRIES

        last_result = None

        for attempt in range(1, max_retries + 1):
            result = await self.execute_tool_and_wait(agent_id, tool_name, args)
            last_result = result

            # Success: no error at all
            if result and not result.error:
                if attempt > 1:
                    logger.info(f"Tool '{tool_name}' succeeded on attempt {attempt}/{max_retries}")
                return result

            # Check if error is retryable
            is_retryable = True
            error_msg = "Unknown error"
            if result and result.error:
                is_retryable = result.error.get("retryable", True)
                error_msg = result.error.get("message", "Unknown error")

            if not is_retryable:
                logger.info(f"Tool '{tool_name}' failed with non-retryable error: {error_msg}")
                return result

            # Retryable error — try again if attempts remain
            if attempt < max_retries:
                backoff = self.RETRY_BACKOFF[attempt - 1] if attempt - 1 < len(self.RETRY_BACKOFF) else 2.0
                logger.warning(
                    f"Tool '{tool_name}' failed (attempt {attempt}/{max_retries}): {error_msg}. "
                    f"Retrying in {backoff}s..."
                )
                # Notify UI about the retry
                try:
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "retrying",
                        "message": f"Tool '{tool_name.replace('_', ' ').title()}' failed. "
                                   f"Retrying... (attempt {attempt + 1}/{max_retries})"
                    }))
                except Exception:
                    pass  # Don't let status notification failure break retry logic

                await asyncio.sleep(backoff)
            else:
                logger.error(
                    f"Tool '{tool_name}' failed after {max_retries} attempts: {error_msg}"
                )

        return last_result

    async def execute_tool_and_wait(self, agent_id: str, tool_name: str, args: Dict, timeout: float = 30.0) -> Optional[MCPResponse]:
        """Send an MCP tool call to an agent and wait for the response.

        Strategy: Always try WebSocket first (fastest, bidirectional), then
        fall back to A2A JSON-RPC if WebSocket is unavailable or fails.
        """
        # Try WebSocket first
        if agent_id in self.agents:
            result = await self._execute_via_websocket(agent_id, tool_name, args, timeout)
            if result and not (result.error and result.error.get("retryable")):
                return result
            # WebSocket failed with a retryable error — fall back to A2A if available
            if agent_id in self.a2a_clients:
                logger.info(f"WebSocket call failed for {agent_id}, falling back to A2A")
                return await self._execute_via_a2a(agent_id, tool_name, args, timeout)
            return result

        # No WebSocket connection — try A2A
        if agent_id in self.a2a_clients:
            return await self._execute_via_a2a(agent_id, tool_name, args, timeout)

        # Agent has a known URL but no active connection — attempt WebSocket reconnect then A2A
        if agent_id in self.agent_urls:
            base_url = self.agent_urls[agent_id]
            logger.info(f"Agent {agent_id} disconnected, attempting WebSocket reconnect to {base_url}")
            try:
                await self.discover_agent(base_url)
                if agent_id in self.agents:
                    return await self._execute_via_websocket(agent_id, tool_name, args, timeout)
            except Exception as e:
                logger.debug(f"WebSocket reconnect failed for {agent_id}: {e}")

            # WebSocket reconnect failed — try A2A discovery as fallback
            logger.info(f"WebSocket reconnect failed for {agent_id}, attempting A2A fallback")
            try:
                await self.discover_a2a_agent(base_url, notify_ui=False)
                if agent_id in self.a2a_clients:
                    return await self._execute_via_a2a(agent_id, tool_name, args, timeout)
            except Exception as e:
                logger.debug(f"A2A fallback discovery failed for {agent_id}: {e}")

        return MCPResponse(
            request_id=f"req_{tool_name}_{int(time.time() * 1000)}",
            error={"message": f"Agent {agent_id} not connected via WebSocket or A2A", "retryable": False},
        )

    async def _execute_via_websocket(self, agent_id: str, tool_name: str, args: Dict, timeout: float = 30.0) -> Optional[MCPResponse]:
        """Execute a tool call via WebSocket (internal agents)."""
        request_id = f"req_{tool_name}_{int(time.time() * 1000)}"

        request = MCPRequest(
            request_id=request_id,
            method="tools/call",
            params={"name": tool_name, "arguments": args}
        )

        # Create a future for the response
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[request_id] = future

        try:
            agent_ws = self.agents[agent_id]
            await agent_ws.send(request.to_json())
            logger.info(f"Sent tool call (WS): {tool_name} → {agent_id}")

            result = await asyncio.wait_for(future, timeout=timeout)
            return result

        except asyncio.TimeoutError:
            logger.error(f"Tool call timed out: {tool_name}")
            return MCPResponse(request_id=request_id,
                               error={"message": "Tool call timed out", "retryable": True})
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return MCPResponse(request_id=request_id,
                               error={"message": str(e), "retryable": True})
        finally:
            self.pending_requests.pop(request_id, None)

    async def _execute_via_a2a(self, agent_id: str, tool_name: str, args: Dict, timeout: float = 30.0) -> Optional[MCPResponse]:
        """Execute a tool call via A2A JSON-RPC (external agents)."""
        import uuid
        from a2a.types import (
            Message as A2AMessage, DataPart, Part, Role, Task, TaskState,
        )
        from shared.a2a_bridge import a2a_response_to_mcp_response

        request_id = f"a2a_{tool_name}_{int(time.time() * 1000)}"
        client = self.a2a_clients[agent_id]

        # Build A2A message with tool call in DataPart
        msg = A2AMessage(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[Part(root=DataPart(data={
                "method": "tools/call",
                "name": tool_name,
                "arguments": {
                    **{k: v for k, v in args.items() if not k.startswith("_")},
                    **({
                        "_credentials": args["_credentials"],
                        "_credentials_encrypted": args["_credentials_encrypted"],
                    } if args.get("_credentials_encrypted") else {}),
                },
            }))],
        )

        # Forward delegation token in request metadata
        delegation_token = args.get("_delegation_token")

        try:
            logger.info(f"Sent tool call (A2A): {tool_name} → {agent_id}")

            # Use the A2A client to send the message
            # The client returns an async iterator of events
            context = None
            if delegation_token:
                from a2a.client.client import ClientCallContext
                context = ClientCallContext(
                    metadata={"authorization": f"Bearer {delegation_token}"},
                )

            last_task = None
            last_message = None
            async for event in await asyncio.wait_for(
                client.send_message(msg, context=context),
                timeout=timeout,
            ):
                if isinstance(event, tuple):
                    # ClientEvent = (Task, UpdateEvent | None)
                    task, _ = event
                    last_task = task
                else:
                    # Direct Message response
                    last_message = event

            if last_task:
                return a2a_response_to_mcp_response(last_task, request_id)
            elif last_message:
                return a2a_response_to_mcp_response(last_message, request_id)
            else:
                return MCPResponse(
                    request_id=request_id,
                    error={"message": "No response from A2A agent", "retryable": True},
                )

        except asyncio.TimeoutError:
            logger.error(f"A2A tool call timed out: {tool_name}")
            return MCPResponse(request_id=request_id,
                               error={"message": "A2A tool call timed out", "retryable": True})
        except Exception as e:
            logger.error(f"A2A tool execution error: {e}")
            return MCPResponse(request_id=request_id,
                               error={"message": str(e), "retryable": True})

    async def _get_delegation_token(self, websocket, agent_id: str, user_id: str) -> Optional[str]:
        """Generate an RFC 8693 delegation token scoped to safe, allowed tools.

        The scope excludes system-blocked tools (from security review) and
        user-disabled tools (from permission manager), so the agent can only
        act within the constrained tool set.
        """
        try:
            card = self.agent_cards.get(agent_id)
            if not card:
                return None
            session = self.ui_sessions.get(websocket, {})
            raw_token = session.get("_raw_token")
            if not raw_token:
                return None

            # Build the effective scope: only tools that pass BOTH checks
            agent_flags = self.security_flags.get(agent_id, {})
            allowed_tools = []
            for skill in card.skills:
                # Exclude system-blocked
                if skill.id in agent_flags and agent_flags[skill.id].get("blocked"):
                    continue
                # Exclude user-disabled
                if not self.tool_permissions.is_tool_allowed(user_id, agent_id, skill.id):
                    continue
                allowed_tools.append(skill.id)

            # Get enabled scope names for the delegation token
            enabled_scopes = self.tool_permissions.get_enabled_scope_names(user_id, agent_id)

            result = await self.delegation.exchange_token_for_agent(
                raw_token, agent_id, allowed_tools, user_id, enabled_scopes
            )
            if "error" in result:
                logger.warning(f"Delegation token exchange failed for agent={agent_id}: {result}")
                return None
            return result.get("access_token")
        except Exception as e:
            logger.warning(f"Delegation token generation failed: {e}")
            return None

    # =========================================================================
    # UI HELPERS
    # =========================================================================

    async def _safe_send(self, websocket, data: str) -> bool:
        """Send data over a websocket, returning False if the connection is closed."""
        try:
            if hasattr(websocket, "send_text"):
                # FastAPI WebSocket
                await websocket.send_text(data)
            else:
                # websockets library WebSocket
                await websocket.send(data)
            return True
        except Exception as e:
            logger.debug(f"Failed to send message (connection likely closed): {e}")
            return False

    async def _broadcast_user_history(self):
        """Send each connected UI client their own user's recent chat history.

        Groups clients by user_id to avoid redundant DB queries when the
        same user has multiple tabs open.
        """
        if not self.ui_clients:
            return

        clients_by_user: Dict[str, list] = {}
        for client in self.ui_clients:
            uid = self._get_user_id(client)
            clients_by_user.setdefault(uid, []).append(client)

        tasks = []
        for uid, clients in clients_by_user.items():
            history_list = self.history.get_recent_chats(user_id=uid)
            msg = json.dumps({"type": "history_list", "chats": history_list})
            for c in clients:
                tasks.append(self._safe_send(c, msg))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def send_ui_render(self, websocket, components: List):
        """Send a UIRender message to a UI client, adapted via ROTE."""
        adapted = self.rote.adapt(websocket, components)
        msg = UIRender(components=adapted)
        await self._safe_send(websocket, msg.to_json())

    @staticmethod
    def _sanitize_tool_schema(schema: dict) -> dict:
        """Fix common agent-generated schema issues before sending to the LLM.

        Addresses: property-level "required": true/false (invalid in OpenAI tool
        schemas) — must be an array at the object level instead.
        """
        if not isinstance(schema, dict):
            return {"type": "object", "properties": {}}

        schema = dict(schema)  # shallow copy
        props = schema.get("properties")
        if isinstance(props, dict):
            required_fields = list(schema.get("required", []) if isinstance(schema.get("required"), list) else [])
            cleaned_props = {}
            for key, val in props.items():
                if isinstance(val, dict):
                    val = dict(val)  # shallow copy
                    prop_req = val.pop("required", None)
                    # If a property had "required": true, promote to object-level required array
                    if prop_req is True and key not in required_fields:
                        required_fields.append(key)
                    # Recurse for nested object properties
                    if val.get("type") == "object" and "properties" in val:
                        val = Orchestrator._sanitize_tool_schema(val)
                    cleaned_props[key] = val
                else:
                    cleaned_props[key] = val
            schema["properties"] = cleaned_props
            if required_fields:
                schema["required"] = required_fields
            elif "required" in schema and not isinstance(schema["required"], list):
                del schema["required"]

        # Ensure top-level type
        if "type" not in schema:
            schema["type"] = "object"

        return schema

    def _is_draft_agent(self, agent_id: str) -> bool:
        """Check if an agent_id belongs to a non-live draft agent."""
        if hasattr(self, 'lifecycle_manager'):
            draft = self.lifecycle_manager._get_draft_by_agent_id(agent_id)
            if draft and draft["status"] != "live":
                return True
        return False

    async def send_dashboard(self, websocket):
        """Send the initial dashboard view."""
        user_id = self._get_user_id(websocket)
        ownership_map = {o["agent_id"]: o for o in self.history.db.get_all_agent_ownership()}
        agent_list = []
        for agent_id, card in self.agent_cards.items():
            # Hide draft agents that aren't live yet — they only appear in the Drafts tab
            if self._is_draft_agent(agent_id):
                continue
            available_tools = [s.id for s in card.skills]
            scopes = self.tool_permissions.get_agent_scopes(user_id, agent_id)
            tool_scope_map = self.tool_permissions.get_tool_scope_map(agent_id)
            permissions = self.tool_permissions.get_effective_permissions(
                user_id, agent_id, available_tools
            )
            ownership = ownership_map.get(agent_id, {})
            entry = {
                "id": card.agent_id,
                "name": card.name,
                "description": card.description,
                "tools": available_tools,
                "tool_descriptions": {s.id: s.description for s in card.skills},
                "scopes": scopes,
                "tool_scope_map": tool_scope_map,
                "permissions": permissions,
                "security_flags": self.security_flags.get(agent_id, {}),
                "status": "connected",
                "owner_email": ownership.get("owner_email"),
                "is_public": bool(ownership.get("is_public", False)),
            }
            if getattr(card, 'metadata', None):
                entry["metadata"] = card.metadata
            agent_list.append(entry)

        # Calculate total available tools for this user based on permissions
        total_tools = 0
        for agent in agent_list:
            if "permissions" in agent:
                total_tools += sum(1 for v in agent["permissions"].values() if v)
            else:
                total_tools += len(agent["tools"])

        await self._safe_send(websocket, json.dumps({
            "type": "system_config",
            "config": {
                "agents": agent_list,
                "total_tools": total_tools
            }
        }))

    async def send_agent_list(self, websocket):
        """Send list of connected agents."""
        user_id = self._get_user_id(websocket)
        ownership_map = {o["agent_id"]: o for o in self.history.db.get_all_agent_ownership()}
        agents = []
        for agent_id, card in self.agent_cards.items():
            # Hide draft agents that aren't live yet
            if self._is_draft_agent(agent_id):
                continue
            available_tools = [s.id for s in card.skills]
            scopes = self.tool_permissions.get_agent_scopes(user_id, agent_id)
            tool_scope_map = self.tool_permissions.get_tool_scope_map(agent_id)
            permissions = self.tool_permissions.get_effective_permissions(
                user_id, agent_id, available_tools
            )
            ownership = ownership_map.get(agent_id, {})
            entry = {
                "id": card.agent_id,
                "name": card.name,
                "description": card.description,
                "tools": [{"name": s.id, "description": s.description} for s in card.skills],
                "scopes": scopes,
                "tool_scope_map": tool_scope_map,
                "permissions": permissions,
                "security_flags": self.security_flags.get(agent_id, {}),
                "status": "connected",
                "owner_email": ownership.get("owner_email"),
                "is_public": bool(ownership.get("is_public", False)),
            }
            if getattr(card, 'metadata', None):
                entry["metadata"] = card.metadata
            agents.append(entry)

        await self._safe_send(websocket, json.dumps({
            "type": "agent_list",
            "agents": agents
        }))

    # =========================================================================
    # SERVER
    # =========================================================================

    async def handle_ui_connection_fastapi(self, websocket: WebSocket):
        """Handle a UI client WebSocket connection using FastAPI."""
        await websocket.accept()
        self.ui_clients.append(websocket)
        self._registered_events[id(websocket)] = asyncio.Event()
        logger.info(f"UI client connected (total: {len(self.ui_clients)})")
        try:
            while True:
                message = await websocket.receive_text()
                # Fire as task so the receive loop stays responsive —
                # long-running handlers (chat, condense, combine, paginate)
                # won't block button clicks or cancel_task messages.
                asyncio.create_task(self._safe_handle_ui_message(websocket, message))
        except WebSocketDisconnect:
            logger.info("UI client disconnected")
        except Exception as e:
            # Only log interesting errors
            if "ConnectionClosed" not in str(e):
                logger.error(f"WebSocket error: {e}")
        finally:
            if websocket in self.ui_clients:
                self.ui_clients.remove(websocket)
            if websocket in self.ui_sessions:
                del self.ui_sessions[websocket]
            self._chat_locks.pop(id(websocket), None)
            self._registered_events.pop(id(websocket), None)
            self.rote.cleanup(websocket)
            logger.info(f"UI client session cleaned up (total: {len(self.ui_clients)})")

    async def handle_ui_connection(self, websocket, path=None):
        """Handle a UI client WebSocket connection (legacy websockets lib)."""
        self.ui_clients.append(websocket)
        self._registered_events[id(websocket)] = asyncio.Event()
        logger.info(f"UI client connected (total: {len(self.ui_clients)})")
        try:
            async for message in websocket:
                asyncio.create_task(self._safe_handle_ui_message(websocket, message))
        except websockets.exceptions.ConnectionClosed:
            logger.info("UI client disconnected")
        finally:
            if websocket in self.ui_clients:
                self.ui_clients.remove(websocket)
            if websocket in self.ui_sessions:
                del self.ui_sessions[websocket]
            self._chat_locks.pop(id(websocket), None)
            self._registered_events.pop(id(websocket), None)
            self.rote.cleanup(websocket)
            logger.info(f"UI client session cleaned up (total: {len(self.ui_clients)})")

    async def start(self):
        logger.info(f"Orchestrator starting on port {PORT}")

        # Auto-discover agents (continuous monitor)
        agent_port = int(os.getenv("AGENT_PORT", 8003))
        max_agents = int(os.getenv("MAX_AGENTS", 10))
        asyncio.create_task(self._monitor_agents(agent_port, max_agents))

        # Import WebSocket protocol docs for OpenAPI description
        from orchestrator.models import WS_PROTOCOL_DOCS

        # OpenAPI tag metadata for grouping endpoints in /docs
        tags_metadata = [
            {"name": "Chat", "description": "Chat session management — create, list, load, delete chats and send messages."},
            {"name": "Components", "description": "Saved UI component management — save, list, delete, combine, and condense components."},
            {"name": "Agents", "description": "Connected agent discovery and information."},
            {"name": "System", "description": "System dashboard and configuration."},
            {"name": "Auth", "description": "Authentication token proxy (Keycloak BFF)."},
            {"name": "Files", "description": "File upload and download."},
        ]

        # Create FastAPI app with rich OpenAPI documentation
        app = FastAPI(
            title="AstralBody Orchestrator API",
            description=(
                "REST API and WebSocket gateway for the AstralBody multi-agent system.\n\n"
                "## Overview\n\n"
                "The orchestrator provides two communication channels:\n\n"
                "1. **REST API** (documented below) — Request/response endpoints for CRUD operations\n"
                "2. **WebSocket** (`ws://<host>:<port>/ws`) — Real-time streaming for chat responses and live updates\n\n"
                "Both channels share the same authentication (Keycloak JWT Bearer tokens).\n\n"
                "---\n"
                + WS_PROTOCOL_DOCS
            ),
            version="1.0.0",
            openapi_tags=tags_metadata,
            docs_url="/docs",
            redoc_url="/redoc",
        )

        # CORS — configurable via CORS_ORIGINS env var (comma-separated)
        cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[o.strip() for o in cors_origins],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Store Orchestrator instance on app.state so REST API routes can access it
        app.state.orchestrator = self

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.handle_ui_connection_fastapi(websocket)

        # Mount REST API routers
        from orchestrator.api import chat_router, component_router, agent_router, dashboard_router, draft_router, voice_router
        from orchestrator.auth import auth_router
        app.include_router(chat_router)
        app.include_router(component_router)
        app.include_router(agent_router)
        app.include_router(draft_router)
        app.include_router(dashboard_router)
        app.include_router(auth_router)
        app.include_router(voice_router)

        # Mount A2A JSON-RPC server (orchestrator as A2A agent)
        try:
            from orchestrator.a2a_orchestrator_executor import setup_orchestrator_a2a
            setup_orchestrator_a2a(app, self)
            logger.info(f"A2A JSON-RPC endpoint mounted at /a2a/")
        except Exception as e:
            logger.warning(f"A2A server setup skipped: {e}")

        # Discover external A2A agents from env var
        external_agents = os.getenv("A2A_EXTERNAL_AGENTS", "")
        if external_agents:
            async def _discover_external():
                await asyncio.sleep(3)  # Wait for server to start
                for url in external_agents.split(","):
                    url = url.strip()
                    if url:
                        await self.discover_a2a_agent(url)
            asyncio.create_task(_discover_external())

        # Start combined server
        config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
        server = uvicorn.Server(config)
        logger.info(f"Consolidated server (Gateway) listening on http://0.0.0.0:{PORT}")
        logger.info(f"API docs available at http://localhost:{PORT}/docs")
        logger.info(f"A2A endpoint: http://localhost:{PORT}/a2a/")
        await server.serve()

    async def _monitor_agents(self, start_port: int, max_ports: int = 10):
        """Continuously monitor and discover agents across a range of ports."""
        logger.info(f"Starting agent monitor for ports {start_port} to {start_port + max_ports - 1}...")

        while True:
            for port in range(start_port, start_port + max_ports):
                agent_url = f"http://localhost:{port}"
                try:
                    # This will connect if not already connected
                    await self.discover_agent(agent_url)
                except Exception as e:
                    pass
            
            await asyncio.sleep(5)  # Check every 5 seconds

    async def summarize_chat_title(self, chat_id: str, message: str, user_id: str = 'legacy'):
        """Generate a concise title for the chat using LLM."""
        if not self.llm_client:
            return

        try:
            response = await asyncio.to_thread(
                self.llm_client.chat.completions.create,
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": "Summarize the following user request into a concise 3-5 word title. Return ONLY the title, no quotes or other text."},
                    {"role": "user", "content": message}
                ],
                max_tokens=20
            )
            title = response.choices[0].message.content.strip().strip('"')
            
            # Update history and notify UI
            self.history.update_chat_title(chat_id, title, user_id=user_id)
            
            # Broadcast update (each user gets their own history)
            await self._broadcast_user_history()
                
        except Exception as e:
            logger.error(f"Failed to summarize chat title: {e}")

    # =========================================================================
    # AUTHENTICATION
    # =========================================================================

    async def validate_token(self, token: str) -> Optional[Dict]:
        """Validate JWT token against KeyCloak."""
        # 0. Mock Auth Bypass
        if os.getenv("VITE_USE_MOCK_AUTH") == "true":
            # Accept any token for mock auth (for testing)
            # Check if it's the old dev-token or new JWT format
            if token == "dev-token":
                logger.info("Mock Auth: Validated dev-token")
                return {
                    "sub": "dev-user-id",
                    "preferred_username": "DevUser",
                    "email": "dev@local",
                    "realm_access": {"roles": ["admin", "user"]}
                }
            else:
                # Try to decode as JWT for mock
                try:
                    import base64
                    import json
                    # Extract payload from JWT
                    parts = token.split('.')
                    if len(parts) == 3:
                        # Decode payload
                        payload_b64 = parts[1]
                        # Add padding if needed
                        payload_b64 += '=' * ((4 - len(payload_b64) % 4) % 4)
                        payload_json = base64.b64decode(payload_b64).decode('utf-8')
                        payload = json.loads(payload_json)
                        return payload
                except:
                    # If decoding fails, return default mock user
                    pass
                # Default mock user
                logger.info("Mock Auth: Accepting any token as dev-user-id")
                return {
                    "sub": "dev-user-id",
                    "preferred_username": "DevUser",
                    "realm_access": {"roles": ["admin", "user"]},
                    "resource_access": {
                        "astral-frontend": {"roles": ["admin", "user"]}
                    }
                }

        try:
            authority = os.getenv("VITE_KEYCLOAK_AUTHORITY")
            expected_client = os.getenv("VITE_KEYCLOAK_CLIENT_ID")
            
            if not authority or not expected_client:
                logger.warning("Auth not configured (VITE_KEYCLOAK_AUTHORITY/CLIENT_ID missing)")
                return None

            # Fetch JWKS
            jwks_url = f"{authority}/protocol/openid-connect/certs"
            async with aiohttp.ClientSession() as session:
                async with session.get(jwks_url) as resp:
                    jwks = await resp.json()

            # Verify token — skip strict audience check since Keycloak
            # confidential clients set aud="account", not the client_id.
            # We validate azp (authorized party) instead.
            payload = jose_jwt.decode(
                token,
                jwks,
                algorithms=["RS256"],
                options={"verify_aud": False, "verify_at_hash": False}
            )

            # Verify authorized party matches our client
            azp = payload.get("azp")
            if azp and azp != expected_client:
                logger.warning(f"Token azp '{azp}' does not match expected client '{expected_client}'")
                return None

            # Extract Roles
            client_id = os.getenv("VITE_KEYCLOAK_CLIENT_ID", "astral-frontend")
            roles = payload.get("realm_access", {}).get("roles", [])
            if "resource_access" in payload:
                if client_id in payload["resource_access"]:
                    client_roles = payload["resource_access"][client_id].get("roles", [])
                    roles.extend(client_roles)
                if "account" in payload["resource_access"]:
                    account_roles = payload["resource_access"]["account"].get("roles", [])
                    roles.extend(account_roles)
            
            logger.debug(f"Token validation: extracted roles {roles} from payload keys {list(payload.keys())}")
            
            if "admin" not in roles and "user" not in roles:
                logger.warning(f"Token unauthorized (Requires 'admin' or 'user' role). Found roles: {roles}")
                return None

            return payload
        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            return None

    def _get_user_id(self, websocket) -> str:
        """Extract user_id from the UI session, default to 'legacy' if not authenticated."""
        if websocket not in self.ui_sessions:
            return 'legacy'
        user_data = self.ui_sessions[websocket]
        # user_data is the JWT payload, sub is the subject (user ID)
        return user_data.get('sub', 'legacy')

    def _save_user_profile(self, user_data: Dict) -> None:
        """Persist user profile from JWT claims to the database."""
        user_id = user_data.get("sub")
        if not user_id or user_id == "legacy":
            return
        try:
            # Extract roles from JWT claims
            roles = list(set(
                user_data.get("realm_access", {}).get("roles", []) +
                user_data.get("resource_access", {}).get(
                    os.getenv("VITE_KEYCLOAK_CLIENT_ID", "astral-frontend"), {}
                ).get("roles", [])
            ))
            self.history.db.upsert_user(
                user_id=user_id,
                email=user_data.get("email"),
                username=user_data.get("preferred_username"),
                display_name=user_data.get("name") or user_data.get("preferred_username"),
                roles=roles,
            )
        except Exception as e:
            logger.warning(f"Failed to save user profile for {user_id}: {e}")


if __name__ == "__main__":
    orch = Orchestrator()
    asyncio.run(orch.start())
