"""
Integration tests for the StreamManager lifecycle (001-tool-stream-ui).

This file is the canonical lifecycle test — story phases extend it:
- US1 (T036): test_us1_happy_path — subscribe → first chunk → ui_stream_data.
- US2 (T048): test_us2_pause_on_load_chat / test_us2_pause_on_disconnect.
- US3 (T058): test_us3_resume_on_return / test_us3_resume_when_agent_gone.

Tests use a mock StreamManager wired with AsyncMock dependencies — no real
agent process or websocket server is required. The fan-out and auth-bypass
properties are exercised in dedicated files (test_stream_fanout.py and
test_stream_reconnect.py).
"""
import asyncio
import json
import os
import sys
import time
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orchestrator.stream_manager import (
    StreamManager,
    StreamState,
    StreamSubscription,
    classify_error,
)
from shared.protocol import ToolStreamData, ToolStreamEnd


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

class FakeWebSocket:
    """Minimal websocket double — tracks messages sent to it for assertion."""
    def __init__(self):
        self.sent: list = []
        self.closed = False

    def __hash__(self):
        return id(self)


def _make_manager_with_dispatcher(dispatcher_returns_request_id: str = "req-1"):
    """Build a StreamManager with mocked dependencies that returns a fixed
    request_id from the agent dispatcher. Returns (manager, deps) for
    assertions."""
    rote = Mock()
    # ROTE.adapt is called per chunk; pass through unchanged.
    rote.adapt = Mock(side_effect=lambda ws, components: components)
    send_to_ws = AsyncMock()
    sessions = {}
    def get_session(ws):
        return sessions.get(ws)
    dispatcher = AsyncMock(return_value=dispatcher_returns_request_id)
    canceller = AsyncMock()
    mgr = StreamManager(
        rote=rote,
        send_to_ws=send_to_ws,
        get_user_session=get_session,
        agent_dispatcher=dispatcher,
        agent_canceller=canceller,
        validate_chat_ownership=None,  # skip ownership check in tests
    )
    return mgr, {
        "rote": rote, "send_to_ws": send_to_ws, "sessions": sessions,
        "dispatcher": dispatcher, "canceller": canceller,
    }


# ---------------------------------------------------------------------------
# US1: happy path — subscribe → first chunk → fanned out as ui_stream_data
# ---------------------------------------------------------------------------

