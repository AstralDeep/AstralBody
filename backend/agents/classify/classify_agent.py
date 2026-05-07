#!/usr/bin/env python3
"""CLASSify Agent — A2A agent wrapping the external CLASSify classification service."""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.classify.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class ClassifyAgent(BaseA2AAgent):
    """Agent for the user-supplied CLASSify ML training service."""

    agent_id = "classify-1"
    service_name = "CLASSify"
    description = (
        "Trains and evaluates Random Forest classifiers on tabular CSV datasets via a "
        "user-configured CLASSify deployment. Each user supplies their own service URL "
        "and API key; credentials never leave the user's session in plaintext."
    )
    skill_tags = ["ml", "classification", "training", "external"]

    card_metadata = {
        "required_credentials": [
            {
                "key": "CLASSIFY_URL",
                "label": "CLASSify Service URL",
                "description": "Base URL of your CLASSify deployment (e.g. https://classify.ai.uky.edu/).",
                "required": True,
                "type": "api_key",
                "placeholder": "https://classify.ai.uky.edu/",
            },
            {
                "key": "CLASSIFY_API_KEY",
                "label": "CLASSify API Key",
                "description": "Personal API key issued by your CLASSify administrator. Used as a Bearer token.",
                "required": True,
                "type": "api_key",
            },
        ],
        # 015-external-ai-agents — tools the orchestrator must subject to the
        # FR-026 concurrency cap. Each acquires a slot on dispatch and releases
        # it when the agent's JobPoller emits a terminal ToolProgress.
        "long_running_tools": ["train_classifier", "retest_model"],
    }

    def __init__(self, port: int = None):
        super().__init__(MCPServer(), port=port, port_env_var="CLASSIFY_AGENT_PORT")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CLASSify Agent")
    parser.add_argument("--port", type=int, default=None, help="Port to run the agent on")
    args = parser.parse_args()

    agent = ClassifyAgent(port=args.port)
    asyncio.run(agent.run())
