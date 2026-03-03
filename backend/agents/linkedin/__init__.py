"""
LinkedIn Engagement Driver agent for AstralBody system.

Analyzes and drives engagement on the UKy CAAI LinkedIn page.
"""

from agents.linkedin.linkedin_agent import LinkedInAgent
from agents.linkedin.mcp_server import MCPServer
from agents.linkedin.mcp_tools import (
    analyze_linkedin_posts,
    get_page_metrics,
    get_content_suggestions,
    draft_linkedin_post,
    generate_weekly_digest,
    suggest_engagement_actions,
    TOOL_REGISTRY
)

__all__ = [
    'LinkedInAgent',
    'MCPServer',
    'analyze_linkedin_posts',
    'get_page_metrics',
    'get_content_suggestions',
    'draft_linkedin_post',
    'generate_weekly_digest',
    'suggest_engagement_actions',
    'TOOL_REGISTRY'
]

__version__ = '1.0.0'
