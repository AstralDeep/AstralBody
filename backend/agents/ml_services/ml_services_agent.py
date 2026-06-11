#!/usr/bin/env python3
"""ML Services Agent — A2A agent consolidating CLASSify, Forecaster, and LLM-Factory."""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.ml_services.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class MlServicesAgent(BaseA2AAgent):
    """Agent for the user-supplied CLASSify, Forecaster, and LLM-Factory services."""

    agent_id = "ml-services-1"
    service_name = "ML Services"
    description = (
        "One agent for three user-configured external ML services; each service is "
        "an optional credential bundle (URL + API key) and credentials never leave "
        "the user's session in plaintext. "
        "CLASSify — trains and evaluates classifiers on tabular CSV datasets. "
        "Workflow: classify_submit_dataset (returns column types) -> set_column_types "
        "-> propose_training_config (renders an interactive picker; its Submit button "
        "triggers classify_start_training_job automatically) -> "
        "classify_start_training_job. "
        "Forecaster — trains and runs forecasts on tabular time-series data. "
        "Workflow: forecaster_submit_dataset -> set_column_roles -> "
        "forecaster_start_training_job. "
        "LLM-Factory — routes chat completions, embeddings, and audio transcription "
        "through an OpenAI-compatible Router deployment (list_models, "
        "chat_with_model, create_embedding, transcribe_audio). "
        "Do NOT call read_spreadsheet or other file-reading tools before the "
        "submit_dataset step of either training pipeline — the tools read and "
        "validate the CSV themselves."
    )
    skill_tags = ["machine-learning", "classification", "timeseries", "embeddings", "transcription"]

    # Feature 029 (FR-008): credentials saved while the predecessor agents
    # were live are ECIES-encrypted to THEIR keys. BaseA2AAgent loads these
    # ids' key files (backend/data/agent_keys/<id>.pem) as decryption
    # fallbacks so saved credentials keep working without a re-save.
    predecessor_agent_ids = ("classify-1", "forecaster-1", "llm-factory-1")

    card_metadata = {
        "required_credentials": [
            {
                "key": "CLASSIFY_URL",
                "label": "CLASSify Service URL",
                "description": "Base URL of your CLASSify deployment (e.g. https://classify.ai.uky.edu/).",
                "required": False,
                "type": "api_key",
                "placeholder": "https://classify.ai.uky.edu/",
            },
            {
                "key": "CLASSIFY_API_KEY",
                "label": "CLASSify API Key",
                "description": "Personal API key issued by your CLASSify administrator. Used as a Bearer token.",
                "required": False,
                "type": "api_key",
            },
            {
                "key": "FORECASTER_URL",
                "label": "Forecaster Service URL",
                "description": "Base URL of your Timeseries Forecaster deployment (e.g. https://forecaster.ai.uky.edu/).",
                "required": False,
                "type": "api_key",
                "placeholder": "https://forecaster.ai.uky.edu/",
            },
            {
                "key": "FORECASTER_API_KEY",
                "label": "Forecaster API Key",
                "description": "Personal API key for the Forecaster service. Used as a Bearer token.",
                "required": False,
                "type": "api_key",
            },
            {
                "key": "LLM_FACTORY_URL",
                "label": "LLM-Factory Service URL",
                "description": "Base URL of your LLM-Factory Router deployment (e.g. https://llm-factory.ai.uky.edu/).",
                "required": False,
                "type": "api_key",
                "placeholder": "https://llm-factory.ai.uky.edu/",
            },
            {
                "key": "LLM_FACTORY_API_KEY",
                "label": "LLM-Factory API Key",
                "description": "Personal API key for the LLM-Factory Router. Used as a Bearer token on every request.",
                "required": False,
                "type": "api_key",
            },
        ],
        # 015-external-ai-agents — tools the orchestrator must subject to the
        # FR-026 concurrency cap. Each acquires a slot on dispatch and releases
        # it when the agent's JobPoller emits a terminal ToolProgress.
        "long_running_tools": ["classify_start_training_job", "forecaster_start_training_job"],
    }

    def __init__(self, port: int = None):
        """Start the agent over the union MCP server.

        Args:
            port: Explicit port; falls back to ``ML_SERVICES_AGENT_PORT``.
        """
        super().__init__(MCPServer(), port=port, port_env_var="ML_SERVICES_AGENT_PORT")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ML Services Agent")
    parser.add_argument("--port", type=int, default=None, help="Port to run the agent on")
    args = parser.parse_args()

    agent = MlServicesAgent(port=args.port)
    asyncio.run(agent.run())
