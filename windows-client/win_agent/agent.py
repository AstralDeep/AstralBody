"""Self-contained A2A agent server for the Windows tools.

Speaks exactly the handshake the orchestrator's `discover_agent` expects:
  GET /.well-known/agent-card.json  -> the AgentCard
  WS  /agent                        -> sends RegisterAgent, then answers
                                       MCPRequest (tools/list, tools/call)
                                       with MCPResponse.

Binds 0.0.0.0 so a Dockerized orchestrator can reach it on the host via
host.docker.internal. Runs on the user's Windows machine, so the tools execute
locally. No dependency on the backend package.

Run standalone:  python -m win_agent.agent --port 8771
"""
from __future__ import annotations

import argparse
import inspect
import json
import logging
import os
from typing import Any, Dict

from aiohttp import web

from .tools import TOOL_REGISTRY

logger = logging.getLogger("win_agent")

AGENT_ID = "windows-tools-1"
AGENT_NAME = "Windows Tools"
AGENT_DESC = ("Windows-specific tools that run on the user's PC: system info, "
              "clipboard read/write, native notifications, open file/folder/URL, "
              "and list a directory.")


def build_card() -> Dict[str, Any]:
    return {
        "name": AGENT_NAME,
        "description": AGENT_DESC,
        "agent_id": AGENT_ID,
        "version": "0.1.0",
        "skills": [{
            "id": name, "name": name, "description": info["description"],
            "input_schema": info.get("input_schema", {"type": "object", "properties": {}}),
            "output_schema": None, "tags": ["windows", "desktop"],
            "scope": info.get("scope", "tools:system"), "metadata": {},
        } for name, info in TOOL_REGISTRY.items()],
        "metadata": {"host": "windows-client", "platform": "windows"},
    }


def _register_message() -> str:
    return json.dumps({
        "type": "register_agent",
        "agent_card": build_card(),
        "api_key": os.getenv("AGENT_API_KEY") or None,
    })


def dispatch(req: Dict[str, Any]) -> Dict[str, Any]:
    """Process one MCPRequest dict -> MCPResponse dict (mirrors the backend MCPServer)."""
    rid = req.get("request_id", "")
    method = req.get("method", "")

    if method == "tools/list":
        return {"type": "mcp_response", "request_id": rid, "result": {"tools": [
            {"name": n, "description": i["description"],
             "input_schema": i.get("input_schema", {"type": "object", "properties": {}})}
            for n, i in TOOL_REGISTRY.items()]}}

    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        info = TOOL_REGISTRY.get(name)
        if not info:
            return {"type": "mcp_response", "request_id": rid,
                    "error": {"code": -32601, "message": f"Unknown tool: {name}", "retryable": False}}
        try:
            fn = info["function"]
            sig = inspect.signature(fn)
            if not any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
                args = {k: v for k, v in args.items() if k in sig.parameters}
            result = fn(**args)
            comps = result.get("_ui_components") if isinstance(result, dict) else None
            data = result.get("_data") if isinstance(result, dict) else result
            return {"type": "mcp_response", "request_id": rid, "result": data, "ui_components": comps}
        except Exception as exc:  # noqa: BLE001
            logger.exception("tool %s failed", name)
            return {"type": "mcp_response", "request_id": rid,
                    "error": {"code": -32603, "message": str(exc), "retryable": True}}

    return {"type": "mcp_response", "request_id": rid,
            "error": {"code": -32601, "message": f"Unknown method: {method}", "retryable": False}}


async def _card(request):
    return web.json_response(build_card())


async def _health(request):
    return web.Response(text="ok")


async def _agent_ws(request):
    ws = web.WebSocketResponse(max_msg_size=50 * 1024 * 1024)
    await ws.prepare(request)
    await ws.send_str(_register_message())
    logger.info("orchestrator connected; registered %d Windows tools", len(TOOL_REGISTRY))
    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            try:
                req = json.loads(msg.data)
            except (ValueError, TypeError):
                continue
            if isinstance(req, dict) and req.get("type") == "mcp_request":
                await ws.send_str(json.dumps(dispatch(req)))
    return ws


def make_app() -> web.Application:
    app = web.Application()
    app.add_routes([
        web.get("/.well-known/agent-card.json", _card),
        web.get("/health", _health),
        web.get("/agent", _agent_ws),
    ])
    return app


def start_agent_thread(host: str = "0.0.0.0", port: int = 8771):
    """Run the agent server in a daemon thread (so the desktop GUI can host it
    in-process). Returns the thread, or None on failure."""
    import asyncio
    import threading

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = web.AppRunner(make_app())
        loop.run_until_complete(runner.setup())
        loop.run_until_complete(web.TCPSite(runner, host, port).start())
        logger.info("Windows tools agent listening on %s:%d", host, port)
        loop.run_forever()

    try:
        t = threading.Thread(target=_run, name="win-agent", daemon=True)
        t.start()
        return t
    except Exception:  # noqa: BLE001
        logger.exception("could not start the Windows tools agent")
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="AstralBody Windows tools agent")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=int(os.getenv("WIN_AGENT_PORT", "8771")))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger.info("Windows tools agent on %s:%d (tools: %s)",
                args.host, args.port, ", ".join(TOOL_REGISTRY))
    web.run_app(make_app(), host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
