"""
Grant Searching Agent package for AstralBody system.

Monitors NSF, NIH, DOE, and DoD for funding opportunities
and matches them to UKy CAAI capabilities.
"""

from agents.grants.grants_agent import GrantsAgent
from agents.grants.mcp_server import MCPServer
from agents.grants.mcp_tools import (
    search_grants,
    get_grant_details,
    match_grants_to_caai,
    get_caai_profile,
    analyze_funding_trends,
    TOOL_REGISTRY
)

__all__ = [
    'GrantsAgent',
    'MCPServer',
    'search_grants',
    'get_grant_details',
    'match_grants_to_caai',
    'get_caai_profile',
    'analyze_funding_trends',
    'TOOL_REGISTRY'
]

__version__ = '1.0.0'
