"""Minimal WebSocket endpoint for academic transport benchmarking.

This module provides a WebSocket echo endpoint that mirrors the SSE echo
endpoint in sse_transport.py, enabling direct latency/throughput comparison
between the two transport mechanisms.
"""

import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


def create_ws_router() -> APIRouter:
    """Create a FastAPI router with a minimal WebSocket echo endpoint."""
    router = APIRouter()

    @router.websocket("/ws/echo")
    async def ws_echo(websocket: WebSocket):
        """WebSocket echo — mirrors SSE echo for benchmarking.

        Accepts JSON messages and echoes them back with a server_timestamp,
        identical to POST /sse/echo but over a persistent WebSocket connection.
        """
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                msg["server_timestamp"] = time.time()
                await websocket.send_text(json.dumps(msg))
        except WebSocketDisconnect:
            pass

    return router
