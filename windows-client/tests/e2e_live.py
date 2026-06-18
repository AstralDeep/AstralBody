"""Live end-to-end check: connect to a RUNNING orchestrator (USE_MOCK_AUTH=true),
send a chat to a keyless agent, and render the REAL ui_render components it
returns as native widgets (offscreen). Proves the whole chain:

    register_ui -> chat_message -> ReAct loop -> astralprims -> ROTE
                -> ui_render(components) -> native PySide6 widgets

Not a pytest test (needs a live server). Usage:
    python tests/e2e_live.py --prompt "roll 3 dice"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import websockets  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from astral_client.renderer import RenderContext, render  # noqa: E402


async def collect(url: str, token: str, prompt: str, window_s: float = 12.0):
    captured, status = [], {"auth": None, "chat_id": None}
    async with websockets.connect(url, max_size=16 * 1024 * 1024) as ws:
        await ws.send(json.dumps({
            "type": "register_ui", "token": token,
            "device": {"device_type": "browser", "viewport_width": 1280, "viewport_height": 800}}))
        await ws.send(json.dumps({"type": "ui_event", "action": "new_chat", "payload": {}}))
        loop = asyncio.get_event_loop()
        deadline = loop.time() + window_s
        sent = False
        while loop.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - loop.time()))
            except asyncio.TimeoutError:
                break
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            t = msg.get("type")
            if t == "auth_required":
                status["auth"] = msg.get("reason", "?")
                break
            if t == "chat_created" and not sent:
                status["chat_id"] = (msg.get("payload") or {}).get("chat_id")
                await ws.send(json.dumps({
                    "type": "ui_event", "action": "chat_message",
                    "session_id": status["chat_id"],
                    "payload": {"message": prompt, "chat_id": status["chat_id"]}}))
                sent = True
                deadline = loop.time() + window_s  # restart the window after asking
            if t in ("ui_render", "ui_upsert"):
                captured.append(msg)
    return captured, status


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://127.0.0.1:8001/ws")
    ap.add_argument("--token", default="dev-token")
    ap.add_argument("--prompt", default="roll 3 dice")
    args = ap.parse_args()

    captured, status = asyncio.run(collect(args.url, args.token, args.prompt))
    if status["auth"]:
        print(f"AUTH FAILED: {status['auth']} — orchestrator is not in mock-auth mode.")
        return 2

    # Gather every structured component from the real payloads.
    components = []
    for m in captured:
        if m.get("type") == "ui_render":
            components += [c for c in (m.get("components") or []) if isinstance(c, dict)]
        else:
            for op in m.get("ops") or []:
                if isinstance(op.get("component"), dict):
                    components.append(op["component"])

    app = QApplication.instance() or QApplication([])  # noqa: F841
    ctx = RenderContext(emit=lambda a, p: None)
    rendered, errors, types = 0, 0, {}
    for c in components:
        types[c.get("type", "?")] = types.get(c.get("type", "?"), 0) + 1
        w = render(c, ctx)
        if isinstance(w, QWidget):
            rendered += 1
        if "render error" in (w.metaObject().className() if w else ""):
            errors += 1

    print(f"connected ok (chat={status['chat_id']})")
    print(f"messages: {len(captured)}  components: {len(components)}  rendered: {rendered}")
    print(f"component types: {dict(sorted(types.items()))}")
    ok = rendered == len(components) and len(components) > 0
    print("RESULT:", "PASS — real orchestrator output renders natively" if ok else "NO COMPONENTS / mismatch")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
