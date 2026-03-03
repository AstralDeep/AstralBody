"""
LinkedIn agent for AstralBody system.

Manages LinkedIn presence for the UKy Center for Applied AI —
publishing posts, engaging with content, and content strategy.
"""

from agents.linkedin.linkedin_agent import LinkedInAgent
from agents.linkedin.mcp_server import MCPServer
from agents.linkedin.mcp_tools import (
    get_my_profile,
    publish_post,
    react_to_post,
    comment_on_post,
    draft_linkedin_post,
    get_content_suggestions,
    suggest_engagement_actions,
    TOOL_REGISTRY
)

__all__ = [
    'LinkedInAgent',
    'MCPServer',
    'get_my_profile',
    'publish_post',
    'react_to_post',
    'comment_on_post',
    'draft_linkedin_post',
    'get_content_suggestions',
    'suggest_engagement_actions',
    'TOOL_REGISTRY'
]

__version__ = '2.0.0'
