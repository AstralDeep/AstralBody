#!/usr/bin/env python3
"""Forecaster Agent — A2A agent wrapping the external Timeseries Forecaster service."""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.forecaster.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class ForecasterAgent(BaseA2AAgent):
    """Agent for the user-supplied Timeseries Forecaster service."""

    agent_id = "forecaster-1"
    service_name = "Forecaster"
    description = (
        "Trains and runs forecasts on tabular time-series data using a user-configured "
        "Timeseries Forecaster deployment. Each user supplies their own service URL and "
        "API key; credentials never leave the user's session in plaintext."
    )
    skill_tags = ["forecasting", "timeseries", "ml", "external"]

    card_metadata = {
        "required_credentials": [
            {
                "key": "FORECASTER_URL",
                "label": "Forecaster Service URL",
                "description": "Base URL of your Timeseries Forecaster deployment (e.g. https://forecaster.ai.uky.edu/).",
                "required": True,
                "type": "api_key",
                "placeholder": "https://forecaster.ai.uky.edu/",
            },
            {
                "key": "FORECASTER_API_KEY",
                "label": "Forecaster API Key",
                "description": "Personal API key for the Forecaster service. Used as a Bearer token.",
                "required": True,
                "type": "api_key",
            },
        ],
        # 015-external-ai-agents — tools subject to the FR-026 concurrency cap.
        "long_running_tools": ["start_training_job"],
    }

    def __init__(self, port: int = None):
        super().__init__(MCPServer(), port=port, port_env_var="FORECASTER_AGENT_PORT")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Timeseries Forecaster Agent")
    parser.add_argument("--port", type=int, default=None, help="Port to run the agent on")
    args = parser.parse_args()

    agent = ForecasterAgent(port=args.port)
    asyncio.run(agent.run())
