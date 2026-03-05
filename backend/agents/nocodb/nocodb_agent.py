#!/usr/bin/env python3
"""
NocoDB Agent — A2A-compliant agent for managing NocoDB project management databases.
"""
import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.nocodb.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class NocodbAgent(BaseA2AAgent):
    """Agent for managing records, links, and attachments in NocoDB project management databases."""

    agent_id = "nocodb-1"
    service_name = "NocoDB"
    description = (
        "Manages records in NocoDB tables. Can list, search, create, update, "
        "and delete records, manage linked relations between tables, and upload "
        "file attachments. Connects to any NocoDB instance via API token."
    )
    skill_tags = ["database", "nocodb", "project-management", "records"]

    card_metadata = {
        "required_credentials": [
            {
                "key": "NOCODB_API_TOKEN",
                "label": "NocoDB API Token",
                "description": "API token (xc-token) for authenticating with your NocoDB instance",
                "required": True,
                "type": "api_key"
            },
            {
                "key": "NOCODB_BASE_URL",
                "label": "NocoDB Base URL",
                "description": "Base URL of your NocoDB instance (e.g. https://app.nocodb.com)",
                "required": True,
                "type": "api_key"
            },
            {
                "key": "NOCODB_BASE_ID",
                "label": "NocoDB Base ID",
                "description": "Default base/project identifier (e.g. p_abc123). Found in your NocoDB dashboard URL.",
                "required": True,
                "type": "api_key"
            }
        ]
    }

    def __init__(self, port: int = None):
        super().__init__(MCPServer(), port=port, port_env_var="NOCODB_AGENT_PORT")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='NocoDB Agent')
    parser.add_argument('--port', type=int, default=None, help='Port to run the agent on')
    args = parser.parse_args()

    agent = NocodbAgent(port=args.port)
    asyncio.run(agent.run())
