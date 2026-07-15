"""
Agent Code Generator for AstralDeep.

Two generation targets, sharing one LLM-written ``mcp_tools.py``:

**backend** (feature 027 — server-hosted draft agents), 3 files:
- {slug}_agent.py  — from template (not LLM)
- mcp_server.py    — from template (not LLM)
- mcp_tools.py     — LLM-generated tool implementations

**byo** (feature 058 — user-hosted desktop agents), 3 files:
- agent_main.py    — from template (not LLM): self-contained JSON-lines-over-stdio runner
- mcp_tools.py     — LLM-generated tool implementations
- manifest.json    — the host's record of what it was handed

The BYO bundle must be SELF-CONTAINED: it runs on the owner's desktop, which
ships none of the backend package (no fastapi/uvicorn/a2a-sdk) and sits behind
NAT, so ``BaseA2AAgent``'s inbound uvicorn server is both too heavy and the wrong
topology. See specs/058-byo-agents-runtime/contracts/host-bundle.md.
"""
import re
import json
import logging
import asyncio
import time
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

# ─── BYO templates (feature 058) ────────────────────────────────────────
#
# Split header/body because the body is brace-dense (dict literals) and
# ``str.format`` would need every one of them doubled. Only the header — the few
# identity constants — is formatted; the runner body is a plain constant.

BYO_AGENT_MAIN_HEADER = '''#!/usr/bin/env python3
"""{service_name} — user-hosted (BYO) agent.

{docstring_description}

Runs as a supervised CHILD PROCESS on the OWNER'S machine and speaks JSON lines
over stdio to its parent (the desktop client), which relays each frame over its
own authenticated tunnel. Self-contained by construction: no backend package, no
inbound server, no third-party import beyond astralprims (which mcp_tools uses).
"""
import inspect
import json
import sys

from mcp_tools import TOOL_REGISTRY

AGENT_ID = {agent_id!r}
AGENT_NAME = {agent_name!r}
AGENT_DESCRIPTION = {agent_desc!r}
SKILL_TAGS = {skill_tags!r}
'''

BYO_AGENT_MAIN_BODY = '''

def build_card():
    """The AgentCard the orchestrator's registration path expects."""
    return {
        "name": AGENT_NAME,
        "description": AGENT_DESCRIPTION,
        "agent_id": AGENT_ID,
        "version": "1.0.0",
        "skills": [{
            "id": name,
            "name": name,
            "description": info.get("description", ""),
            "input_schema": info.get("input_schema", {"type": "object", "properties": {}}),
            "output_schema": None,
            "tags": SKILL_TAGS,
            "scope": info.get("scope", "tools:read"),
            "metadata": {},
        } for name, info in TOOL_REGISTRY.items()],
        "metadata": {"host": "byo_client", "transport": "stdio"},
    }


def _emit(frame):
    """One JSON object per line on stdout; the parent relays it verbatim.

    No AGENT_API_KEY: authority on this path is the owner's authenticated UI
    session, never anything the frame presents.
    """
    sys.stdout.write(json.dumps(frame) + "\\n")
    sys.stdout.flush()


def dispatch(req):
    """One mcp_request dict -> one mcp_response dict."""
    rid = req.get("request_id", "")
    method = req.get("method", "")

    if method == "tools/list":
        return {"type": "mcp_response", "request_id": rid, "result": {"tools": [
            {"name": n, "description": i.get("description", ""),
             "input_schema": i.get("input_schema", {"type": "object", "properties": {}})}
            for n, i in TOOL_REGISTRY.items()]}}

    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        info = TOOL_REGISTRY.get(name)
        if not info:
            return {"type": "mcp_response", "request_id": rid,
                    "error": {"code": -32601, "message": "Unknown tool: %s" % name,
                              "retryable": False}}
        try:
            fn = info["function"]
            sig = inspect.signature(fn)
            if not any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
                args = {k: v for k, v in args.items() if k in sig.parameters}
            result = fn(**args)
            comps = result.get("_ui_components") if isinstance(result, dict) else None
            data = result.get("_data") if isinstance(result, dict) else result
            # The tool-error convention the backend MCPServer implements: a tool
            # that handled its own failure returns create_ui_response([
            # Alert(variant="error")]). That is an ERROR response, not a success
            # one — without this the orchestrator would treat a failed BYO tool
            # call as having succeeded.
            if isinstance(comps, list):
                for c in comps:
                    if isinstance(c, dict) and c.get("variant") == "error":
                        return {"type": "mcp_response", "request_id": rid,
                                "error": {"code": -32000,
                                          "message": c.get("message",
                                                           "Tool returned an error"),
                                          "retryable": True},
                                "ui_components": comps}
            return {"type": "mcp_response", "request_id": rid,
                    "result": data, "ui_components": comps}
        except Exception as exc:
            return {"type": "mcp_response", "request_id": rid,
                    "error": {"code": -32603, "message": str(exc), "retryable": True}}

    return {"type": "mcp_response", "request_id": rid,
            "error": {"code": -32601, "message": "Unknown method: %s" % method,
                      "retryable": False}}


def main():
    # stdout is the channel — force UTF-8 so a non-ASCII tool result cannot
    # wedge the pipe on a Windows console default codepage.
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    _emit({"type": "register_agent", "agent_card": build_card()})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except (ValueError, TypeError):
            # A stray print() in tool code must not corrupt the channel.
            sys.stderr.write("discarded non-JSON line on stdin\\n")
            continue
        if not isinstance(req, dict):
            continue
        if req.get("type") == "mcp_request" or "method" in req:
            _emit(dispatch(req))

    return 0   # EOF: the child dies with its parent


if __name__ == "__main__":
    raise SystemExit(main())
'''

