#!/usr/bin/env python3
"""
Grant Searching Agent — A2A-compliant specialist agent for federal funding opportunities.

Provides tools for:
- Searching grants.gov (NSF, NIH, DOE, DoD)
- Grant opportunity detail retrieval
- Matching opportunities to UKy CAAI capabilities
- CAAI profile and expertise lookup
- Funding trend analysis
"""
import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.grants.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class GrantsAgent(BaseA2AAgent):
    """Specialist agent for searching federal funding opportunities."""

    agent_id = "grants-1"
    service_name = "Grant Searching Agent"
    description = (
        "Specialist agent for searching federal funding opportunities "
        "(NSF, NIH, DOE, DoD) and matching them to UKy Center for "
        "Applied AI capabilities. Focuses on large-scale start-up "
        "grants, center grants, and AI research infrastructure. "
        "Also supports drafting and gap-checking the NSF TechAccess: "
        "AI-Ready America (NSF 26-508) Kentucky Coordination Hub LOI "
        "and full proposal, plus program-officer questions, "
        "page-budget prioritization, and standalone deadline citation."
    )
    skill_tags = [
        "grants", "funding", "nsf", "nih", "doe", "dod", "research",
        "techaccess", "loi", "proposal", "techaccess26508",
    ]

    def __init__(self, port: int = None):
        super().__init__(MCPServer(), port=port, port_env_var="GRANTS_AGENT_PORT")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Grant Searching Agent')
    parser.add_argument('--port', type=int, default=None, help='Port to run the agent on (overrides dynamic discovery)')
    args = parser.parse_args()

    agent = GrantsAgent(port=args.port)
    asyncio.run(agent.run())