class TestUS1HappyPath:
    @pytest.mark.asyncio
    async def test_subscribe_creates_active_entry(self):
        mgr, deps = _make_manager_with_dispatcher("req-test-1")
        ws = FakeWebSocket()
        deps["sessions"][ws] = {"sub": "alice"}

        stream_id, attached = await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="chat-1",
            tool_name="live_temperature", agent_id="weather",
            params={"latitude": 51.5, "longitude": -0.12, "interval_s": 5},
        )

        assert stream_id.startswith("stream-")
        assert attached is False
        assert len(mgr._active) == 1
        sub = next(iter(mgr._active.values()))
        assert sub.stream_id == stream_id
        assert sub.state == StreamState.STARTING  # no chunk yet
        assert sub.subscribers == [ws]
        assert sub.user_id == "alice"
        assert sub.chat_id == "chat-1"
        assert sub.request_id == "req-test-1"
        assert mgr._request_to_key["req-test-1"] == sub.key
        deps["dispatcher"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_subscribe_rejects_when_session_missing(self):
        mgr, deps = _make_manager_with_dispatcher()
        ws = FakeWebSocket()
        # No session entry → reject
        with pytest.raises(ValueError, match="no active session"):
            await mgr.subscribe(
                ws=ws, user_id="alice", chat_id="c1",
                tool_name="t", agent_id="a", params={},
            )

    @pytest.mark.asyncio
    async def test_subscribe_rejects_user_mismatch(self):
        mgr, deps = _make_manager_with_dispatcher()
        ws = FakeWebSocket()
        deps["sessions"][ws] = {"sub": "alice"}
        with pytest.raises(ValueError, match="user_id does not match"):
            await mgr.subscribe(
                ws=ws, user_id="bob", chat_id="c1",
                tool_name="t", agent_id="a", params={},
            )

    @pytest.mark.asyncio
    async def test_first_chunk_transitions_to_active_and_sends(self):
        mgr, deps = _make_manager_with_dispatcher("req-1")
        ws = FakeWebSocket()
        deps["sessions"][ws] = {"sub": "alice"}
        stream_id, _ = await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="chat-1",
            tool_name="live_temperature", agent_id="weather",
            params={"latitude": 51.5, "longitude": -0.12},
        )

        # Agent emits a chunk
        chunk_msg = ToolStreamData(
            request_id="req-1",
            stream_id=stream_id,
            agent_id="weather",
            tool_name="live_temperature",
            seq=1,
            components=[{"type": "metric", "id": stream_id, "value": "12C"}],
        )
        await mgr.handle_agent_chunk(chunk_msg)
        # Give the spawned send task a chance to run.
        await asyncio.sleep(0.05)

        sub = mgr._active[next(iter(mgr._active))]
        assert sub.state == StreamState.ACTIVE
        assert sub.delivered_count >= 1
        # Verify a ui_stream_data wire message was sent to the subscriber
        assert deps["send_to_ws"].await_count >= 1
        sent_args = deps["send_to_ws"].await_args_list[0]
        sent_ws, sent_payload = sent_args.args
        assert sent_ws is ws
        wire = json.loads(sent_payload)
        assert wire["type"] == "ui_stream_data"
        assert wire["stream_id"] == stream_id
        assert wire["session_id"] == "chat-1"
        assert wire["seq"] == 1
        assert wire["components"][0]["value"] == "12C"
        assert wire["components"][0]["id"] == stream_id

    @pytest.mark.asyncio
    async def test_multiple_chunks_increment_delivered(self):
        mgr, deps = _make_manager_with_dispatcher("req-1")
        ws = FakeWebSocket()
        deps["sessions"][ws] = {"sub": "alice"}
        stream_id, _ = await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="chat-1",
            tool_name="live_temperature", agent_id="weather",
            params={"latitude": 51.5, "longitude": -0.12},
        )

        for i in range(3):
            await mgr.handle_agent_chunk(ToolStreamData(
                request_id="req-1", stream_id=stream_id,
                agent_id="weather", tool_name="live_temperature",
                seq=i + 1,
                components=[{"type": "metric", "id": stream_id, "value": str(i)}],
            ))
            await asyncio.sleep(0.15)  # exceed the 1/max_fps gate

        sub = mgr._active[next(iter(mgr._active))]
        # Send loop may coalesce; we just check at least one was delivered.
        assert sub.delivered_count >= 1
        assert deps["send_to_ws"].await_count >= 1

    @pytest.mark.asyncio
    async def test_handle_agent_end_sends_terminal_and_cleans_up(self):
        mgr, deps = _make_manager_with_dispatcher("req-1")
        ws = FakeWebSocket()
        deps["sessions"][ws] = {"sub": "alice"}
        stream_id, _ = await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="chat-1",
            tool_name="live_temperature", agent_id="weather",
            params={"latitude": 51.5, "longitude": -0.12},
        )
        await mgr.handle_agent_end(ToolStreamEnd(request_id="req-1", stream_id=stream_id))
        # Subscription torn down
        assert stream_id not in [s.stream_id for s in mgr._active.values()]
        assert "req-1" not in mgr._request_to_key
        # A terminal ui_stream_data went out
        terminal_calls = [
            call for call in deps["send_to_ws"].await_args_list
            if "terminal" in call.args[1] and json.loads(call.args[1]).get("terminal") is True
        ]
        assert len(terminal_calls) == 1

    @pytest.mark.asyncio
    async def test_unknown_request_id_chunk_dropped_silently(self):
        mgr, _ = _make_manager_with_dispatcher()
        # No subscription registered
        await mgr.handle_agent_chunk(ToolStreamData(
            request_id="never-existed", stream_id="x", agent_id="a",
            tool_name="t", seq=1,
        ))
        # No exception, no state change
        assert len(mgr._active) == 0

    @pytest.mark.asyncio
    async def test_per_user_cap_enforced(self):
        # 11th subscription on the same user should fail
        from orchestrator.stream_manager import MAX_STREAM_SUBSCRIPTIONS
        mgr, deps = _make_manager_with_dispatcher()
        ws = FakeWebSocket()
        deps["sessions"][ws] = {"sub": "alice"}
        for i in range(MAX_STREAM_SUBSCRIPTIONS):
            await mgr.subscribe(
                ws=ws, user_id="alice", chat_id=f"chat-{i}",
                tool_name="t", agent_id="a", params={"k": i},
            )
        with pytest.raises(ValueError, match="limit"):
            await mgr.subscribe(
                ws=ws, user_id="alice", chat_id="chat-overflow",
                tool_name="t", agent_id="a", params={"k": "extra"},
            )


