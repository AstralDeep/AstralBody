"""Live-system WS smoke test (integration).

Connects to the orchestrator's real UI WebSocket endpoint (``/ws``) the same
way the web client does — register_ui with the dev-mode mock token — and
asserts the registration handshake completes (``system_config`` received).

Historic note: this file used to target ``ws://localhost:8000`` with no path
and swallowed every exception, so it "passed" while logging
``server rejected WebSocket connection: HTTP 403`` (Starlette's standard
rejection for a WS upgrade on an unmatched route) to verification_log.txt.
It now fails loudly when the system is unreachable or refuses registration.

Run directly (``python tests/test_agent_flow.py``) for the long LLM-driven
multi-agent flow with console narration.
"""

import asyncio
import json
import os
import sys

import pytest
import websockets
from dotenv import load_dotenv

load_dotenv()

QUERY = (
    "search all the patients, graph their age, then do an arxiv search about "
    "the main disease in this patient population, then give me the system "
    "stats (cpu, memory, storage, all of it)"
)
URI = f"ws://localhost:{os.getenv('ORCHESTRATOR_PORT', '8001')}/ws"
# Mock-auth literal accepted when USE_MOCK_AUTH=true + ASTRAL_ENV=development.
DEV_TOKEN = os.getenv("TEST_UI_TOKEN", "dev-token")

REGISTER_MSG = {
    "type": "register_ui",
    "token": DEV_TOKEN,
    "capabilities": ["text", "images"],
    "session_id": "test_agent_flow",
}


async def _register(websocket) -> None:
    """Send register_ui and wait for system_config (raises on auth refusal)."""
    await websocket.send(json.dumps(REGISTER_MSG))
    while True:
        resp = json.loads(await asyncio.wait_for(websocket.recv(), timeout=30))
        msg_type = resp.get("type")
        if msg_type == "system_config":
            return
        if msg_type == "auth_required":
            raise AssertionError(
                "register_ui was refused (auth_required) — is the stack "
                "running with USE_MOCK_AUTH=true and ASTRAL_ENV=development?"
            )
        if msg_type == "error":
            raise AssertionError(f"register_ui error: {resp.get('message')}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ws_register_handshake():
    """The UI WS endpoint accepts a dev-token registration end to end."""
    try:
        async with websockets.connect(URI) as websocket:
            await _register(websocket)
    except (OSError, websockets.exceptions.WebSocketException) as exc:
        pytest.fail(f"Could not complete WS registration at {URI}: {exc}")


async def run_full_flow() -> None:
    """Manual long-form flow: drive a real multi-agent LLM query."""
    print(f"Connecting to {URI}...")
    async with websockets.connect(URI) as websocket:
        await _register(websocket)
        print("System ready.")

        await websocket.send(json.dumps({
            "type": "ui_event",
            "action": "chat_message",
            "payload": {"message": QUERY},
        }))
        print(f"Sent query: {QUERY}")

        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < 240:
            resp = json.loads(await websocket.recv())
            msg_type = resp.get("type")
            if msg_type == "chat_status":
                print(f"STATUS: {resp.get('status')} - {resp.get('message')}")
            elif msg_type in ("ui_render", "ui_upsert"):
                components = resp.get("components", [])
                ops = resp.get("ops", [])
                print(f"{msg_type.upper()}: {len(components) or len(ops)} item(s)")
                for c in components:
                    print(f"  - [{c.get('type', 'unknown')}] {c.get('title', 'No Title')}")
                    if c.get("title") == "Analysis":
                        print("--- FINAL ANALYSIS RECEIVED ---")
                        return
            elif msg_type == "error":
                print(f"ERROR: {resp.get('message')}")
        print("Timeout waiting for full flow.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(run_full_flow())
    except KeyboardInterrupt:
        print("Stopped.")
