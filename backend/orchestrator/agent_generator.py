"""
Agent Code Generator for AstralBody.

Generates the 3 files needed for a new agent:
- {slug}_agent.py  — from template (not LLM)
- mcp_server.py    — from template (not LLM)
- mcp_tools.py     — LLM-generated tool implementations
"""
import os
import re
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List

from openai import OpenAI
from httpx import Timeout

from orchestrator.agent_spec import generate_llm_prompt_section

logger = logging.getLogger("AgentGenerator")


# ─── Templates ──────────────────────────────────────────────────────────

AGENT_PY_TEMPLATE = '''#!/usr/bin/env python3
"""
{service_name} — A2A-compliant agent.

{docstring_description}
"""
import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.base_agent import BaseA2AAgent
from agents.{slug}.mcp_server import MCPServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class {class_name}(BaseA2AAgent):
    """{docstring_description}"""

    agent_id = "{agent_id}"
    service_name = "{service_name}"
    description = """{escaped_description}"""
    skill_tags = {skill_tags}

    def __init__(self, port: int = None):
        super().__init__(MCPServer(), port=port, port_env_var="{port_env_var}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='{service_name}')
    parser.add_argument('--port', type=int, default=None, help='Port to run the agent on')
    args = parser.parse_args()

    agent = {class_name}(port=args.port)
    asyncio.run(agent.run())
'''

MCP_SERVER_TEMPLATE = '''#!/usr/bin/env python3
"""
MCP Server for {service_name} — dispatches tool calls to tool functions.
"""
import os
import sys
import json
import inspect
import logging
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from shared.protocol import MCPRequest, MCPResponse
from agents.{slug}.mcp_tools import TOOL_REGISTRY

logger = logging.getLogger('{class_name}MCPServer')

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
            {{
                "name": name,
                "description": info["description"],
                "input_schema": info.get("input_schema", {{"type": "object", "properties": {{}}}})
            }}
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
                result={{"tools": self.get_tool_list()}}
            )

        if request.method == "tools/call":
            tool_name = request.params.get("name", "")
            arguments = request.params.get("arguments", {{}})

            if tool_name not in self.tools:
                return MCPResponse(
                    request_id=request.request_id,
                    error={{"code": -32601, "message": f"Unknown tool: {{tool_name}}",
                           "retryable": False}}
                )

            try:
                tool_fn = self.tools[tool_name]["function"]
                # Filter out orchestrator-injected kwargs the tool doesn't expect
                sig = inspect.signature(tool_fn)
                params = sig.parameters
                has_var_keyword = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
                )
                if not has_var_keyword:
                    arguments = {{
                        k: v for k, v in arguments.items() if k in params
                    }}
                result = tool_fn(**arguments)

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
                        logger.warning(f"Tool '{{tool_name}}' returned error alert: {{error_msg}}")
                        return MCPResponse(
                            request_id=request.request_id,
                            error={{"code": -32000, "message": error_msg,
                                   "retryable": True}},
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
                logger.error(f"Tool '{{tool_name}}' raised {{type(e).__name__}}: {{e}} "
                             f"(retryable={{retryable}})")
                return MCPResponse(
                    request_id=request.request_id,
                    error={{"code": -32603, "message": str(e),
                           "retryable": retryable}}
                )

        return MCPResponse(
            request_id=request.request_id,
            error={{"code": -32601, "message": f"Unknown method: {{request.method}}",
                   "retryable": False}}
        )
'''

# ─── Code Generator ─────────────────────────────────────────────────────

