#!/usr/bin/env python3
"""
LinkedIn Agent — A2A-compliant specialist agent for managing LinkedIn
presence for the UKy Center for Applied AI.

Provides tools for:
- Publishing posts as the authenticated LinkedIn user
- Reacting to and commenting on LinkedIn posts
- Drafting posts using CAAI content frames and brand voice
- Generating content suggestions across 6 content frames
- Actionable engagement growth recommendations
- Viewing authenticated user profile info
"""
import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.linkedin.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class LinkedInAgent(BaseA2AAgent):
    """Specialist agent for LinkedIn engagement analysis and content strategy."""

    agent_id = "linkedin-1"
    service_name = "LinkedIn Engagement Driver"
    description = (
        "Specialist agent for managing LinkedIn presence for CAAI. "
        "Publishes posts, reacts to and comments on content, drafts posts "
        "using content frames and brand voice, generates content ideas, "
        "and provides engagement growth recommendations."
    )
    skill_tags = ["linkedin", "social_media", "engagement", "content", "marketing", "caai"]
    card_metadata = {
        "required_credentials": [
            {"key": "LINKEDIN_CLIENT_ID", "label": "LinkedIn Client ID", "required": True},
            {"key": "LINKEDIN_CLIENT_SECRET", "label": "LinkedIn Client Secret", "required": True},
            {"key": "LINKEDIN_ORG_ID", "label": "LinkedIn Organization ID", "required": True},
        ]
    }

    def __init__(self, port: int = None):
        super().__init__(MCPServer(), port=port, port_env_var="LINKEDIN_AGENT_PORT")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='LinkedIn Engagement Driver Agent')
    parser.add_argument('--port', type=int, default=None, help='Port to run the agent on (overrides dynamic discovery)')
    args = parser.parse_args()

    agent = LinkedInAgent(port=args.port)
    asyncio.run(agent.run())
