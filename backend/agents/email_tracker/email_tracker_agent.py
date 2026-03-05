#!/usr/bin/env python3
"""
Email Tracker — A2A-compliant agent.

Role: You are an expert Python Automation Engineer and DevOps specialist. Objective: Write a Python script that acts as an intelligent "Inbox Triage" agent. The script needs to interface with the Microsoft Graph API to manage Outlook and Microsoft To Do. Core Logic: Fetch: Authenticate via OAuth2 and retrieve emails received in the past 7 days from the user's Outlook inbox. Analyze (The "Agent" Component): Pass the body of these emails to an LLM (design the script to be modular so I can swap between OpenAI API, Anthropic, or a local Ollama endpoint). The LLM prompt should instruct it to scan for actionable requests, explicit "To Do" items, or deadlines, and return them as a structured JSON list. Deduplicate: Fetch the user's current active tasks from the default list in Microsoft To Do. Compare the extracted items against existing tasks to prevent duplicates (implement simple fuzzy matching or semantic similarity). Action: If an extracted item is not in the current list, create a new task in Microsoft To Do. Include a link to the original email in the task notes for context.
"""
import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.email_tracker.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class EmailTrackerAgent(BaseA2AAgent):
    """Role: You are an expert Python Automation Engineer and DevOps specialist. Objective: Write a Python script that acts as an intelligent "Inbox Triage" agent. The script needs to interface with the Microsoft Graph API to manage Outlook and Microsoft To Do. Core Logic: Fetch: Authenticate via OAuth2 and retrieve emails received in the past 7 days from the user's Outlook inbox. Analyze (The "Agent" Component): Pass the body of these emails to an LLM (design the script to be modular so I can swap between OpenAI API, Anthropic, or a local Ollama endpoint). The LLM prompt should instruct it to scan for actionable requests, explicit "To Do" items, or deadlines, and return them as a structured JSON list. Deduplicate: Fetch the user's current active tasks from the default list in Microsoft To Do. Compare the extracted items against existing tasks to prevent duplicates (implement simple fuzzy matching or semantic similarity). Action: If an extracted item is not in the current list, create a new task in Microsoft To Do. Include a link to the original email in the task notes for context."""

    agent_id = "email-tracker-1"
    service_name = "Email Tracker"
    description = """Role: You are an expert Python Automation Engineer and DevOps specialist. Objective: Write a Python script that acts as an intelligent "Inbox Triage" agent. The script needs to interface with the Microsoft Graph API to manage Outlook and Microsoft To Do. Core Logic: Fetch: Authenticate via OAuth2 and retrieve emails received in the past 7 days from the user's Outlook inbox. Analyze (The "Agent" Component): Pass the body of these emails to an LLM (design the script to be modular so I can swap between OpenAI API, Anthropic, or a local Ollama endpoint). The LLM prompt should instruct it to scan for actionable requests, explicit "To Do" items, or deadlines, and return them as a structured JSON list. Deduplicate: Fetch the user's current active tasks from the default list in Microsoft To Do. Compare the extracted items against existing tasks to prevent duplicates (implement simple fuzzy matching or semantic similarity). Action: If an extracted item is not in the current list, create a new task in Microsoft To Do. Include a link to the original email in the task notes for context."""
    skill_tags = []
    card_metadata = {
        "required_credentials": [
            {
                "key": "MS_GRAPH_CLIENT_ID",
                "label": "Microsoft Graph Client ID",
                "description": "OAuth 2.0 Client ID from Azure App Registration",
                "required": True,
                "type": "oauth_client_id"
            },
            {
                "key": "MS_GRAPH_CLIENT_SECRET",
                "label": "Microsoft Graph Client Secret",
                "description": "OAuth 2.0 Client Secret from Azure App Registration",
                "required": True,
                "type": "oauth_client_secret"
            },
            {
                "key": "MS_GRAPH_TENANT_ID",
                "label": "Microsoft Graph Tenant ID",
                "description": "Azure AD Tenant/Directory ID",
                "required": True,
                "type": "api_key"
            }
        ]
    }

    def __init__(self, port: int = None):
        super().__init__(MCPServer(), port=port, port_env_var="EMAIL_TRACKER_AGENT_PORT")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Email Tracker')
    parser.add_argument('--port', type=int, default=None, help='Port to run the agent on')
    args = parser.parse_args()

    agent = EmailTrackerAgent(port=args.port)
    asyncio.run(agent.run())
