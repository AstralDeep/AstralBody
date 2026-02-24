"""
Medical Agent — A2A-compliant specialist agent for medical professionals.
"""
import asyncio
import json
import os
import sys
import logging
from typing import Set, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.protocol import (
    Message, RegisterAgent, MCPRequest, MCPResponse,
    AgentCard, AgentSkill
)
from agents.medical.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('MedicalAgent')


class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/.well-known/agent-card.json" not in record.getMessage()

# Filter uvicorn access logs if they exist
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

DEFAULT_PORT = 8004

class MedicalAgent:
    """Specialist agent with medical data generation and analysis capabilities."""

    def __init__(self, port: int = DEFAULT_PORT):
        self.agent_id = "medical-1"
        self.service_name = "Medical Agent"
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = port
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
                tags=["medical", "analysis", "data"]
            ))

        return AgentCard(
            name=self.service_name,
            description="Specialist agent tailored for medical professionals, offering data analysis and synthetic patient data generation.",
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
        
        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="info", ws_max_size=50 * 1024 * 1024)
        server = uvicorn.Server(config)
        await server.serve()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Medical Agent')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    agent = MedicalAgent(port=args.port)
    asyncio.run(agent.run())
