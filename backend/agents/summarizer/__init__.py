"""
Summarizer Agent package for AstralDeep system.

Provides text/URL summarization and two-document comparison tools.
"""

from agents.summarizer.summarizer_agent import SummarizerAgent
from agents.summarizer.mcp_server import MCPServer
from agents.summarizer.mcp_tools import (
    summarize_text,
    summarize_url,
    compare_documents,
    TOOL_REGISTRY,
)

__all__ = [
    'SummarizerAgent',
    'MCPServer',
    'summarize_text',
    'summarize_url',
    'compare_documents',
    'TOOL_REGISTRY',
]

__version__ = '1.0.0'
