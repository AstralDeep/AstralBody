"""WebSocket client for the AstralBody orchestrator.

Speaks the exact client protocol: connects to ws://<host>/ws, sends `register_ui`
(token + device caps) first, then streams JSON messages. Inbound messages are
delivered to the Qt main thread via the `message` signal; outbound `ui_event` /
`chat_message` are sent thread-safely onto the asyncio loop.

Runs the asyncio websocket loop in a daemon thread so the Qt UI stays responsive.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Optional

import websockets
from PySide6.QtCore import QObject, Signal


def device_caps(width: int = 1280, height: int = 860) -> dict:
    """Report a full-capability browser-class profile so the server sends the
    complete component tree (we render natively, so we want no degradation)."""
    return {
        "device_type": "browser",
        "screen_width": width, "screen_height": height,
        "viewport_width": width, "viewport_height": height,
        "pixel_ratio": 1.0, "has_touch": False, "user_agent": "AstralWindowsClient/0.1",
        "connection_type": "wifi",
    }


class OrchestratorClient(QObject):
    message = Signal(dict)        # any inbound server message {type: ...}
    status = Signal(str)          # "connecting" | "connected" | "auth_required:<reason>" | "closed:<why>"

    def __init__(self, url: str, token: str, device: Optional[dict] = None):
        super().__init__()
        self.url = url
        self.token = token
        self.device = device or device_caps()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop = False

    # --- lifecycle ------------------------------------------------------- #
    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        if self._loop and self._ws:
            asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as exc:  # surface connection failures to the UI
            self.status.emit(f"closed:{exc}")

    async def _main(self) -> None:
        self.status.emit("connecting")
        async with websockets.connect(self.url, max_size=16 * 1024 * 1024,
                                      ping_interval=20) as ws:
            self._ws = ws
            await ws.send(json.dumps({
                "type": "register_ui",
                "token": self.token,
                "capabilities": ["render", "stream"],
                "session_id": "win-client",
                "device": self.device,
                "resumed": False,
            }))
            self.status.emit("connected")
            async for raw in ws:
                if self._stop:
                    break
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if isinstance(msg, dict):
                    if msg.get("type") == "auth_required":
                        self.status.emit(f"auth_required:{msg.get('reason', '')}")
                    self.message.emit(msg)
        self.status.emit("closed:server")

    # --- outbound -------------------------------------------------------- #
    def _send(self, obj: dict) -> None:
        if not (self._loop and self._ws):
            return
        asyncio.run_coroutine_threadsafe(self._ws.send(json.dumps(obj)), self._loop)

    def send_event(self, action: str, payload: dict, session_id: Optional[str] = None) -> None:
        self._send({"type": "ui_event", "action": action,
                    "session_id": session_id, "payload": payload or {}})

    def send_chat(self, message: str, chat_id: Optional[str] = None,
                  attachments: Optional[list] = None) -> None:
        payload: dict[str, Any] = {"message": message}
        if chat_id:
            payload["chat_id"] = chat_id
        if attachments:
            payload["attachments"] = attachments
        self.send_event("chat_message", payload, session_id=chat_id)
