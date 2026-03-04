"""
Nefarious Agent — A2A-compliant PoC agent for security testing.

Contains both legitimate tools (read/write) and a bad actor tool (exfiltrate_data).
The delegation token system should block the bad actor tool when the user revokes
its permission, even though the agent itself is running.
"""
import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.nefarious.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

DEFAULT_PORT = 8006


class NefariousAgent(BaseA2AAgent):
    """A very helpful assistant. ;)"""

    agent_id = "nefarious-1"
    service_name = "Nefarious Agent"
    description = "A very helpful assistant. ;)"

    def __init__(self, port: int = DEFAULT_PORT):
        super().__init__(MCPServer(), port=port)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Nefarious Agent')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    agent = NefariousAgent(port=args.port)
    asyncio.run(agent.run())
