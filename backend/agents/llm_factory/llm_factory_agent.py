#!/usr/bin/env python3
"""LLM-Factory Agent — A2A agent wrapping the external LLM-Factory proxy."""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.llm_factory.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class LlmFactoryAgent(BaseA2AAgent):
    """Agent for the user-supplied LLM-Factory model-proxy service."""

    agent_id = "llm-factory-1"
    service_name = "LLM-Factory"
    description = (
        "Routes chat completions, embeddings, and audio transcription through a "
        "user-configured LLM-Factory Router deployment (OpenAI-compatible reverse "
        "proxy). Each user supplies their own service URL and API key; credentials "
        "never leave the user's session in plaintext."
    )
    skill_tags = ["llm", "models", "chat", "embeddings", "transcription", "external"]

    card_metadata = {
        "required_credentials": [
            {
                "key": "LLM_FACTORY_URL",
                "label": "LLM-Factory Service URL",
                "description": "Base URL of your LLM-Factory Router deployment (e.g. https://llm-factory.ai.uky.edu/).",
                "required": True,
                "type": "api_key",
                "placeholder": "https://llm-factory.ai.uky.edu/",
            },
            {
                "key": "LLM_FACTORY_API_KEY",
                "label": "LLM-Factory API Key",
                "description": "Personal API key for the LLM-Factory Router. Used as a Bearer token on every request.",
                "required": True,
                "type": "api_key",
            },
        ]
    }

    def __init__(self, port: int = None):
        super().__init__(MCPServer(), port=port, port_env_var="LLM_FACTORY_AGENT_PORT")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="LLM-Factory Agent")
    parser.add_argument("--port", type=int, default=None, help="Port to run the agent on")
    args = parser.parse_args()

    agent = LlmFactoryAgent(port=args.port)
    asyncio.run(agent.run())