#: A BYO bundle that reaches for the backend package would ImportError on the
#: desktop host (and, if it somehow resolved, would import server-side code onto
#: a user's machine). Checked as a GATE on the LLM-written file, not merely asked
#: for in the prompt.
BYO_FORBIDDEN_PATTERNS = (
    "from shared", "import shared", "from agents.", "import agents.",
    "sys.path.insert",
)


def byo_import_violations(code: str) -> List[str]:
    """The forbidden backend-coupling patterns present in a BYO bundle file."""
    return [p for p in BYO_FORBIDDEN_PATTERNS if p in (code or "")]


# ─── Security rules (shared by generate + refine) ───────────────────────

_SECURITY_RULES_COMMON = """- Do NOT use `eval()`, `exec()`, `compile()`, or `__import__()`
- Do NOT use `subprocess`, `os.system`, `os.popen`, or any shell execution
- Do NOT access `os.environ` for secrets or sensitive keys
- Do NOT use `pickle`, `marshal`, or `yaml.load` (unsafe deserialization)
- Do NOT write/read files outside of returning data
- Do NOT use `ctypes`, `cffi`, or native code execution"""

#: Server-hosted (027) image: requests/httpx ARE installed.
_SECURITY_RULES_BACKEND = f"""{_SECURITY_RULES_COMMON}
- Do NOT open network sockets directly (use `requests`/`httpx` for HTTP only)
- Import ONLY the Python standard library and packages already installed in this
  image. Do NOT assume any `pip install` is available — there is no network or
  package-install step. If a format truly needs an unavailable library, do a
  best-effort structural extraction with the standard library (e.g. treat
  zip/OOXML/epub as `zipfile` + XML, archives via `tarfile`/`zipfile`, columnar
  or binary data via a documented partial read) and clearly state the limitation
  in the returned output rather than failing."""

#: BYO (058) desktop host: ONLY the standard library + astralprims exist there.
#: An `import requests` bundle dies at import on the user's machine, never sends
#: `register_agent`, and surfaces only as the host's silence timeout — so the
#: allowlist is enforced as a GATE at generation time (agent_validator).
_SECURITY_RULES_BYO = f"""{_SECURITY_RULES_COMMON}
- Do NOT open network sockets directly. For HTTP use `urllib.request` from the
  standard library — `requests` and `httpx` are NOT available on the user's machine.
- Import ONLY the Python standard library and `astralprims`. NOTHING else is
  installed where this agent runs. Do NOT assume any `pip install` is available,
  do NOT import from `shared` or `agents.`, and NEVER touch `sys.path`.
  A file that imports anything else is REJECTED and never delivered."""


