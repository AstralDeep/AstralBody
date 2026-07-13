"""055-uniform-artifacts US2 (T019) — stream→workspace identity bridge.

With FF_STREAM_ARTIFACTS on, ``StreamManager.subscribe`` assigns the
workspace rule-2 fingerprint to ``StreamSubscription.component_id``, every
``ui_stream_data`` frame carries it, and the newest content-bearing chunk is
retained on the subscription for the orchestrator's persist-on-terminal
(T020). Flag off: frames stay byte-identical to pre-055 and nothing is
retained. Narrative (``narrative-*``) and legacy polling frames never carry
the field.
"""
import asyncio
import json
import os
import sys
import types
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orchestrator.stream_manager import StreamManager
from orchestrator.workspace import fingerprint
from shared.feature_flags import flags
from shared.protocol import ToolStreamData, ToolStreamEnd

pytestmark = pytest.mark.asyncio


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


def _make_manager(dispatcher_returns_request_id: str = "req-1"):
    """StreamManager with mocked dependencies (same shape as
    test_stream_lifecycle). Returns (manager, deps)."""
    rote = Mock()
    rote.adapt = Mock(side_effect=lambda ws, components: components)
    send_to_ws = AsyncMock()
    sessions = {}

    def get_session(ws):
        return sessions.get(ws)

    mgr = StreamManager(
        rote=rote,
        send_to_ws=send_to_ws,
        get_user_session=get_session,
        agent_dispatcher=AsyncMock(return_value=dispatcher_returns_request_id),
        agent_canceller=AsyncMock(),
        validate_chat_ownership=None,
    )
    return mgr, {"send_to_ws": send_to_ws, "sessions": sessions}


async def _subscribed(mgr, deps, params=None, user_id="alice", chat_id="chat-1"):
    ws = FakeWebSocket()
    deps["sessions"][ws] = {"sub": user_id}
    stream_id, _ = await mgr.subscribe(
        ws=ws, user_id=user_id, chat_id=chat_id,
        tool_name="live_temperature", agent_id="weather",
        params=params if params is not None else {"latitude": 51.5, "longitude": -0.12},
    )
    return ws, stream_id


def _chunk(stream_id, seq, components):
    return ToolStreamData(
        request_id="req-1", stream_id=stream_id, agent_id="weather",
        tool_name="live_temperature", seq=seq, components=components,
    )


def _sent_frames(deps):
    return [json.loads(call.args[1]) for call in deps["send_to_ws"].await_args_list]


@pytest.fixture
def stream_artifacts_off():
    prior = flags._flags["stream_artifacts"]
    flags._flags["stream_artifacts"] = False
    yield
    flags._flags["stream_artifacts"] = prior


# ---------------------------------------------------------------------------
# Identity assignment at subscribe
# ---------------------------------------------------------------------------

class TestIdentityAssignment:
    async def test_subscribe_assigns_rule2_fingerprint(self):
        mgr, deps = _make_manager()
        params = {"latitude": 51.5, "longitude": -0.12}
        ws, stream_id = await _subscribed(mgr, deps, params=params)

        sub = next(iter(mgr._active.values()))
        assert stream_id.startswith("stream-")
        assert sub.component_id == fingerprint("weather", "live_temperature", params)
        assert sub.component_id.startswith("wc_")
        assert sub.bridged_component_id == sub.component_id

    async def test_identity_stable_across_param_order(self):
        mgr, deps = _make_manager()
        await _subscribed(mgr, deps, params={"longitude": -0.12, "latitude": 51.5})
        sub = next(iter(mgr._active.values()))
        assert sub.component_id == fingerprint(
            "weather", "live_temperature", {"latitude": 51.5, "longitude": -0.12})

    async def test_different_params_get_different_identity(self):
        mgr, deps = _make_manager()
        await _subscribed(mgr, deps, params={"latitude": 51.5}, chat_id="chat-1")
        await _subscribed(mgr, deps, params={"latitude": 52.0}, chat_id="chat-2")
        ids = {s.component_id for s in mgr._active.values()}
        assert len(ids) == 2

    async def test_component_id_for_active_and_dormant(self):
        mgr, deps = _make_manager()
        ws, stream_id = await _subscribed(mgr, deps)
        expected = fingerprint(
            "weather", "live_temperature", {"latitude": 51.5, "longitude": -0.12})
        assert mgr.component_id_for(stream_id) == expected

        # ws disconnect parks the subscription DORMANT — still resolvable.
        await mgr.detach(ws)
        assert mgr.component_id_for(stream_id) == expected
        assert mgr.component_id_for("stream-never-existed") is None

    async def test_flag_off_component_id_equals_stream_id(self, stream_artifacts_off):
        mgr, deps = _make_manager()
        ws, stream_id = await _subscribed(mgr, deps)
        sub = next(iter(mgr._active.values()))
        assert sub.component_id == stream_id
        assert sub.bridged_component_id is None
        assert mgr.component_id_for(stream_id) is None