class AgentCodeGenerator:
    """Generates agent code files using LLM for tool implementations and templates for boilerplate."""

    def __init__(self, llm_client: Optional[OpenAI] = None, llm_model: str = None):
        self.llm_client = llm_client
        self.llm_model = llm_model
        if not self.llm_client:
            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL")
            self.llm_model = os.getenv("LLM_MODEL", "meta-llama/Llama-3.2-90B-Vision-Instruct")
            if api_key and base_url:
                self.llm_client = OpenAI(
                    api_key=api_key, base_url=base_url,
                    timeout=Timeout(180.0, connect=10.0)
                )

    def _slugify(self, name: str) -> str:
        """Convert agent name to a safe directory/module slug."""
        slug = re.sub(r'[^a-z0-9]+', '_', name.lower().strip())
        slug = slug.strip('_')
        return slug or 'custom_agent'

    def _class_name(self, slug: str) -> str:
        """Convert slug to PascalCase class name."""
        return ''.join(word.capitalize() for word in slug.split('_')) + 'Agent'

    @staticmethod
    def _sanitize_description(description: str) -> str:
        """Sanitize description for safe injection into Python source code.

        Returns a single-line string safe for use in triple-quoted strings.
        Collapses whitespace, escapes backslashes and triple quotes, and
        ensures the string doesn't end with a quote (which would collide
        with the closing triple-quote delimiter).
        """
        # Collapse all whitespace (newlines, tabs, multiple spaces) to single spaces
        safe = ' '.join(description.split())
        # Escape backslashes first, then triple quotes
        safe = safe.replace('\\', '\\\\').replace('"""', '\\"\\"\\"')
        # If it ends with a quote, add a trailing space to prevent """" ambiguity
        if safe.endswith('"'):
            safe += ' '
        return safe

    def generate_template_files(self, agent_name: str, description: str,
                                 slug: str, skill_tags: List[str] = None) -> Dict[str, str]:
        """Generate the boilerplate agent_py and mcp_server files from templates."""
        class_name = self._class_name(slug)
        agent_id = f"{slug.replace('_', '-')}-1"
        port_env_var = f"{slug.upper()}_AGENT_PORT"
        tags_repr = repr(skill_tags or [])
        safe_desc = self._sanitize_description(description)

        agent_py = AGENT_PY_TEMPLATE.format(
            service_name=agent_name.replace('"', '\\"'),
            docstring_description=safe_desc,
            escaped_description=safe_desc,
            slug=slug,
            class_name=class_name,
            agent_id=agent_id,
            skill_tags=tags_repr,
            port_env_var=port_env_var,
        )

        mcp_server_py = MCP_SERVER_TEMPLATE.format(
            service_name=agent_name,
            slug=slug,
            class_name=class_name,
        )

        return {
            f"{slug}_agent.py": agent_py,
            "mcp_server.py": mcp_server_py,
        }

    async def generate_tools_file(self, agent_name: str, description: str,
                                   tools_spec: List[Dict[str, Any]],
                                   packages: List[str] = None) -> str:
        """Use LLM to generate mcp_tools.py with tool implementations."""
        if not self.llm_client:
            raise RuntimeError("LLM not configured — cannot generate agent tools")

        tools_description = ""
        if tools_spec:
            for i, tool in enumerate(tools_spec, 1):
                tools_description += f"\n{i}. **{tool.get('name', f'tool_{i}')}**\n"
                tools_description += f"   - Description: {tool.get('description', 'No description')}\n"
                if tool.get('input_schema'):
                    tools_description += f"   - Input schema: {json.dumps(tool['input_schema'])}\n"
                if tool.get('scope'):
                    tools_description += f"   - Scope: {tool['scope']}\n"

        packages_note = ""
        if packages:
            packages_note = f"\nAllowed packages to import: {', '.join(packages)}"

        ui_spec = generate_llm_prompt_section()

        prompt = f"""You are a Python code generator for an agent tool system. Generate a complete `mcp_tools.py` file.

## Agent Info
- Name: {agent_name}
- Description: {description}

## Tools to Implement
{tools_description if tools_description else "Create appropriate tools based on the agent description."}
{packages_note}

{ui_spec}

## CREDENTIAL DECLARATION

If this agent needs external API keys, OAuth tokens, or other secrets for **third-party services**
(e.g. a weather API, email service, database), declare them with REQUIRED_CREDENTIALS:

```python
REQUIRED_CREDENTIALS = [
    {{
        "key": "SERVICE_API_KEY",        # UPPER_SNAKE_CASE key name
        "label": "Service API Key",      # Human-readable label
        "description": "Get this from ...",  # Help text for the user
        "required": True,                # True if agent cannot work without it
        "type": "api_key"                # One of: api_key, oauth_client_id, oauth_client_secret, token, password, username
    }},
]
```

If the agent does NOT need any external credentials (e.g. it only generates data locally
or uses public APIs), set `REQUIRED_CREDENTIALS = []`.

**NEVER declare credentials for the LLM itself** (no OpenAI key, no model config, no AI/LLM API keys).
The LLM is provided by the system and shared across all agents — agents do not need their own LLM credentials.
Only declare credentials for external third-party services the agent's tools call directly.

IMPORTANT: Credentials are injected at runtime via the `_credentials` dict parameter.
Inside tool functions, accept `**kwargs` and access them like:
`api_key = kwargs.get("_credentials", {{}}).get("SERVICE_API_KEY", "")`
Do NOT hardcode secrets. Do NOT use os.environ for secrets.

## SECURITY RULES — You MUST follow these:
- Do NOT use `eval()`, `exec()`, `compile()`, or `__import__()`
- Do NOT use `subprocess`, `os.system`, `os.popen`, or any shell execution
- Do NOT access `os.environ` for secrets or sensitive keys
- Do NOT open network sockets directly (use `requests`/`httpx` for HTTP only)
- Do NOT use `pickle`, `marshal`, or `yaml.load` (unsafe deserialization)
- Do NOT write/read files outside of returning data
- Do NOT use `ctypes`, `cffi`, or native code execution

Output ONLY the Python code. No markdown fences, no explanations."""

        messages = [
            {"role": "system", "content": "You are a precise Python code generator. Output ONLY valid Python code, no markdown fences or explanations."},
            {"role": "user", "content": prompt}
        ]

        response = await asyncio.to_thread(
            self.llm_client.chat.completions.create,
            model=self.llm_model,
            messages=messages,
            temperature=0.2,
        )

        code = response.choices[0].message.content.strip()
        # Strip markdown fences if present
        if code.startswith("```"):
            lines = code.split("\n")
            # Remove first and last fence lines
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines)

        return code

    async def refine_tools_file(self, current_code: str, user_message: str,
                                 agent_name: str, description: str) -> str:
        """Refine existing mcp_tools.py based on user feedback."""
        if not self.llm_client:
            raise RuntimeError("LLM not configured — cannot refine agent tools")

        ui_spec = generate_llm_prompt_section()

        prompt = f"""You are refining the tool implementations for an agent.

## Agent Info
- Name: {agent_name}
- Description: {description}

## Current mcp_tools.py code:
```python
{current_code}
```

## User's requested changes:
{user_message}

{ui_spec}

IMPORTANT: Ensure all UI components use the shared.primitives classes (Card, MetricCard, Alert, etc.)
and call `.to_json()` to serialize them. Do NOT use raw dicts for UI components.

## CREDENTIAL DECLARATION

The file must include a `REQUIRED_CREDENTIALS` list at the module level. If the agent needs
external API keys, OAuth tokens, or other secrets for **third-party services**, declare each one:

```python
REQUIRED_CREDENTIALS = [
    {{"key": "SERVICE_API_KEY", "label": "Service API Key", "description": "Get this from ...", "required": True, "type": "api_key"}},
]
```

If no credentials are needed, set `REQUIRED_CREDENTIALS = []`.
If the refinement adds or removes API integrations, update REQUIRED_CREDENTIALS accordingly.
Access credentials at runtime via: `kwargs.get("_credentials", {{}}).get("KEY", "")`

**NEVER declare credentials for the LLM/AI model** (no OpenAI key, no model config).
The LLM is system-provided and shared across all agents. Only declare credentials for external services.

## SECURITY RULES — You MUST follow these:
- Do NOT use `eval()`, `exec()`, `compile()`, or `__import__()`
- Do NOT use `subprocess`, `os.system`, `os.popen`, or any shell execution
- Do NOT access `os.environ` for secrets or sensitive keys
- Do NOT open network sockets directly (use `requests`/`httpx` for HTTP only)
- Do NOT use `pickle`, `marshal`, or `yaml.load` (unsafe deserialization)
- Do NOT write/read files outside of returning data
- Do NOT use `ctypes`, `cffi`, or native code execution

Apply the requested changes and output the COMPLETE updated mcp_tools.py file.
Output ONLY the Python code. No markdown fences, no explanations."""

        messages = [
            {"role": "system", "content": "You are a precise Python code generator. Output ONLY valid Python code, no markdown fences or explanations."},
            {"role": "user", "content": prompt}
        ]

        response = await asyncio.to_thread(
            self.llm_client.chat.completions.create,
            model=self.llm_model,
            messages=messages,
            temperature=0.2,
        )

        code = response.choices[0].message.content.strip()
        if code.startswith("```"):
            lines = code.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines)

        return code
