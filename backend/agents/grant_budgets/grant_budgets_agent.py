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
import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.grant_budgets.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class GrantBudgetsAgent(BaseA2AAgent):
    """Specialist agent for grant budget estimation and CGS-templated budget generation."""

    agent_id = "grant-budgets-1"
    service_name = "Grant Budgets Agent"
    description = (
        "Financial specialist agent for grant budget estimation and "
        "UKy research administration Q&A. Analyzes cover letters for "
        "budget signals, suggests line items, calculates salary/FTE, "
        "travel, equipment, and F&A costs, generates CGS-templated "
        "budgets, and answers OSPA/CGS/PDO policy questions with "
        "source citations."
    )
    skill_tags = ["grants", "budget", "financial", "nsf", "nih",
                  "cgs", "pappg", "f&a", "salary", "ospa", "pdo",
                  "research-admin", "forms", "deadlines"]

    def __init__(self, port: int = None):
        super().__init__(MCPServer(), port=port, port_env_var="GRANT_BUDGETS_AGENT_PORT")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Grant Budgets Agent')
    parser.add_argument('--port', type=int, default=None, help='Port to run the agent on (overrides dynamic discovery)')
    args = parser.parse_args()

    agent = GrantBudgetsAgent(port=args.port)
    asyncio.run(agent.run())