# ---------------------------------------------------------------------------
# Last content-bearing chunk retention (persist-on-terminal payload for T020)
# ---------------------------------------------------------------------------

class TestRetention:
    async def test_content_chunk_retained(self):
        mgr, deps = _make_manager()
        ws, stream_id = await _subscribed(mgr, deps)
        await mgr.handle_agent_chunk(_chunk(stream_id, 1, [{"type": "metric", "value": "12C"}]))
        await asyncio.sleep(0.05)

        sub = next(iter(mgr._active.values()))
        assert sub.retained_chunk is not None
        assert sub.retained_chunk.seq == 1
        assert sub.retained_chunk.components == [{"type": "metric", "value": "12C"}]

    async def test_heartbeat_does_not_overwrite(self):
        mgr, deps = _make_manager()
        ws, stream_id = await _subscribed(mgr, deps)
        await mgr.handle_agent_chunk(_chunk(stream_id, 1, [{"type": "metric", "value": "12C"}]))
        await mgr.handle_agent_chunk(_chunk(stream_id, 2, []))  # empty delta
        await asyncio.sleep(0.05)

        sub = next(iter(mgr._active.values()))
        assert sub.retained_chunk.seq == 1

    async def test_newer_content_replaces(self):
        mgr, deps = _make_manager()
        ws, stream_id = await _subscribed(mgr, deps)
        await mgr.handle_agent_chunk(_chunk(stream_id, 1, [{"type": "metric", "value": "12C"}]))
        await asyncio.sleep(0.05)
        await mgr.handle_agent_chunk(_chunk(stream_id, 2, [{"type": "metric", "value": "13C"}]))
        await asyncio.sleep(0.05)

        sub = next(iter(mgr._active.values()))
        assert sub.retained_chunk.seq == 2
        assert sub.retained_chunk.components[0]["value"] == "13C"

    async def test_retained_survives_terminal(self):
        mgr, deps = _make_manager()
        ws, stream_id = await _subscribed(mgr, deps)
        await mgr.handle_agent_chunk(_chunk(stream_id, 1, [{"type": "metric", "value": "12C"}]))
        await asyncio.sleep(0.05)
        sub = next(iter(mgr._active.values()))

        await mgr.handle_agent_end(ToolStreamEnd(request_id="req-1", stream_id=stream_id))
        # Teardown must not clear the retention — the orchestrator's
        # persist-on-terminal wrapper reads it after handle_agent_end.
        assert sub.retained_chunk is not None
        assert sub.retained_chunk.components[0]["value"] == "12C"

    async def test_flag_off_no_retention(self, stream_artifacts_off):
        mgr, deps = _make_manager()
        ws, stream_id = await _subscribed(mgr, deps)
        await mgr.handle_agent_chunk(_chunk(stream_id, 1, [{"type": "metric", "value": "12C"}]))
        await asyncio.sleep(0.05)

        sub = next(iter(mgr._active.values()))
        assert sub.retained_chunk is None


# ---------------------------------------------------------------------------
# component_id field presence on the wire
# ---------------------------------------------------------------------------

