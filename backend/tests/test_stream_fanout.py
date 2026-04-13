"""
Multi-tab fan-out tests for StreamManager (001-tool-stream-ui US4 T069).

Verifies FR-009a: when the same user has the same chat loaded in multiple
client sessions, the orchestrator deduplicates by
(user_id, chat_id, tool_name, params_hash) and fans the chunks out to every
client session. Counts as one against the per-user concurrency cap.
"""
import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orchestrator.stream_manager import StreamManager, StreamState
from shared.protocol import ToolStreamData, ToolStreamEnd


class FakeWS:
    def __init__(self, label: str = ""):
        self.label = label

    def __repr__(self):
        return f"<FakeWS {self.label}>"


def _make_manager():
    rote = Mock()
    rote.adapt = Mock(side_effect=lambda ws, c: c)
    sessions: dict = {}
    sent_log: list = []
    async def send_to_ws(ws, payload):
        sent_log.append((ws, payload))
    dispatcher = AsyncMock()
    dispatcher.return_value = "req-1"
    canceller = AsyncMock()
    mgr = StreamManager(
        rote=rote, send_to_ws=send_to_ws,
        get_user_session=lambda ws: sessions.get(ws),
        agent_dispatcher=dispatcher,
        agent_canceller=canceller,
        validate_chat_ownership=None,
    )
    return mgr, sessions, sent_log, dispatcher, canceller


@pytest.mark.asyncio
async def test_two_tabs_dedup_to_one_subscription():
    """Same user, same chat, same tool, same params from two ws → one
    subscription with two subscribers, single agent dispatch."""
    mgr, sessions, sent_log, dispatcher, _ = _make_manager()
    tab1 = FakeWS("tab1")
    tab2 = FakeWS("tab2")
    sessions[tab1] = {"sub": "alice"}
    sessions[tab2] = {"sub": "alice"}

    sid1, attached1 = await mgr.subscribe(
        ws=tab1, user_id="alice", chat_id="chat-1",
        tool_name="t", agent_id="a", params={"k": 1},
    )
    assert attached1 is False
    assert dispatcher.await_count == 1

    sid2, attached2 = await mgr.subscribe(
        ws=tab2, user_id="alice", chat_id="chat-1",
        tool_name="t", agent_id="a", params={"k": 1},
    )
    assert sid2 == sid1  # same stream_id
    assert attached2 is True
    # Dispatcher was NOT called a second time
    assert dispatcher.await_count == 1
    # The subscription has both tabs
    assert len(mgr._active) == 1
    sub = next(iter(mgr._active.values()))
    assert tab1 in sub.subscribers
    assert tab2 in sub.subscribers
    assert len(sub.subscribers) == 2


@pytest.mark.asyncio
async def test_chunk_fanned_out_to_all_subscribers_at_same_seq():
    """A single chunk arriving from the agent must be delivered to BOTH
    tabs at the same seq."""
    mgr, sessions, sent_log, dispatcher, _ = _make_manager()
    tab1 = FakeWS("tab1")
    tab2 = FakeWS("tab2")
    sessions[tab1] = {"sub": "alice"}
    sessions[tab2] = {"sub": "alice"}

    sid, _ = await mgr.subscribe(
        ws=tab1, user_id="alice", chat_id="chat-1",
        tool_name="t", agent_id="a", params={"k": 1},
    )
    await mgr.subscribe(
        ws=tab2, user_id="alice", chat_id="chat-1",
        tool_name="t", agent_id="a", params={"k": 1},
    )

    await mgr.handle_agent_chunk(ToolStreamData(
        request_id="req-1", stream_id=sid, agent_id="a", tool_name="t",
        seq=42, components=[{"type": "metric", "id": sid, "value": "12C"}],
    ))
    await asyncio.sleep(0.1)

    # Each tab received the chunk
    tab1_msgs = [json.loads(p) for w, p in sent_log if w is tab1]
    tab2_msgs = [json.loads(p) for w, p in sent_log if w is tab2]
    assert any(m["seq"] == 42 for m in tab1_msgs)
    assert any(m["seq"] == 42 for m in tab2_msgs)
    # Same value
    tab1_data = [m for m in tab1_msgs if m["seq"] == 42][0]
    tab2_data = [m for m in tab2_msgs if m["seq"] == 42][0]
    assert tab1_data["components"][0]["value"] == "12C"
    assert tab2_data["components"][0]["value"] == "12C"


