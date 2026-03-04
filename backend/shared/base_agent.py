"""
BaseA2AAgent — Base class for all AstralBody agents with WebSocket + A2A dual transport.

Provides:
- WebSocket endpoint (/agent) for orchestrator communication (default internal transport)
- A2A JSON-RPC endpoint for external A2A-compliant clients
- Legacy agent card (/.well-known/agent-card.json) for backward compat
- Official A2A agent card (/.well-known/agent.json via A2AFastAPIApplication)
- Health check endpoint (/health)
- Agent-to-agent peer communication via WebSocket
"""
import asyncio
import json
import os
import sys
import logging
import time
import uuid
import socket
from typing import Set, Dict, Optional, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.protocol import (
    Message, RegisterAgent, MCPRequest, MCPResponse,
    AgentCard, AgentSkill
)
from shared.a2a_bridge import custom_card_to_a2a
from shared.a2a_executor import MCPAgentExecutor
from shared.a2a_security import A2ASecurityValidator


logger = logging.getLogger("BaseA2AAgent")

BASE_PORT = int(os.getenv("AGENT_PORT", "8003"))
MAX_PORT_OFFSET = 20


class EndpointFilter(logging.Filter):
    """Filter out noisy agent-card polling from access logs."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "/.well-known/agent-card.json" not in msg and "/.well-known/agent.json" not in msg


def find_available_port(start_port: int = BASE_PORT, max_offset: int = MAX_PORT_OFFSET) -> int:
    """Find an available port starting from start_port."""
    for offset in range(max_offset):
        port = start_port + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                if s.connect_ex(('localhost', port)) != 0:
                    return port
        except Exception:
            continue
    return start_port


class BaseA2AAgent:
    """Base class for all AstralBody agents with WebSocket + A2A dual transport.

    Subclasses must provide:
        - agent_id: Unique identifier (e.g. "general-1")
        - service_name: Human-readable name (e.g. "General Agent")
        - description: Agent description
        - mcp_server: An MCPServer instance with .tools and .process_request()

    Optional overrides:
        - skill_tags: Default tags to add to all skills
        - card_metadata: Extra metadata for the agent card (e.g. required_credentials)
    """

    agent_id: str = ""
    service_name: str = ""
    description: str = ""
    skill_tags: List[str] = []
    card_metadata: Dict[str, Any] = {}

    def __init__(self, mcp_server, port: int = None, port_env_var: str = None, default_port_offset: int = 0):
        """
        Args:
            mcp_server: The agent's MCPServer instance.
            port: Explicit port (from command line).
            port_env_var: Environment variable name for port (e.g. "WEATHER_AGENT_PORT").
            default_port_offset: Fallback offset from BASE_PORT if no port is found.
        """
        self.host = os.getenv("HOST", "0.0.0.0")
        self.mcp_server = mcp_server
        self.orchestrator_connections: Set[WebSocket] = set()

        # Port resolution: explicit > env var > dynamic discovery
        if port is not None:
            self.port = port
        elif port_env_var and os.getenv(port_env_var):
            self.port = int(os.getenv(port_env_var))
        else:
            self.port = find_available_port(BASE_PORT)

        # Build agent cards
        self.card = self._build_agent_card()

        # Peer connections for agent-to-agent communication
        self.peer_connections: Dict[str, Any] = {}  # agent_id -> websocket connection
        self.peer_pending: Dict[str, asyncio.Future] = {}  # request_id -> Future
        self._peer_registry: Dict[str, str] = {}  # agent_id -> ws_url

        # Security validator for A2A requests
        self._security_validator = A2ASecurityValidator()

        self._logger = logging.getLogger(self.__class__.__name__)

    def _build_agent_card(self) -> AgentCard:
        """Build custom AgentCard from registered MCP tools."""
        skills = []
        for name, info in self.mcp_server.tools.items():
            desc = info.get("description", "No description provided")
            tags = list(self.skill_tags) if self.skill_tags else []
            skills.append(AgentSkill(
                name=name,
                description=desc,
                id=name,
                input_schema=info.get("input_schema"),
                tags=tags,
                scope=info.get("scope", "tools:read"),
            ))

        return AgentCard(
            name=self.service_name,
            description=self.description,
            agent_id=self.agent_id,
            version="1.0.0",
            skills=skills,
            metadata=dict(self.card_metadata) if self.card_metadata else {},
        )

    def _build_a2a_card(self):
        """Build official A2A AgentCard from custom card."""
        base_url = f"http://{self.host}:{self.port}"
        return custom_card_to_a2a(self.card, base_url)

    async def handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket connection from orchestrator or peer agent."""
        await websocket.accept()
        self._logger.info("Connection established via WebSocket")
        self.orchestrator_connections.add(websocket)

        try:
            # Send registration with agent card
            register_msg = RegisterAgent(agent_card=self.card)
            await websocket.send_text(register_msg.to_json())
            self._logger.info(f"Sent RegisterAgent with {len(self.card.skills)} skills")

            async for message in websocket.iter_text():
                try:
                    parsed = Message.from_json(message)
                    if isinstance(parsed, MCPRequest):
                        await self.handle_mcp_request(websocket, parsed)
                    elif parsed.type == "peer_registry":
                        # Orchestrator broadcasting peer agent URLs
                        data = json.loads(message)
                        self._peer_registry = data.get("agents", {})
                        self._logger.info(f"Updated peer registry: {list(self._peer_registry.keys())}")
                except Exception as e:
                    self._logger.error(f"Error processing message: {e}")

        except WebSocketDisconnect:
            self._logger.info("Connection disconnected")
        finally:
            self.orchestrator_connections.discard(websocket)

    async def handle_mcp_request(self, ws: WebSocket, msg: MCPRequest):
        """Handle MCP request by dispatching to MCP server."""
        self._logger.info(f"Processing MCP Request: {msg.method}")
        response = await asyncio.to_thread(self.mcp_server.process_request, msg)
        await ws.send_text(response.to_json())
        self._logger.info(f"Sent response for {msg.request_id}")

    # =========================================================================
    # Agent-to-Agent Communication
    # =========================================================================

    async def connect_to_peer(self, agent_id: str, ws_url: str):
        """Connect to a peer agent via WebSocket for direct communication."""
        import websockets
        try:
            ws = await websockets.connect(ws_url, max_size=50 * 1024 * 1024)
            self.peer_connections[agent_id] = ws
            # Start listening for responses
            asyncio.create_task(self._peer_listen_loop(agent_id, ws))
            self._logger.info(f"Connected to peer agent: {agent_id} at {ws_url}")
        except Exception as e:
            self._logger.error(f"Failed to connect to peer {agent_id}: {e}")

    async def _peer_listen_loop(self, agent_id: str, ws):
        """Listen for responses from a peer agent."""
        import websockets.exceptions
        try:
            async for message in ws:
                try:
                    msg = Message.from_json(message)
                    if isinstance(msg, MCPResponse):
                        req_id = msg.request_id
                        if req_id in self.peer_pending:
                            self.peer_pending[req_id].set_result(msg)
                except Exception as e:
                    self._logger.error(f"Error processing peer message: {e}")
        except websockets.exceptions.ConnectionClosed:
            self._logger.info(f"Peer {agent_id} disconnected")
        finally:
            self.peer_connections.pop(agent_id, None)

    async def call_peer_tool(
        self,
        agent_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        delegation_token: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Optional[MCPResponse]:
        """Call a tool on a peer agent — WebSocket first, A2A fallback.

        Strategy:
        1. Try WebSocket (fast, bidirectional, preferred for internal agents)
        2. If WebSocket fails or is unavailable, fall back to A2A JSON-RPC
        """
        request_id = f"peer_{tool_name}_{int(time.time() * 1000)}"

        # Step 1: Try WebSocket
        ws_result = await self._call_peer_via_ws(
            agent_id, tool_name, arguments, delegation_token, request_id, timeout
        )
        if ws_result is not None:
            # If it succeeded or failed with a non-retryable error, return it
            if not (ws_result.error and ws_result.error.get("retryable")):
                return ws_result
            # Retryable error — try A2A fallback
            self._logger.info(f"WebSocket peer call to {agent_id} failed (retryable), trying A2A fallback")

        # Step 2: Fall back to A2A JSON-RPC
        a2a_result = await self._call_peer_via_a2a(
            agent_id, tool_name, arguments, delegation_token, request_id, timeout
        )
        if a2a_result is not None:
            return a2a_result

        # Both transports failed — return the WS error if we got one, else generic error
        if ws_result is not None:
            return ws_result
        return MCPResponse(
            request_id=request_id,
            error={"message": f"Cannot reach peer {agent_id} via WebSocket or A2A", "retryable": False},
        )

    async def _call_peer_via_ws(
        self,
        agent_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        delegation_token: Optional[str],
        request_id: str,
        timeout: float,
    ) -> Optional[MCPResponse]:
        """Attempt to call a peer tool via WebSocket. Returns None if no WS available."""
        # Auto-connect if needed
        if agent_id not in self.peer_connections:
            ws_url = self._peer_registry.get(agent_id)
            if ws_url:
                await self.connect_to_peer(agent_id, ws_url)

        if agent_id not in self.peer_connections:
            return None  # No WebSocket available — caller should try A2A

        request = MCPRequest(
            request_id=request_id,
            method="tools/call",
            params={"name": tool_name, "arguments": arguments},
        )
        if delegation_token:
            request.params["_delegation_token"] = delegation_token

        future = asyncio.get_event_loop().create_future()
        self.peer_pending[request_id] = future

        try:
            ws = self.peer_connections[agent_id]
            await ws.send(request.to_json())
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._logger.error(f"WebSocket peer call timed out: {tool_name} on {agent_id}")
            return MCPResponse(
                request_id=request_id,
                error={"message": "Peer tool call timed out via WebSocket", "retryable": True},
            )
        except Exception as e:
            self._logger.error(f"WebSocket peer call error: {e}")
            return MCPResponse(
                request_id=request_id,
                error={"message": str(e), "retryable": True},
            )
        finally:
            self.peer_pending.pop(request_id, None)

    async def _call_peer_via_a2a(
        self,
        agent_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        delegation_token: Optional[str],
        request_id: str,
        timeout: float,
    ) -> Optional[MCPResponse]:
        """Attempt to call a peer tool via A2A JSON-RPC. Returns None if no A2A endpoint."""
        peer_url = self._peer_registry.get(agent_id)
        if not peer_url:
            return None

        try:
            import httpx
            import uuid as uuid_mod
            from a2a.types import (
                Message as A2AMessage, DataPart, Part, Role,
            )
            from shared.a2a_bridge import a2a_response_to_mcp_response

            # Build A2A JSON-RPC request
            a2a_url = f"{peer_url}/a2a" if not peer_url.endswith("/a2a") else peer_url
            msg = A2AMessage(
                message_id=str(uuid_mod.uuid4()),
                role=Role.user,
                parts=[Part(root=DataPart(data={
                    "method": "tools/call",
                    "name": tool_name,
                    "arguments": {k: v for k, v in arguments.items() if not k.startswith("_")},
                }))],
            )

            # Send via httpx (simple JSON-RPC POST)
            headers = {"Content-Type": "application/json"}
            if delegation_token:
                headers["Authorization"] = f"Bearer {delegation_token}"

            jsonrpc_payload = {
                "jsonrpc": "2.0",
                "method": "message/send",
                "id": request_id,
                "params": {"message": msg.model_dump()},
            }

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(a2a_url, json=jsonrpc_payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            if "error" in data:
                return MCPResponse(
                    request_id=request_id,
                    error={"message": data["error"].get("message", "A2A error"), "retryable": False},
                )

            result_data = data.get("result", {})
            # Extract text/data from A2A response parts
            if isinstance(result_data, dict):
                return MCPResponse(request_id=request_id, result=result_data)
            return MCPResponse(request_id=request_id, result=str(result_data))

        except Exception as e:
            self._logger.error(f"A2A peer call to {agent_id} failed: {e}")
            return MCPResponse(
                request_id=request_id,
                error={"message": f"A2A fallback failed: {e}", "retryable": False},
            )

    # =========================================================================
    # Server Setup & Run
    # =========================================================================

    def _setup_a2a_routes(self, app: FastAPI):
        """Mount the A2A JSON-RPC application on the FastAPI app."""
        try:
            from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
            from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
            from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore

            a2a_card = self._build_a2a_card()
            executor = MCPAgentExecutor(self.mcp_server, self._security_validator)
            task_store = InMemoryTaskStore()
            handler = DefaultRequestHandler(
                agent_executor=executor,
                task_store=task_store,
            )

            a2a_app = A2AFastAPIApplication(
                agent_card=a2a_card,
                http_handler=handler,
            )

            # Mount at /a2a — this provides:
            #   /a2a/.well-known/agent-card.json (official A2A card)
            #   /a2a/ (JSON-RPC endpoint)
            a2a_fastapi = a2a_app.build()
            app.mount("/a2a", a2a_fastapi)

            self._logger.info(f"A2A JSON-RPC endpoint mounted at /a2a/")

        except Exception as e:
            self._logger.warning(f"A2A setup failed (SDK may not be installed): {e}")

    async def run(self):
        """Run the FastAPI server with both WebSocket and A2A endpoints."""
        app = FastAPI(title=f"Agent: {self.service_name}")

        # Suppress noisy access logs
        logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

        # Legacy A2A Agent Card endpoint (for existing orchestrator)
        @app.get("/.well-known/agent-card.json")
        async def get_agent_card():
            return self.card.to_dict()

        # Health check
        @app.get("/health")
        async def health_check():
            return {
                "status": "ok",
                "agent_id": self.agent_id,
                "tools": len(self.mcp_server.tools),
                "a2a_compliant": True,
            }

        # WebSocket for orchestrator/peer communication
        app.add_api_websocket_route("/agent", self.handle_websocket)

        # Mount A2A JSON-RPC endpoint
        self._setup_a2a_routes(app)

        self._logger.info(f"Starting {self.service_name} on http://{self.host}:{self.port}")
        self._logger.info(f"Legacy Card: http://localhost:{self.port}/.well-known/agent-card.json")
        self._logger.info(f"A2A Card:    http://localhost:{self.port}/a2a/.well-known/agent-card.json")
        self._logger.info(f"A2A RPC:     http://localhost:{self.port}/a2a/")
        self._logger.info(f"WebSocket:   ws://localhost:{self.port}/agent")
        self._logger.info(f"Registered tools: {list(self.mcp_server.tools.keys())}")

        config = uvicorn.Config(
            app, host=self.host, port=self.port,
            log_level="info", ws_max_size=50 * 1024 * 1024,
        )
        server = uvicorn.Server(config)
        await server.serve()
