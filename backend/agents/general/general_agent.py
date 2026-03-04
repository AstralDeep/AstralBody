"""
General Agent — A2A-compliant specialist agent with MCP tool execution.

Runs a FastAPI server with:
- /.well-known/agent-card.json (legacy A2A discovery)
- /a2a/.well-known/agent-card.json (official A2A v0.3 discovery)
- /a2a/ (A2A JSON-RPC endpoint)
- /agent (WebSocket for MCP tool calls from orchestrator)
- /health (health check)
"""
import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.general.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

DEFAULT_PORT = 8003


class GeneralAgent(BaseA2AAgent):
    """Unified specialist agent with patient, system, and search capabilities."""

    agent_id = "general-1"
    service_name = "General Agent"
    description = "Unified agent with patient data, system monitoring, and search capabilities."

    def __init__(self, port: int = DEFAULT_PORT):
        super().__init__(MCPServer(), port=port)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='General Agent')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    agent = GeneralAgent(port=args.port)
    asyncio.run(agent.run())