def security_rules_block(self_contained: bool = False) -> str:
    """The SECURITY RULES prompt block for the target the code will run on."""
    return _SECURITY_RULES_BYO if self_contained else _SECURITY_RULES_BACKEND


# ─── Code Generator ─────────────────────────────────────────────────────

class AgentCodeGenerator:
    """Generates agent code files using LLM for tool implementations and templates for boilerplate."""

    def __init__(self, llm_client: Optional[OpenAI] = None, llm_model: str = None,
                 config_resolver=None):
        """Args:
            llm_client / llm_model: An explicit pre-built client (tests,
                injection seams). When absent, ``config_resolver`` is used.
            config_resolver: Zero-arg SYNC callable returning the current
                system LLM configuration (feature 054 — codegen is a
                system-context flow billed to the admin-managed credential;
                the retired ``OPENAI_*`` env fallback is gone). Resolved
                per generation call so an admin save takes effect without
                a restart.
        """
        self.llm_client = llm_client
        self.llm_model = llm_model
        self._config_resolver = config_resolver

    async def _aresolve_client(self, config_resolver=None):
        """Resolve (client, model) for one generation call, or (None, None).

        ``config_resolver`` overrides the default (system) resolver for this call.
        BYO authoring passes the OWNER's resolver: the user is actively authoring
        their own private agent, so its code is generated with THEIR configured
        LLM — not the admin-managed system credential that background codegen uses
        (feature 054). A direct ``llm_client`` still wins (tests inject it)."""
        if self.llm_client is not None:
            return self.llm_client, self.llm_model
        resolver = config_resolver or self._config_resolver
        if resolver is None:
            return None, None
        try:
            cfg = await asyncio.to_thread(resolver)
        except Exception:
            logger.exception("agent codegen: LLM config resolution failed")
            return None, None
        if cfg is None:
            return None, None
        return OpenAI(
            api_key=getattr(cfg, "api_key", "") or "not-needed",
            base_url=cfg.base_url,
            timeout=Timeout(180.0, connect=10.0),
        ), cfg.model

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

    @staticmethod
    def default_agent_id(slug: str) -> str:
        """The runtime agent id a slug implies on the server-hosted (027) path."""
        return f"{slug.replace('_', '-')}-1"

    def generate_template_files(self, agent_name: str, description: str,
                                 slug: str, skill_tags: List[str] = None,
                                 agent_id: Optional[str] = None) -> Dict[str, str]:
        """Generate the boilerplate agent_py and mcp_server files from templates.

        ``agent_id`` defaults to the slug-derived id, so the 027 path is
        byte-identical. It is explicit because a BYO agent's identity is
        owner-namespaced (``ua-<name>-<ownerhash>``) and must be the id the card
        presents — the registry looks the card's id up and refuses fail-closed on
        a mismatch (``user_agents.authorize_registration``)."""
        class_name = self._class_name(slug)
        agent_id = agent_id or self.default_agent_id(slug)
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

    def generate_byo_files(self, agent_name: str, description: str,
                           agent_id: str, skill_tags: List[str] = None,
                           constitution_version: Optional[str] = None) -> Dict[str, str]:
        """The deterministic half of a BYO bundle (058 T008): the stdio runner and
        the host's manifest. The LLM-written ``mcp_tools.py`` is added by the caller.

        The runner bakes the OWNER-NAMESPACED ``agent_id`` it is handed; a
        slug-derived id here would be refused at registration and the refusal is
        silent on the wire (host-bundle.md §6)."""
        safe_desc = self._sanitize_description(description)

        agent_main = BYO_AGENT_MAIN_HEADER.format(
            service_name=agent_name.replace('"', '\\"'),
            docstring_description=safe_desc,
            agent_id=agent_id,
            agent_name=agent_name,
            agent_desc=safe_desc,
            skill_tags=list(skill_tags or []),
        ) + BYO_AGENT_MAIN_BODY

        manifest = json.dumps({
            "agent_id": agent_id,
            "agent_name": agent_name,
            "description": safe_desc,
            "constitution_version": constitution_version,
            "generated_at": int(time.time() * 1000),
        }, indent=2) + "\n"

        return {"agent_main.py": agent_main, "manifest.json": manifest}

    async def generate_tools_file(self, agent_name: str, description: str,
                                   tools_spec: List[Dict[str, Any]],
                                   packages: List[str] = None,
                                   knowledge_context: str = "",
                                   self_contained: bool = False,
                                   config_resolver=None) -> str:
        """Use LLM to generate mcp_tools.py with tool implementations.

        ``self_contained`` (BYO): the file runs on the owner's desktop, which has
        no backend package — say so in the prompt. The hard guarantee is the
        ``byo_import_violations`` gate on the result, not this instruction.
        ``config_resolver`` (BYO): use the owner's LLM, not the system one."""
        _client, _model = await self._aresolve_client(config_resolver)
        if not _client:
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
        if self_contained:
            packages_note += (
                "\n\nThis agent runs on the USER'S OWN DESKTOP, not on the server. "
                "The file MUST be self-contained: import ONLY the Python standard "
                "library and `astralprims`. NEVER import from `shared`, from "
                "`agents.`, and NEVER touch `sys.path`."
            )

        ui_spec = generate_llm_prompt_section(self_contained=self_contained)

        knowledge_section = ""
        if knowledge_context:
            knowledge_section = f"""
## Proven Patterns & Techniques
The following patterns have been learned from production usage and should inform your implementation:

{knowledge_context}
"""

        prompt = f"""You are a Python code generator for an agent tool system. Generate a complete `mcp_tools.py` file.

## Agent Info
- Name: {agent_name}
- Description: {description}

## Tools to Implement
{tools_description if tools_description else "Create appropriate tools based on the agent description."}
{packages_note}

{ui_spec}
{knowledge_section}

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
{security_rules_block(self_contained)}

Output ONLY the Python code. No markdown fences, no explanations."""

        messages = [
            {"role": "system", "content": "You are a precise Python code generator. Output ONLY valid Python code, no markdown fences or explanations."},
            {"role": "user", "content": prompt}
        ]

        response = await asyncio.to_thread(
            _client.chat.completions.create,
            model=_model,
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
                                 agent_name: str, description: str,
                                 self_contained: bool = False,
                                 config_resolver=None) -> str:
        """Refine existing mcp_tools.py based on user feedback.

        ``self_contained`` (BYO): the refinement must stay runnable on the owner's
        desktop — no backend package, no sys.path shim, stdlib + astralprims only.
        The auto-fix loop refines BYO code too, so a refine prompt that mandated
        the backend imports block would hand the self-containment gate a file it
        must reject.
        ``config_resolver`` (BYO): use the owner's LLM, not the system one."""
        _client, _model = await self._aresolve_client(config_resolver)
        if not _client:
            raise RuntimeError("LLM not configured — cannot refine agent tools")

        ui_spec = generate_llm_prompt_section(self_contained=self_contained)

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

IMPORTANT: Ensure all UI components use the astralprims classes (Card, MetricCard, Alert, etc.)
and call `.to_dict()` to serialize them. Do NOT use raw dicts for UI components.

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
{security_rules_block(self_contained)}

Apply the requested changes and output the COMPLETE updated mcp_tools.py file.
Output ONLY the Python code. No markdown fences, no explanations."""

        messages = [
            {"role": "system", "content": "You are a precise Python code generator. Output ONLY valid Python code, no markdown fences or explanations."},
            {"role": "user", "content": prompt}
        ]

        response = await asyncio.to_thread(
            _client.chat.completions.create,
            model=_model,
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
