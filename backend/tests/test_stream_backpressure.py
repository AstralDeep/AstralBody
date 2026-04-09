"""
Backpressure / coalescing tests (001-tool-stream-ui Phase 8 T091).

Verifies FR-016 / SC-006: when a tool emits chunks faster than the UI can
render, the orchestrator MUST coalesce or drop intermediate values rather
than queueing unboundedly. The single-slot last-write-wins semantics from
research §7 are the runtime enforcement.
"""
import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orchestrator.stream_manager import StreamManager
from shared.protocol import ToolStreamData


class FakeWS:
    pass


@pytest.mark.asyncio
async def test_high_rate_source_coalesces_to_single_slot():
    """Emit 100 chunks back-to-back. The send loop is gated by max_fps so
    most chunks should be coalesced — drop count should be high."""
    sessions = {}
    sent = []
    sent_lock = asyncio.Lock()

    async def send(ws, payload):
        # Make the send slow enough to force coalescing on subsequent chunks
        async with sent_lock:
            await asyncio.sleep(0.005)
            sent.append((ws, payload))

    rote = Mock()
    rote.adapt = Mock(side_effect=lambda ws, c: c)
    dispatcher = AsyncMock()
    dispatcher.return_value = "req-1"
    mgr = StreamManager(
        rote=rote, send_to_ws=send,
        get_user_session=lambda ws: sessions.get(ws),
        agent_dispatcher=dispatcher, agent_canceller=AsyncMock(),
        validate_chat_ownership=None,
    )
    ws = FakeWS()
    sessions[ws] = {"sub": "alice"}
    sid, _ = await mgr.subscribe(
        ws=ws, user_id="alice", chat_id="c", tool_name="t",
        agent_id="a", params={}, tool_metadata={"max_fps": 30, "min_fps": 5},
    )

    # Fire 100 chunks rapidly
    for i in range(100):
        await mgr.handle_agent_chunk(ToolStreamData(
            request_id="req-1", stream_id=sid, agent_id="a", tool_name="t",
            seq=i + 1, components=[{"type": "metric", "id": sid, "value": str(i)}],
        ))
    # Let the send loop drain
    await asyncio.sleep(1.5)

    sub = next(iter(mgr._active.values()))
    # Coalescing must have happened — many chunks dropped
    assert sub.dropped_count > 0
    # The total delivered + dropped should account for ~all input chunks
    # (delivered_count is per-subscriber-send, here only one ws)
    assert sub.delivered_count + sub.dropped_count >= 90
    # And the rate cap held: at no point did we send more than ~30/s.
    # Over a ~1.5s window that's at most ~45 sends. Allow some slack.
    assert sub.delivered_count <= 60

    # The last-delivered chunk should be the LAST input value (last-write-wins)
    delivered_msgs = [json.loads(p) for w, p in sent]
    # Some chunks may be terminal, drop those
    data_msgs = [m for m in delivered_msgs if m.get("components") and m["components"]]
    if data_msgs:
        last = data_msgs[-1]
        # The last delivered value should be one of the last few inputs
        last_value_int = int(last["components"][0]["value"])
        assert last_value_int >= 80, (
            f"expected last-write-wins to deliver a near-final value, got {last_value_int}"
        )


@pytest.mark.asyncio
async def test_coalesce_slot_is_single_element():
    """At every moment, sub.coalesce_slot is at most one chunk — the
    invariant that bounds memory."""
    sessions = {}
    sent = []
    async def send(ws, payload):
        await asyncio.sleep(0.05)  # very slow consumer
        sent.append((ws, payload))
    rote = Mock()
    rote.adapt = Mock(side_effect=lambda ws, c: c)
    dispatcher = AsyncMock()
    dispatcher.return_value = "req-1"
    mgr = StreamManager(
        rote=rote, send_to_ws=send,
        get_user_session=lambda ws: sessions.get(ws),
        agent_dispatcher=dispatcher, agent_canceller=AsyncMock(),
        validate_chat_ownership=None,
    )
    ws = FakeWS()
    sessions[ws] = {"sub": "alice"}
    sid, _ = await mgr.subscribe(
        ws=ws, user_id="alice", chat_id="c", tool_name="t",
        agent_id="a", params={},
    )

    # Fire 10 chunks while sends are slow
    for i in range(10):
        await mgr.handle_agent_chunk(ToolStreamData(
            request_id="req-1", stream_id=sid, agent_id="a", tool_name="t",
            seq=i + 1, components=[{"type": "metric", "id": sid, "value": str(i)}],
        ))
        # The slot must be a single value, not a queue
        sub = next(iter(mgr._active.values()))
        # Either None (just drained) or a single StreamChunk reference
        assert sub.coalesce_slot is None or hasattr(sub.coalesce_slot, "stream_id")

    # Drain
    await asyncio.sleep(1.0)
