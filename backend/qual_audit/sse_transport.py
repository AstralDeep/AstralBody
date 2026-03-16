"""Minimal SSE endpoint for academic transport benchmarking.

This module exists solely to provide an empirical comparison between
WebSocket and Server-Sent Events. It is NOT a production transport.
"""

import asyncio
import json
import time
import uuid
from typing import AsyncGenerator, Dict

from starlette.requests import Request
from starlette.responses import StreamingResponse
from fastapi import APIRouter


def create_sse_router() -> APIRouter:
    """Create a FastAPI router with a minimal SSE endpoint."""
    router = APIRouter()

    # Per-connection message queues
    _connections: Dict[str, asyncio.Queue] = {}

    async def _event_stream(
        queue: asyncio.Queue, conn_id: str
    ) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted events from the queue."""
        try:
            while True:
                msg = await queue.get()
                if msg is None:
                    break
                event_id = msg.get("id", str(uuid.uuid4()))
                data = json.dumps(msg)
                yield f"id: {event_id}\nevent: message\ndata: {data}\n\n"
        finally:
            _connections.pop(conn_id, None)

    @router.get("/sse")
    async def sse_endpoint(request: Request):
        """SSE endpoint — mirrors WebSocket message flow for benchmarking."""
        conn_id = str(uuid.uuid4())
        queue: asyncio.Queue = asyncio.Queue()
        _connections[conn_id] = queue

        # Send initial connection confirmation
        await queue.put({
            "type": "connected",
            "connection_id": conn_id,
            "timestamp": time.time(),
        })

        return StreamingResponse(
            _event_stream(queue, conn_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Connection-Id": conn_id,
            },
        )

    @router.post("/sse/send/{conn_id}")
    async def sse_send(conn_id: str, request: Request):
        """Push a message to a specific SSE connection (for benchmarking)."""
        queue = _connections.get(conn_id)
        if not queue:
            return {"error": "connection not found"}
        body = await request.json()
        body["server_timestamp"] = time.time()
        body["id"] = body.get("id", str(uuid.uuid4()))
        await queue.put(body)
        return {"status": "sent", "id": body["id"]}

    @router.post("/sse/echo")
    async def sse_echo(request: Request):
        """Echo endpoint — returns the message with a server timestamp.

        Used for latency measurement without requiring SSE connection.
        """
        body = await request.json()
        body["server_timestamp"] = time.time()
        return body

    @router.post("/sse/broadcast")
    async def sse_broadcast(request: Request):
        """Broadcast a message to all SSE connections."""
        body = await request.json()
        body["server_timestamp"] = time.time()
        body["id"] = body.get("id", str(uuid.uuid4()))
        for queue in _connections.values():
            await queue.put(body)
        return {"status": "broadcast", "connections": len(_connections)}

    @router.delete("/sse/{conn_id}")
    async def sse_disconnect(conn_id: str):
        """Cleanly close an SSE connection."""
        queue = _connections.get(conn_id)
        if queue:
            await queue.put(None)
        return {"status": "disconnected"}

    # Expose internals for test access
    router._connections = _connections  # type: ignore[attr-defined]

    return router
