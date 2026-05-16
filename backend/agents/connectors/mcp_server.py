"""
MCP Server for the Claude Connectors Agent — US-22.

Registers all 14 connector tools across office, dev, runtime, and creative domains.
"""
import asyncio
import inspect
import os
import sys
import json
import logging
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from shared.protocol import MCPRequest, MCPResponse

from agents.connectors.mcp_tools_office import OFFICE_TOOL_REGISTRY
from agents.connectors.mcp_tools_dev import DEV_TOOL_REGISTRY
from agents.connectors.mcp_tools_runtime import RUNTIME_TOOL_REGISTRY
from agents.connectors.mcp_tools_creative import CREATIVE_TOOL_REGISTRY

logger = logging.getLogger("ConnectorsMCPServer")

# Merge all tool registries
TOOL_REGISTRY = {}
TOOL_REGISTRY.update(OFFICE_TOOL_REGISTRY)
TOOL_REGISTRY.update(DEV_TOOL_REGISTRY)
TOOL_REGISTRY.update(RUNTIME_TOOL_REGISTRY)
TOOL_REGISTRY.update(CREATIVE_TOOL_REGISTRY)


class ConnectorsMCPServer:
    """MCP server that routes tool calls to registered connector functions."""

    def __init__(self):
        self.tools = TOOL_REGISTRY

    def get_tool_list(self) -> list:
        """Return list of available tools with their schemas."""
        return [
            {
                "name": name,
                "description": info["description"],
                "input_schema": info.get("input_schema", {"type": "object", "properties": {}})
            }
            for name, info in self.tools.items()
        ]

    async def process_request(self, request: MCPRequest) -> MCPResponse:
        """Route raw MCPRequest to the correct tool function."""
        tool_name = request.tool_name
        tool = self.tools.get(tool_name)

        if not tool:
            return MCPResponse(
                id=request.id,
                error=json.dumps({
                    "message": f"Tool '{tool_name}' not found",
                    "available": list(self.tools.keys()),
                }),
                success=False,
            )

        try:
            handler = tool["function"]
            args = request.arguments or {}

            # Support both sync and async handlers
            if inspect.iscoroutinefunction(handler):
                result = await handler(args)
            else:
                result = handler(args)

            return MCPResponse(
                id=request.id,
                result=json.dumps(result),
                success=True,
            )
        except Exception as e:
            logger.exception(f"Connectors tool '{tool_name}' failed: {e}")
            return MCPResponse(
                id=request.id,
                error=json.dumps({"message": str(e), "tool": tool_name}),
                success=False,
            )