class TestFrameFieldPresence:
    async def test_chunk_frames_carry_component_id(self):
        mgr, deps = _make_manager()
        ws, stream_id = await _subscribed(mgr, deps)
        await mgr.handle_agent_chunk(_chunk(stream_id, 1, [{"type": "metric", "value": "12C"}]))
        await asyncio.sleep(0.05)

        frames = _sent_frames(deps)
        assert frames, "no frame delivered"
        expected = fingerprint(
            "weather", "live_temperature", {"latitude": 51.5, "longitude": -0.12})
        for frame in frames:
            assert frame["type"] == "ui_stream_data"
            assert frame["component_id"] == expected

    async def test_terminal_frame_carries_component_id(self):
        mgr, deps = _make_manager()
        ws, stream_id = await _subscribed(mgr, deps)
        await mgr.handle_agent_end(ToolStreamEnd(request_id="req-1", stream_id=stream_id))

        frames = [f for f in _sent_frames(deps) if f.get("terminal") is True]
        assert len(frames) == 1
        assert frames[0]["component_id"].startswith("wc_")

    async def test_unsubscribe_ack_carries_component_id(self):
        # The unsubscribe ack goes through the single-ws builder
        # (_send_chunk_to_ws) — the other of the two frame builders.
        mgr, deps = _make_manager()
        ws, stream_id = await _subscribed(mgr, deps)
        await mgr.unsubscribe(ws, stream_id)

        frames = [f for f in _sent_frames(deps) if f.get("terminal") is True]
        assert len(frames) == 1
        assert frames[0]["component_id"].startswith("wc_")

    async def test_flag_off_frames_byte_identical(self, stream_artifacts_off):
        mgr, deps = _make_manager()
        ws, stream_id = await _subscribed(mgr, deps)
        await mgr.handle_agent_chunk(_chunk(stream_id, 1, [{"type": "metric", "value": "12C"}]))
        await asyncio.sleep(0.05)
        await mgr.unsubscribe(ws, stream_id)

        frames = _sent_frames(deps)
        assert frames
        # Pre-055 key sets, exactly: fan-out frames carry html, the
        # single-ws ack does not. No component_id anywhere.
        fanout_keys = {"type", "stream_id", "session_id", "seq",
                       "components", "html", "raw", "terminal", "error"}
        ack_keys = fanout_keys - {"html"}
        for frame in frames:
            assert set(frame.keys()) in (fanout_keys, ack_keys)


# ---------------------------------------------------------------------------
# Narrative + legacy polling streams stay identity-less
# ---------------------------------------------------------------------------

class TestNarrativeAndLegacyExclusion:
    async def test_narrative_frames_never_carry_component_id(self):
        from orchestrator.orchestrator import Orchestrator

        orch = Orchestrator.__new__(Orchestrator)
        sent = []

        async def record(ws, data):
            sent.append(json.loads(data))
            return True

        orch._safe_send = record
        rote = Mock()
        rote.get_profile = Mock(return_value=None)
        rote.adapt = Mock(side_effect=lambda ws, comps: comps)
        orch.rote = rote
        ws = FakeWebSocket()

        await orch._emit_narrative_frame(
            ws, "chat-1", "narrative-abc123def456", 1, "Hello **world**", terminal=False)
        await orch._emit_narrative_frame(
            ws, "chat-1", "narrative-abc123def456", 2, "", terminal=True)

        assert len(sent) == 2
        for frame in sent:
            assert frame["type"] == "ui_stream_data"
            assert frame["stream_id"].startswith("narrative-")
            assert "component_id" not in frame

    async def test_legacy_poll_path_never_carries_component_id(self):
        from orchestrator.orchestrator import Orchestrator

        orch = Orchestrator.__new__(Orchestrator)
        sent = []

        async def record(ws, data):
            sent.append(json.loads(data))
            return True

        orch._safe_send = record
        orch.security_flags = {}
        orch.tool_permissions = types.SimpleNamespace(
            is_tool_allowed=lambda *a, **k: True)
        orch._get_user_id = lambda ws: "alice"
        orch._streamable_tools = {"cpu_load": {
            "agent_id": "sys-1", "kind": "poll",
            "default_interval": 1, "min_interval": 1, "max_interval": 5,
        }}
        orch._MAX_STREAM_SUBSCRIPTIONS = 10
        orch._stream_tasks = {}
        orch._stream_subs = {}
        orch._execute_via_websocket = AsyncMock(return_value=types.SimpleNamespace(
            error=None, ui_components=[{"type": "metric", "value": "0.5"}],
            result={}, correlation_id=None))
        ws = FakeWebSocket()

        await orch._handle_stream_subscribe(ws, {"tool_name": "cpu_load"})
        await asyncio.sleep(0.05)
        for task in list(orch._stream_tasks.get(id(ws), {}).values()):
            task.cancel()

        types_seen = {f["type"] for f in sent}
        assert "stream_subscribed" in types_seen
        assert "stream_data" in types_seen
        for frame in sent:
            assert "component_id" not in frame
