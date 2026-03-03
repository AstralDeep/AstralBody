"""
Journal Review Agent package for AstralBody system.

Evaluates scientific journals to recommend optimal publication venues
for research papers based on impact, topical fit, review timelines,
submission requirements, and audience relevance.
"""
from agents.journal_review.journal_review_agent import JournalReviewAgent
from agents.journal_review.mcp_server import MCPServer
from agents.journal_review.mcp_tools import (
    find_matching_journals,
    get_journal_profile,
    compare_journals,
    analyze_paper_fit,
    get_field_landscape,
    TOOL_REGISTRY,
)

__all__ = [
    'JournalReviewAgent',
    'MCPServer',
    'find_matching_journals',
    'get_journal_profile',
    'compare_journals',
    'analyze_paper_fit',
    'get_field_landscape',
    'TOOL_REGISTRY',
]
__version__ = '1.0.0'