# ---------------------------------------------------------------------------
# US2: pause-on-leave (T048, T049, T050)
# ---------------------------------------------------------------------------

class TestUS2PauseOnLeave:
    @pytest.mark.asyncio
    async def test_pause_on_load_chat_moves_to_dormant(self):
        mgr, deps = _make_manager_with_dispatcher("req-1")
        ws = FakeWebSocket()
        deps["sessions"][ws] = {"sub": "alice"}
        stream_id, _ = await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="chat-1",
            tool_name="live_temperature", agent_id="weather", params={},
        )
        # Verify subscription is active
        assert len(mgr._active) == 1

        # User navigates to chat-2; orchestrator calls pause_chat
        await mgr.pause_chat(ws, "chat-1")

        # Subscription should now be dormant, not active
        assert len(mgr._active) == 0
        assert ("alice", "chat-1") in mgr._dormant
        dormant_sub = mgr._dormant[("alice", "chat-1")][next(iter(mgr._dormant[("alice", "chat-1")]))]
        assert dormant_sub.state == StreamState.DORMANT
        assert dormant_sub.subscribers == []
        assert dormant_sub.task is None
        # Agent canceller was called
        deps["canceller"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_moves_all_to_dormant(self):
        mgr, deps = _make_manager_with_dispatcher("req-1")
        ws = FakeWebSocket()
        deps["sessions"][ws] = {"sub": "alice"}
        await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="chat-1",
            tool_name="t1", agent_id="a", params={"k": 1},
        )
        # Test only one subscription per dispatcher fixture (it returns the
        # same request_id) — that's enough to verify the path.
        assert len(mgr._active) == 1

        await mgr.detach(ws)

        assert len(mgr._active) == 0
        assert ("alice", "chat-1") in mgr._dormant

    @pytest.mark.asyncio
    async def test_pause_chat_only_affects_named_chat(self):
        # Subscribe to chat-1 with one ws, chat-2 with another (same user)
        mgr, deps = _make_manager_with_dispatcher("req-1")
        ws1 = FakeWebSocket()
        ws2 = FakeWebSocket()
        deps["sessions"][ws1] = {"sub": "alice"}
        deps["sessions"][ws2] = {"sub": "alice"}

        # subscribe ws1 to chat-1
        await mgr.subscribe(
            ws=ws1, user_id="alice", chat_id="chat-1",
            tool_name="t1", agent_id="a", params={"k": 1},
        )
        # subscribe ws2 to chat-2 — different chat, different params_hash
        await mgr.subscribe(
            ws=ws2, user_id="alice", chat_id="chat-2",
            tool_name="t1", agent_id="a", params={"k": 2},
        )
        assert len(mgr._active) == 2

        # Pause only chat-1's streams from ws1 — should NOT touch chat-2
        await mgr.pause_chat(ws1, "chat-1")
        active_chats = {sub.chat_id for sub in mgr._active.values()}
        assert active_chats == {"chat-2"}
        assert ("alice", "chat-1") in mgr._dormant
        assert ("alice", "chat-2") not in mgr._dormant

    @pytest.mark.asyncio
    async def test_dormant_ttl_eviction(self):
        from orchestrator.stream_manager import DORMANT_TTL_SECONDS
        mgr, deps = _make_manager_with_dispatcher("req-1")
        ws = FakeWebSocket()
        deps["sessions"][ws] = {"sub": "alice"}
        await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="chat-1",
            tool_name="t", agent_id="a", params={},
        )
        await mgr.detach(ws)
        # Confirm in dormant
        assert ("alice", "chat-1") in mgr._dormant

        # Force the dormant entry's created_at to look ancient
        sub = next(iter(mgr._dormant[("alice", "chat-1")].values()))
        sub.created_at = sub.created_at - DORMANT_TTL_SECONDS - 10

        mgr._sweep_dormant_ttl()

        assert ("alice", "chat-1") not in mgr._dormant

    @pytest.mark.asyncio
    async def test_dormant_lru_eviction(self):
        from orchestrator.stream_manager import MAX_DORMANT_PER_USER
        mgr, deps = _make_manager_with_dispatcher("req-1")
        ws = FakeWebSocket()
        deps["sessions"][ws] = {"sub": "alice"}
        # Fill the dormant cap
        for i in range(MAX_DORMANT_PER_USER):
            await mgr.subscribe(
                ws=ws, user_id="alice", chat_id=f"chat-{i}",
                tool_name="t", agent_id="a", params={"k": i},
            )
            await mgr.detach(ws)
            # Re-attach the session for the next subscribe
            deps["sessions"][ws] = {"sub": "alice"}
        assert mgr._count_dormant_for_user("alice") == MAX_DORMANT_PER_USER

        # One more dormant — should evict the oldest, total stays at the cap
        await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="chat-overflow",
            tool_name="t", agent_id="a", params={"k": "extra"},
        )
        await mgr.detach(ws)
        assert mgr._count_dormant_for_user("alice") == MAX_DORMANT_PER_USER


