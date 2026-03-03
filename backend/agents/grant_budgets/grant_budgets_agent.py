#!/usr/bin/env python3
"""
Grant Budgets Agent — A2A-compliant specialist agent for grant budget estimation.

Provides tools for:
- Analyzing grant cover letters for budget signals (secure, in-memory)
- Suggesting categorized budget line items (CGS/PAPPG)
- Calculating salary/FTE, travel, equipment, and F&A costs
- Generating CGS-templated budgets with year-by-year breakdowns
- Referencing NSF PAPPG, NIH, and institutional budget guidelines
"""
import asyncio
import json
import os
import sys
import logging
import socket
from typing import Set, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.protocol import (
    Message, RegisterAgent, MCPRequest, MCPResponse,
    AgentCard, AgentSkill
)
from agents.grant_budgets.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('GrantBudgetsAgent')


class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/.well-known/agent-card.json" not in record.getMessage()

# Filter uvicorn access logs if they exist
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

BASE_PORT = 8003  # Starting port for agents
MAX_PORT_OFFSET = 10  # Maximum ports to check


def find_available_port(start_port: int = BASE_PORT, max_offset: int = MAX_PORT_OFFSET) -> int:
    """Find an available port starting from start_port."""
    for offset in range(max_offset):
        port = start_port + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                if s.connect_ex(('localhost', port)) != 0:
                    logger.info(f"Port {port} appears available")
                    return port
        except Exception:
            continue
    logger.warning(f"No available port found in range {start_port}-{start_port + max_offset - 1}")
    return start_port + 5  # Default offset for grant budgets agent


class GrantBudgetsAgent:
    """Specialist agent for grant budget estimation and CGS-templated budget generation."""

    def __init__(self, port: int = None):
        self.agent_id = "grant-budgets-1"
        self.service_name = "Grant Budgets Agent"
        self.host = os.getenv("HOST", "0.0.0.0")

        # Determine port: command line arg > env var > dynamic discovery
        if port is not None:
            self.port = port
        else:
            env_port = os.getenv("GRANT_BUDGETS_AGENT_PORT")
            if env_port:
                self.port = int(env_port)
            else:
                self.port = find_available_port()

        self.mcp_server = MCPServer()
        self.orchestrator_connections: Set[WebSocket] = set()
        self.card = self._build_agent_card()

    def _build_agent_card(self) -> AgentCard:
        skills = []
        for name, info in self.mcp_server.tools.items():
            desc = info.get("description", "No description provided")
            skills.append(AgentSkill(
                name=name,
                description=desc,
                id=name,
                input_schema=info.get("input_schema"),
                tags=["grants", "budget", "financial", "nsf", "nih",
                      "cgs", "pappg", "f&a", "salary", "ospa", "pdo",
                      "research-admin", "forms", "deadlines"]
            ))

        return AgentCard(
            name=self.service_name,
            description=(
                "Financial specialist agent for grant budget estimation and "
                "UKy research administration Q&A. Analyzes cover letters for "
                "budget signals, suggests line items, calculates salary/FTE, "
                "travel, equipment, and F&A costs, generates CGS-templated "
                "budgets, and answers OSPA/CGS/PDO policy questions with "
                "source citations."
            ),
            agent_id=self.agent_id,
            version="1.0.0",
            skills=skills
        )

    async def handle_websocket(self, websocket: WebSocket):
        await websocket.accept()
        logger.info(f"Orchestrator connected via WebSocket")
        self.orchestrator_connections.add(websocket)

        try:
            register_msg = RegisterAgent(agent_card=self.card)
            await websocket.send_text(register_msg.to_json())
            logger.info(f"Sent RegisterAgent with {len(self.card.skills)} skills")

            async for message in websocket.iter_text():
                try:
                    parsed = Message.from_json(message)
                    if isinstance(parsed, MCPRequest):
                        await self.handle_mcp_request(websocket, parsed)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

        except WebSocketDisconnect:
            logger.info("Orchestrator disconnected")
        finally:
            self.orchestrator_connections.discard(websocket)

    async def handle_mcp_request(self, ws: WebSocket, msg: MCPRequest):
        logger.info(f"Processing MCP Request: {msg.method} params={msg.params}")
        response = await asyncio.to_thread(self.mcp_server.process_request, msg)
        await ws.send_text(response.to_json())
        logger.info(f"Sent response for {msg.request_id}")

    async def run(self):
        app = FastAPI(title=f"Agent: {self.service_name}")

        @app.get("/.well-known/agent-card.json")
        async def get_agent_card():
            return self.card.to_dict()

        @app.get("/health")
        async def health_check():
            return {"status": "ok", "agent_id": self.agent_id,
                    "tools": len(self.mcp_server.tools)}

        app.add_api_websocket_route("/agent", self.handle_websocket)

        logger.info(f"Starting {self.service_name} on http://{self.host}:{self.port}")
        logger.info(f"Agent Card: http://localhost:{self.port}/.well-known/agent-card.json")
        logger.info(f"Registered tools: {list(self.mcp_server.tools.keys())}")

        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="info", ws_max_size=50 * 1024 * 1024)
        server = uvicorn.Server(config)
        await server.serve()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Grant Budgets Agent')
    parser.add_argument('--port', type=int, default=None, help='Port to run the agent on (overrides dynamic discovery)')
    args = parser.parse_args()

    agent = GrantBudgetsAgent(port=args.port)
    asyncio.run(agent.run())
