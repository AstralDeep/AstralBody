"""
Cross-user isolation tests for StreamManager (001-tool-stream-ui US4 T068).

Verifies the FR-011 / SC-004 invariant: stream data is delivered ONLY to
the user who initiated it. No cross-user leak is possible by design (the
StreamKey first element is user_id), but these tests are the runtime
enforcement check that catches any future regression.
"""
import json
import os
import sys
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orchestrator.stream_manager import StreamManager, StreamState
from shared.protocol import ToolStreamData


class FakeWS:
    def __init__(self, label: str):
        self.label = label
        self.sent: list = []

    def __repr__(self):
        return f"<FakeWS {self.label}>"


def _make_isolated_manager():
    rote = Mock()
    rote.adapt = Mock(side_effect=lambda ws, c: c)
    sessions: dict = {}
    sent_log: list = []  # (ws, payload) pairs
    async def send_to_ws(ws, payload):
        sent_log.append((ws, payload))
    dispatcher = AsyncMock()
    dispatcher.return_value = "req-stub"
    canceller = AsyncMock()
    mgr = StreamManager(
        rote=rote,
        send_to_ws=send_to_ws,
        get_user_session=lambda ws: sessions.get(ws),
        agent_dispatcher=dispatcher,
        agent_canceller=canceller,
        validate_chat_ownership=None,
    )
    return mgr, sessions, sent_log, dispatcher


@pytest.mark.asyncio
async def test_two_users_no_crossleak():
    """User A and User B subscribe to the same tool with different params.
    Each user must only receive their own chunks."""
    mgr, sessions, sent_log, dispatcher = _make_isolated_manager()
    ws_a = FakeWS("alice")
    ws_b = FakeWS("bob")
    sessions[ws_a] = {"sub": "alice"}
    sessions[ws_b] = {"sub": "bob"}

    dispatcher.side_effect = ["req-alice", "req-bob"]

    sid_a, _ = await mgr.subscribe(
        ws=ws_a, user_id="alice", chat_id="chat-a",
        tool_name="live_temperature", agent_id="weather",
        params={"latitude": 51.5, "longitude": -0.12},
    )
    sid_b, _ = await mgr.subscribe(
        ws=ws_b, user_id="bob", chat_id="chat-b",
        tool_name="live_temperature", agent_id="weather",
        params={"latitude": 40.7, "longitude": -74.0},
    )
    assert sid_a != sid_b  # distinct streams
    assert len(mgr._active) == 2

    # Agent emits chunks for each
    await mgr.handle_agent_chunk(ToolStreamData(
        request_id="req-alice", stream_id=sid_a, agent_id="weather",
        tool_name="live_temperature", seq=1,
        components=[{"type": "metric", "id": sid_a, "value": "alice-data"}],
    ))
    await mgr.handle_agent_chunk(ToolStreamData(
        request_id="req-bob", stream_id=sid_b, agent_id="weather",
        tool_name="live_temperature", seq=1,
        components=[{"type": "metric", "id": sid_b, "value": "bob-data"}],
    ))
    import asyncio
    await asyncio.sleep(0.1)

    # Verify: alice's ws only saw alice's data, bob's only saw bob's
    alice_msgs = [json.loads(p) for w, p in sent_log if w is ws_a]
    bob_msgs = [json.loads(p) for w, p in sent_log if w is ws_b]
    assert all(m["stream_id"] == sid_a for m in alice_msgs)
    assert all(m["stream_id"] == sid_b for m in bob_msgs)
    # Alice never saw bob's data
    assert not any("bob-data" in str(m) for m in alice_msgs)
    assert not any("alice-data" in str(m) for m in bob_msgs)


@pytest.mark.asyncio
async def test_unauthorized_unsubscribe_rejected():
    """User A cannot unsubscribe a stream owned by User B."""
    mgr, sessions, sent_log, dispatcher = _make_isolated_manager()
    ws_a = FakeWS("alice")
    ws_b = FakeWS("bob")
    sessions[ws_a] = {"sub": "alice"}
    sessions[ws_b] = {"sub": "bob"}

    dispatcher.side_effect = ["req-alice", "req-bob"]
    sid_a, _ = await mgr.subscribe(
        ws=ws_a, user_id="alice", chat_id="ca",
        tool_name="t", agent_id="a", params={},
    )
    sid_b, _ = await mgr.subscribe(
        ws=ws_b, user_id="bob", chat_id="cb",
        tool_name="t", agent_id="a", params={},
    )

    # User A's ws tries to unsubscribe User B's stream
    with pytest.raises(ValueError, match="not authorized"):
        await mgr.unsubscribe(ws_a, sid_b)
    # B's stream is unaffected
    assert any(s.stream_id == sid_b for s in mgr._active.values())


@pytest.mark.asyncio
async def test_per_subscriber_auth_failure_isolates_to_failing_ws():
    """One subscriber's token expiry must not affect other subscribers of
    the same fanned-out stream."""
    mgr, sessions, sent_log, dispatcher = _make_isolated_manager()
    ws_good = FakeWS("good-tab")
    ws_bad = FakeWS("expired-tab")
    sessions[ws_good] = {"sub": "alice", "expires_at": 0}  # 0 = no expiry check passes
    sessions[ws_bad] = {"sub": "alice", "expires_at": 0}

    dispatcher.return_value = "req-1"
    sid, attached = await mgr.subscribe(
        ws=ws_good, user_id="alice", chat_id="chat-1",
        tool_name="t", agent_id="a", params={"k": 1},
    )
    assert attached is False
    # Same user attaches second tab (FR-009a dedup → same stream)
    sid2, attached2 = await mgr.subscribe(
        ws=ws_bad, user_id="alice", chat_id="chat-1",
        tool_name="t", agent_id="a", params={"k": 1},
    )
    assert sid == sid2
    assert attached2 is True
    sub = mgr._active[next(iter(mgr._active))]
    assert len(sub.subscribers) == 2

    # Now ws_bad's token expires
    import time as time_mod
    sessions[ws_bad]["expires_at"] = int(time_mod.time()) - 60

    # Agent emits a chunk
    await mgr.handle_agent_chunk(ToolStreamData(
        request_id="req-1", stream_id=sid, agent_id="a", tool_name="t",
        seq=1, components=[{"type": "metric", "id": sid, "value": "12C"}],
    ))
    import asyncio
    await asyncio.sleep(0.1)

    # ws_good received the data chunk
    good_msgs = [json.loads(p) for w, p in sent_log if w is ws_good]
    assert any(m["components"] and m["components"][0].get("value") == "12C" for m in good_msgs)
    # ws_bad received an unauthenticated error chunk
    bad_msgs = [json.loads(p) for w, p in sent_log if w is ws_bad]
    auth_errs = [m for m in bad_msgs if m.get("error", {}).get("code") == "unauthenticated"]
    assert len(auth_errs) >= 1
    # ws_bad was removed from subscribers
    assert ws_bad not in sub.subscribers
    assert ws_good in sub.subscribers