# ---------------------------------------------------------------------------
# US3: resume-on-return (T058, T059)
# ---------------------------------------------------------------------------

class TestUS3ResumeOnReturn:
    @pytest.mark.asyncio
    async def test_resume_after_pause_with_same_stream_id(self):
        mgr, deps = _make_manager_with_dispatcher("req-1")
        ws = FakeWebSocket()
        deps["sessions"][ws] = {"sub": "alice"}
        original_id, _ = await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="chat-1",
            tool_name="t", agent_id="a", params={"k": 1},
        )
        # Leave
        await mgr.pause_chat(ws, "chat-1")
        assert ("alice", "chat-1") in mgr._dormant

        # Now return — set the dispatcher to return a fresh request_id
        deps["dispatcher"].return_value = "req-resumed"
        resumed = await mgr.resume(ws, "alice", "chat-1")
        assert len(resumed) == 1
        resumed_stream_id, resumed_tool = resumed[0]
        # Same stream_id (so the frontend's existing component merges chunks)
        assert resumed_stream_id == original_id
        assert resumed_tool == "t"
        # Now in active again
        assert ("alice", "chat-1") not in mgr._dormant
        sub = next(iter(mgr._active.values()))
        assert sub.state == StreamState.STARTING
        assert sub.subscribers == [ws]
        # New request_id was registered
        assert sub.request_id == "req-resumed"
        assert deps["dispatcher"].await_count == 2  # original + resumed

    @pytest.mark.asyncio
    async def test_resume_with_no_dormant_returns_empty(self):
        mgr, deps = _make_manager_with_dispatcher()
        ws = FakeWebSocket()
        deps["sessions"][ws] = {"sub": "alice"}
        resumed = await mgr.resume(ws, "alice", "chat-fresh")
        assert resumed == []

    @pytest.mark.asyncio
    async def test_resume_when_agent_gone_sends_failure_chunk(self):
        # First subscribe normally, leave, then resume with a dispatcher
        # that raises (simulating an agent that disconnected meanwhile).
        mgr, deps = _make_manager_with_dispatcher("req-1")
        ws = FakeWebSocket()
        deps["sessions"][ws] = {"sub": "alice"}
        await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="chat-1",
            tool_name="t", agent_id="a", params={"k": 1},
        )
        await mgr.pause_chat(ws, "chat-1")

        # Make the dispatcher raise on the resume attempt
        deps["dispatcher"].side_effect = RuntimeError("agent gone")

        resumed = await mgr.resume(ws, "alice", "chat-1")
        # The subscription does not appear in resumed (dispatch failed)
        assert resumed == []
        # The user got an error chunk
        sent = [json.loads(call.args[1]) for call in deps["send_to_ws"].await_args_list]
        # Find the failure chunk
        failure_msgs = [
            m for m in sent
            if m.get("error") and m["error"].get("phase") == "failed"
        ]
        assert len(failure_msgs) >= 1
        assert failure_msgs[-1]["error"]["code"] == "upstream_unavailable"
        assert failure_msgs[-1]["error"]["retryable"] is True
        # And the subscription is gone (not in active or dormant)
        assert ("alice", "chat-1") not in mgr._dormant
        assert len(mgr._active) == 0
