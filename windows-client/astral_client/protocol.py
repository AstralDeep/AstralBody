"""WebSocket client for the AstralBody orchestrator.

Speaks the exact client protocol: connects to ws://<host>/ws, sends `register_ui`
(token + device caps) first, then streams JSON messages. Inbound messages are
delivered to the Qt main thread via the `message` signal; outbound `ui_event` /
`chat_message` are sent thread-safely onto the asyncio loop.

Feature 044 (FR-003): the transport owns the connection lifecycle — it
auto-reconnects after a drop with exponential backoff (1 s base, x2, 30 s cap,
reset on a successful open), buffers outbound frames composed while
disconnected in a bounded queue flushed FIFO on (re)connect, and surfaces every
state change through the `status` signal so the app can keep the connection
state visible. Queue overflow is never silent: the oldest frame is dropped AND
a `send_dropped:` status is emitted for the UI to surface.

Runs the asyncio websocket loop in a daemon thread so the Qt UI stays responsive.
"""
from __future__ import annotations

import asyncio
import json
import threading
from collections import deque
from typing import Any, Optional

import websockets
from PySide6.QtCore import QObject, Signal

#: Bounded outbound buffer while disconnected (matches the Android client).
MAX_QUEUE = 64

#: Reconnect backoff bounds (seconds) — 1 s base doubling to a 30 s cap.
BACKOFF_BASE_S = 1.0
BACKOFF_MAX_S = 30.0


def backoff_delay_s(attempt: int, base: float = BACKOFF_BASE_S,
                    cap: float = BACKOFF_MAX_S) -> float:
    """Delay before reconnect ``attempt`` (1-based): base * 2^(attempt-1), capped.

    Mirrors the Android client's ``backoffDelayMs`` so both natives share the
    same contract (specs/044 contracts/session-lifecycle.md §1).
    """
    if attempt <= 1:
        return base
    return min(base * (2 ** (attempt - 1)), cap)


def device_caps(width: int = 1280, height: int = 860,
                supported_types=None) -> dict:
    """Report this client as a native ``windows`` device with the set of SDUI
    primitive types it renders natively. ROTE keys off ``device_type`` for the
    desktop host-config and uses ``supported_types`` to substitute web-only
    primitives (e.g. audio) the native renderer can't draw — so the
    server adapts to the desktop app's real capabilities, not the web view's."""
    caps = {
        "device_type": "windows",
        "screen_width": width, "screen_height": height,
        "viewport_width": width, "viewport_height": height,
        "pixel_ratio": 1.0, "has_touch": False, "user_agent": "AstralWindowsClient/0.1",
        "connection_type": "wifi",
    }
    if supported_types:
        caps["supported_types"] = list(supported_types)
    return caps


