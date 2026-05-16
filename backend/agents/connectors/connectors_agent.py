"""
Claude Connectors Agent — US-22

Bundles 14 connector tools as MCP tools:
- Office: Excel, PowerPoint, Word, Outlook, Pitch Templates
- Dev: Code Review, Constitution Critique
- Runtime: Adaptive Intelligence
- Creative: Blender, Adobe CC, Canva, Dashboards, Graphs, Design (stubs)
"""
import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.connectors.mcp_server import ConnectorsMCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

DEFAULT_PORT = 8017


class ConnectorsAgent(BaseA2AAgent):
    agent_id = "connectors-1"
    service_name = "Claude Connectors Agent"
    description = (
        "Specialized agent for office productivity, developer tools, "
        "and creative connectors (Excel, PowerPoint, Word, Outlook, "
        "pitch templates, code review, constitution critique, and more)."
    )

    def __init__(self, port: int = DEFAULT_PORT):
        super().__init__(ConnectorsMCPServer(), port=port)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Claude Connectors Agent')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    agent = ConnectorsAgent(port=args.port)
    asyncio.run(agent.run())