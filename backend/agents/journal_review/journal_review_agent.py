#!/usr/bin/env python3
"""
Journal Review Agent — A2A-compliant specialist for evaluating scientific journals
and recommending optimal publication venues for research papers.

Provides tools for:
- Finding matching journals for a paper's topic, keywords, and abstract
- Detailed journal profiles (impact, scope, timelines, submission info)
- Side-by-side journal comparisons on key metrics
- Paper-to-journal fit scoring and analysis
- Field landscape overviews (top journals by discipline)
"""
import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.journal_review.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class JournalReviewAgent(BaseA2AAgent):
    """Specialist agent for evaluating scientific journals and recommending publication venues."""

    agent_id = "journal-review-1"
    service_name = "Journal Review Agent"
    description = (
        "Evaluates scientific journals to recommend optimal publication "
        "venues for research papers. Considers impact factor, topical fit, "
        "review timelines, acceptance rates, submission requirements, open "
        "access options, and audience relevance to help researchers choose "
        "where to submit their work."
    )
    skill_tags = ["journals", "publishing", "peer-review", "impact-factor",
                  "research", "academic", "science"]

    def __init__(self, port: int = None):
        super().__init__(MCPServer(), port=port, port_env_var="JOURNAL_REVIEW_AGENT_PORT")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Journal Review Agent')
    parser.add_argument('--port', type=int, default=None,
                        help='Port to run the agent on (overrides dynamic discovery)')
    args = parser.parse_args()

    agent = JournalReviewAgent(port=args.port)
    asyncio.run(agent.run())