class OrchestratorClient(QObject):
    message = Signal(dict)        # any inbound server message {type: ...}
    # "connecting" | "connected" | "reconnecting:<attempt>" |
    # "auth_required:<reason>" | "closed:<why>" | "send_dropped:<action>"
    status = Signal(str)

    def __init__(self, url: str, token: str, device: Optional[dict] = None):
        super().__init__()
        self.url = url
        self.token = token
        self.device = device or device_caps()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop = False
        self._auth_hold = False   # auth_required seen: don't loop on a bad token
        self._connected = False
        self._had_session = False
        self._pending: deque[str] = deque()

    # --- lifecycle ------------------------------------------------------- #
    def _safe_status(self, s: str) -> None:
        """Emit a status signal, tolerating teardown (the C++ QObject may be
        deleted while this daemon thread is still running)."""
        try:
            self.status.emit(s)
        except RuntimeError:
            pass

    def _safe_message(self, m: dict) -> None:
        try:
            self.message.emit(m)
        except RuntimeError:
            pass

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        if self._loop and self._ws:
            try:
                asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)
            except RuntimeError:
                pass

    def _should_reconnect(self) -> bool:
        """Auto-reconnect unless the app is quitting or the server demanded
        re-authentication (the app owns the refresh + rebuild in that case)."""
        return not self._stop and not self._auth_hold

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        attempt = 0
        while True:
            self._had_session = False
            try:
                self._loop.run_until_complete(self._main())
                if not self._stop and not self._auth_hold:
                    self._safe_status("closed:server")
            except Exception as exc:  # surface connection failures to the UI
                if not self._stop:
                    self._safe_status(f"closed:{exc}")
            self._connected = False
            self._ws = None
            if self._had_session:
                attempt = 0  # successful open resets the backoff (FR-003)
            if not self._should_reconnect():
                break
            attempt += 1
            self._safe_status(f"reconnecting:{attempt}")
            if not self._interruptible_sleep(backoff_delay_s(attempt)):
                break

    def _interruptible_sleep(self, seconds: float) -> bool:
        """Sleep in slices so stop()/auth_required end the wait promptly.
        Returns False when the loop should exit instead of reconnecting."""
        remaining = seconds
        while remaining > 0:
            if not self._should_reconnect():
                return False
            step = min(0.25, remaining)
            self._loop.run_until_complete(asyncio.sleep(step))
            remaining -= step
        return self._should_reconnect()

    async def _main(self) -> None:
        self._safe_status("connecting")
        async with websockets.connect(self.url, max_size=16 * 1024 * 1024,
                                      ping_interval=20) as ws:
            self._ws = ws
            self._had_session = True
            await ws.send(json.dumps({
                "type": "register_ui",
                "token": self.token,
                "capabilities": ["render", "stream"],
                "session_id": "win-client",
                "device": self.device,
                "resumed": False,
            }))
            await self._finish_open(ws)
            async for raw in ws:
                if self._stop:
                    break
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if isinstance(msg, dict):
                    if msg.get("type") == "auth_required":
                        # Hold auto-reconnect: retrying with the same token
                        # would loop; the app refreshes and rebuilds instead.
                        self._auth_hold = True
                        self._safe_status(f"auth_required:{msg.get('reason', '')}")
                    self._safe_message(msg)

    async def _finish_open(self, ws) -> None:
        """Post-register open sequence. Drain the offline queue FIFO BEFORE
        flipping `_connected`, so any queued frame goes out ahead of a new
        direct send. If `_connected` were set first, a frame sent by the
        "connected" handler could race ahead of the queued backlog and reorder
        reconnect delivery. Then drain ONCE MORE after the flip: a frame
        appended to `_pending` between the first drain and the flip would
        otherwise sit unflushed while the connection stays healthy — once
        `_connected` is True no new frame enters the queue, so the second
        drain deterministically closes that window (FR-003)."""
        await self._flush_pending(ws)
        self._connected = True
        await self._flush_pending(ws)
        self._safe_status("connected")

    # --- outbound -------------------------------------------------------- #
    async def _flush_pending(self, ws) -> None:
        """Drain frames queued while disconnected, FIFO (FR-003)."""
        while self._pending and not self._stop:
            frame = self._pending.popleft()
            await ws.send(frame)

    def _send(self, obj: dict) -> None:
        frame = json.dumps(obj)
        # Snapshot `_ws`/`_loop` under the guard: the transport thread can null
        # `_ws` between the check and the attribute access, which would raise an
        # AttributeError inside a Qt slot (TOCTOU). If the snapshot is None after
        # the guard, fall through to the queue path.
        ws = self._ws
        loop = self._loop
        if self._connected and loop and ws:
            fut = asyncio.run_coroutine_threadsafe(ws.send(frame), loop)
            # The socket can die AFTER the `_connected` check with the flag
            # still True — a fire-and-forget send would then vanish silently.
            # Re-queue a failed fast-path send through the offline path so it
            # goes out on the next (re)connect. The callback runs on the
            # asyncio loop thread; deque appends are thread-safe.
            fut.add_done_callback(lambda f: self._on_fast_send_done(f, frame))
            return
        self._queue_frame(frame)

    def _on_fast_send_done(self, fut, frame: str) -> None:
        """Done-callback for a connected fast-path send: on failure the frame is
        re-queued so an outbound frame never just vanishes (FR-003)."""
        try:
            failed = fut.cancelled() or fut.exception() is not None
        except Exception:  # noqa: BLE001 — treat an unreadable future as failed
            failed = True
        if failed:
            self._queue_frame(frame)

    def _queue_frame(self, frame: str) -> None:
        """Queue a frame for the (re)connect flush with a bounded buffer;
        overflow is dropped-oldest AND surfaced — an outbound frame never just
        vanishes."""
        self._pending.append(frame)
        while len(self._pending) > MAX_QUEUE:
            dropped = self._pending.popleft()
            try:
                action = json.loads(dropped).get("action", "message")
            except (ValueError, TypeError, AttributeError):
                action = "message"
            self._safe_status(f"send_dropped:{action}")

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
