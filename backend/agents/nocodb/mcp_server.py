#!/usr/bin/env python3
"""
MCP Server for NocoDB Agent — dispatches tool calls to tool functions.
"""
import os
import sys
import json
import inspect
import logging
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from shared.protocol import MCPRequest, MCPResponse
from agents.nocodb.mcp_tools import TOOL_REGISTRY

logger = logging.getLogger('NocodbAgentMCPServer')

RETRYABLE_EXCEPTIONS = (
    ConnectionError, TimeoutError, json.JSONDecodeError, OSError,
)

try:
    import requests
    RETRYABLE_EXCEPTIONS = RETRYABLE_EXCEPTIONS + (
        requests.exceptions.RequestException,
    )
except ImportError:
    pass

NON_RETRYABLE_EXCEPTIONS = (TypeError, KeyError, ValueError, AttributeError)


class MCPServer:
    """MCP server that routes tool/call requests to registered functions."""

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

    @staticmethod
    def _classify_error(exc: Exception) -> bool:
        """Return True if the error is retryable (transient), False otherwise."""
        if isinstance(exc, RETRYABLE_EXCEPTIONS):
            return True
        if isinstance(exc, NON_RETRYABLE_EXCEPTIONS):
            return False
        return True

    def process_request(self, request: MCPRequest) -> MCPResponse:
        """Process an MCP request and return a response."""
        if request.method == "tools/list":
            return MCPResponse(
                request_id=request.request_id,
                result={"tools": self.get_tool_list()}
            )

        if request.method == "tools/call":
            tool_name = request.params.get("name", "")
            arguments = request.params.get("arguments", {})

            if tool_name not in self.tools:
                return MCPResponse(
                    request_id=request.request_id,
                    error={"code": -32601, "message": f"Unknown tool: {tool_name}",
                           "retryable": False}
                )

            try:
                tool_fn = self.tools[tool_name]["function"]
                sig = inspect.signature(tool_fn)
                params = sig.parameters
                has_var_keyword = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
                )
                if not has_var_keyword:
                    arguments = {
                        k: v for k, v in arguments.items() if k in params
                    }
                result = tool_fn(**arguments)

                # A2UI component responses (new flat adjacency-list format)
                if isinstance(result, dict) and "_a2ui_components" in result:
                    data = result.get("_data")
                    return MCPResponse(
                        request_id=request.request_id,
                        result=data,
                        ui_components=result["_a2ui_components"],
                        a2ui_root_id=result.get("_a2ui_root_id", ""),
                    )

                if isinstance(result, dict) and "_ui_components" in result:
                    ui_comps = result["_ui_components"]
                    has_error = any(
                        isinstance(c, dict) and c.get("variant") == "error"
                        for c in ui_comps
                    )
                    if has_error:
                        error_msg = "Tool returned an error"
                        for c in ui_comps:
                            if isinstance(c, dict) and c.get("variant") == "error":
                                error_msg = c.get("message", error_msg)
                                break
                        logger.warning(f"Tool '{tool_name}' returned error alert: {error_msg}")
                        return MCPResponse(
                            request_id=request.request_id,
                            error={"code": -32000, "message": error_msg,
                                   "retryable": True},
                            ui_components=ui_comps
                        )

                    data = result.get("_data")
                    return MCPResponse(
                        request_id=request.request_id,
                        result=data,
                        ui_components=ui_comps
                    )

                return MCPResponse(
                    request_id=request.request_id,
                    result=result
                )

            except Exception as e:
                retryable = MCPServer._classify_error(e)
                logger.error(f"Tool '{tool_name}' raised {type(e).__name__}: {e} "
                             f"(retryable={retryable})")
                return MCPResponse(
                    request_id=request.request_id,
                    error={"code": -32603, "message": str(e),
                           "retryable": retryable}
                )

        return MCPResponse(
            request_id=request.request_id,
            error={"code": -32601, "message": f"Unknown method: {request.method}",
                   "retryable": False}
        )