@pytest.mark.asyncio
async def test_first_subscriber_leaves_stream_continues_for_other():
    """When the first tab disconnects, the stream stays ACTIVE for the
    second tab. No ToolStreamCancel is sent."""
    mgr, sessions, sent_log, dispatcher, canceller = _make_manager()
    tab1 = FakeWS("tab1")
    tab2 = FakeWS("tab2")
    sessions[tab1] = {"sub": "alice"}
    sessions[tab2] = {"sub": "alice"}

    sid, _ = await mgr.subscribe(
        ws=tab1, user_id="alice", chat_id="chat-1",
        tool_name="t", agent_id="a", params={"k": 1},
    )
    await mgr.subscribe(
        ws=tab2, user_id="alice", chat_id="chat-1",
        tool_name="t", agent_id="a", params={"k": 1},
    )
    assert canceller.await_count == 0

    # tab1 disconnects
    await mgr.detach(tab1)

    # Stream still active
    assert len(mgr._active) == 1
    sub = next(iter(mgr._active.values()))
    assert sub.state in (StreamState.STARTING, StreamState.ACTIVE)
    assert tab1 not in sub.subscribers
    assert tab2 in sub.subscribers
    # Cancel was NOT sent
    assert canceller.await_count == 0


@pytest.mark.asyncio
async def test_last_subscriber_leaves_goes_dormant():
    """Both tabs leaving → subscription transitions to DORMANT and
    ToolStreamCancel is sent to the agent."""
    mgr, sessions, sent_log, dispatcher, canceller = _make_manager()
    tab1 = FakeWS("tab1")
    tab2 = FakeWS("tab2")
    sessions[tab1] = {"sub": "alice"}
    sessions[tab2] = {"sub": "alice"}

    await mgr.subscribe(
        ws=tab1, user_id="alice", chat_id="chat-1",
        tool_name="t", agent_id="a", params={"k": 1},
    )
    await mgr.subscribe(
        ws=tab2, user_id="alice", chat_id="chat-1",
        tool_name="t", agent_id="a", params={"k": 1},
    )

    await mgr.detach(tab1)
    await mgr.detach(tab2)

    # Now dormant
    assert len(mgr._active) == 0
    assert ("alice", "chat-1") in mgr._dormant
    # Cancel was sent exactly once (when the last subscriber left)
    assert canceller.await_count == 1


@pytest.mark.asyncio
async def test_attach_does_not_count_against_per_user_cap():
    """Multi-tab attach uses one slot, not N slots."""
    from orchestrator.stream_manager import MAX_STREAM_SUBSCRIPTIONS
    mgr, sessions, sent_log, dispatcher, _ = _make_manager()
    tab1 = FakeWS("tab1")
    sessions[tab1] = {"sub": "alice"}

    # Max out alice's cap with 10 distinct streams
    for i in range(MAX_STREAM_SUBSCRIPTIONS):
        await mgr.subscribe(
            ws=tab1, user_id="alice", chat_id=f"chat-{i}",
            tool_name="t", agent_id="a", params={"k": i},
        )
    assert mgr._count_active_for_user("alice") == MAX_STREAM_SUBSCRIPTIONS

    # A NEW tab attaches to one of the existing streams — this is allowed
    tab2 = FakeWS("tab2")
    sessions[tab2] = {"sub": "alice"}
    sid, attached = await mgr.subscribe(
        ws=tab2, user_id="alice", chat_id="chat-0",
        tool_name="t", agent_id="a", params={"k": 0},
    )
    assert attached is True
    # Cap is unchanged
    assert mgr._count_active_for_user("alice") == MAX_STREAM_SUBSCRIPTIONS

    # A NEW distinct subscription (different params) STILL exceeds the cap
    with pytest.raises(ValueError, match="limit"):
        await mgr.subscribe(
            ws=tab1, user_id="alice", chat_id="chat-overflow",
            tool_name="t", agent_id="a", params={"k": "extra"},
        )
