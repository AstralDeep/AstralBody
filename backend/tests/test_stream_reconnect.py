"""
US5 auto-retry and auth-bypass tests (001-tool-stream-ui T086).

Verifies the load-bearing security carve-out from research §12: auth
failures (`unauthenticated`, `unauthorized`) MUST bypass the RECONNECTING
state entirely and go directly to FAILED. The orchestrator MUST NEVER
auto-retry a stream whose user has had their token revoked.

Also verifies the happy path:
- Transient error → RECONNECTING with backoff
- Recovery on next chunk → ACTIVE
- 3 attempts exhausted → FAILED with retryable=True
- User leaves during reconnect → DORMANT (retry cancelled)
"""
import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orchestrator.stream_manager import (
    StreamManager,
    StreamState,
    MAX_RETRY_ATTEMPTS,
)
from shared.protocol import ToolStreamData


class FakeWS:
    pass


def _make_mgr():
    sessions = {}
    sent = []
    async def send(ws, payload):
        sent.append((ws, payload))
    dispatcher = AsyncMock()
    canceller = AsyncMock()
    rote = Mock()
    rote.adapt = Mock(side_effect=lambda ws, c: c)
    mgr = StreamManager(
        rote=rote, send_to_ws=send,
        get_user_session=lambda ws: sessions.get(ws),
        agent_dispatcher=dispatcher,
        agent_canceller=canceller,
        validate_chat_ownership=None,
    )
    return mgr, sessions, sent, dispatcher, canceller


# ---------------------------------------------------------------------------
# Auth-bypass — THE security carve-out
# ---------------------------------------------------------------------------

class TestAuthBypass:
    @pytest.mark.asyncio
    async def test_unauthenticated_skips_reconnecting_goes_to_failed(self):
        mgr, sessions, sent, dispatcher, _ = _make_mgr()
        ws = FakeWS()
        sessions[ws] = {"sub": "alice"}
        dispatcher.return_value = "req-1"
        sid, _ = await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="c1",
            tool_name="t", agent_id="a", params={},
        )
        # Bring it to ACTIVE
        await mgr.handle_agent_chunk(ToolStreamData(
            request_id="req-1", stream_id=sid, agent_id="a", tool_name="t",
            seq=1, components=[{"type": "metric", "id": sid}],
        ))
        await asyncio.sleep(0.05)
        sub = next(iter(mgr._active.values()))
        assert sub.state == StreamState.ACTIVE

        # Now agent emits an unauthenticated error
        await mgr.handle_agent_chunk(ToolStreamData(
            request_id="req-1", stream_id=sid, agent_id="a", tool_name="t",
            seq=2, components=[],
            error={"code": "unauthenticated", "message": "token revoked"},
        ))
        await asyncio.sleep(0.05)

        # Subscription should be GONE (transitioned to FAILED → torn down)
        assert sid not in [s.stream_id for s in mgr._active.values()]
        # Dispatcher was NOT called a second time (no retry)
        assert dispatcher.await_count == 1
        # The user got a failed chunk with the right error code
        msgs = [json.loads(p) for w, p in sent]
        failed = [m for m in msgs if (m.get("error") or {}).get("phase") == "failed"]
        assert len(failed) >= 1
        assert failed[-1]["error"]["code"] == "unauthenticated"
        assert failed[-1]["error"]["retryable"] is False
        # NO reconnecting chunks were sent
        reconnecting = [m for m in msgs if (m.get("error") or {}).get("phase") == "reconnecting"]
        assert reconnecting == []

    @pytest.mark.asyncio
    async def test_unauthorized_also_bypasses(self):
        mgr, sessions, sent, dispatcher, _ = _make_mgr()
        ws = FakeWS()
        sessions[ws] = {"sub": "alice"}
        dispatcher.return_value = "req-1"
        sid, _ = await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="c1",
            tool_name="t", agent_id="a", params={},
        )
        await mgr.handle_agent_chunk(ToolStreamData(
            request_id="req-1", stream_id=sid, agent_id="a", tool_name="t",
            seq=1, components=[],
            error={"code": "unauthorized", "message": "scope revoked"},
        ))
        await asyncio.sleep(0.05)
        # Gone, no retry
        assert sid not in [s.stream_id for s in mgr._active.values()]
        assert dispatcher.await_count == 1


# ---------------------------------------------------------------------------
# Transient error → RECONNECTING happy path
# ---------------------------------------------------------------------------

class TestReconnectHappyPath:
    @pytest.mark.asyncio
    async def test_transient_error_enters_reconnecting(self):
        mgr, sessions, sent, dispatcher, _ = _make_mgr()
        ws = FakeWS()
        sessions[ws] = {"sub": "alice"}
        dispatcher.return_value = "req-1"
        sid, _ = await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="c1",
            tool_name="t", agent_id="a", params={},
        )
        # First chunk → ACTIVE
        await mgr.handle_agent_chunk(ToolStreamData(
            request_id="req-1", stream_id=sid, agent_id="a", tool_name="t",
            seq=1, components=[{"type": "metric", "id": sid}],
        ))
        await asyncio.sleep(0.05)

        # Patch compute_backoff to return 0.05s for fast tests
        with patch("orchestrator.stream_manager.compute_backoff", return_value=0.05):
            # Transient error
            dispatcher.return_value = "req-2"  # next dispatch returns new id
            await mgr.handle_agent_chunk(ToolStreamData(
                request_id="req-1", stream_id=sid, agent_id="a", tool_name="t",
                seq=2, components=[],
                error={"code": "upstream_unavailable", "message": "blip"},
            ))
            # Should be in RECONNECTING state
            sub = next(iter(mgr._active.values()))
            assert sub.state == StreamState.RECONNECTING
            assert sub.retry_attempt == 1
            # Reconnecting chunk was sent
            msgs = [json.loads(p) for w, p in sent]
            recons = [m for m in msgs if (m.get("error") or {}).get("phase") == "reconnecting"]
            assert len(recons) >= 1
            assert recons[-1]["error"]["attempt"] == 1
            # Wait for the retry timer
            await asyncio.sleep(0.2)
            # Dispatcher should have been called again (retry)
            assert dispatcher.await_count == 2

    @pytest.mark.asyncio
    async def test_recovery_after_retry_resets_state(self):
        mgr, sessions, sent, dispatcher, _ = _make_mgr()
        ws = FakeWS()
        sessions[ws] = {"sub": "alice"}
        dispatcher.return_value = "req-1"
        sid, _ = await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="c1",
            tool_name="t", agent_id="a", params={},
        )
        # → ACTIVE
        await mgr.handle_agent_chunk(ToolStreamData(
            request_id="req-1", stream_id=sid, agent_id="a", tool_name="t",
            seq=1, components=[{"type": "metric", "id": sid}],
        ))
        await asyncio.sleep(0.05)

        with patch("orchestrator.stream_manager.compute_backoff", return_value=0.01):
            dispatcher.return_value = "req-2"
            # Transient error
            await mgr.handle_agent_chunk(ToolStreamData(
                request_id="req-1", stream_id=sid, agent_id="a", tool_name="t",
                seq=2, components=[],
                error={"code": "upstream_unavailable", "message": "blip"},
            ))
            await asyncio.sleep(0.1)  # let retry timer fire
            # Now agent emits a successful chunk on the new request_id
            await mgr.handle_agent_chunk(ToolStreamData(
                request_id="req-2", stream_id=sid, agent_id="a", tool_name="t",
                seq=3, components=[{"type": "metric", "id": sid, "value": "back"}],
            ))
            await asyncio.sleep(0.05)
            sub = next(iter(mgr._active.values()))
            # Recovered: state ACTIVE, retry_attempt 0
            assert sub.state == StreamState.ACTIVE
            assert sub.retry_attempt == 0
            assert sub.last_error_code is None

    @pytest.mark.asyncio
    async def test_three_attempts_exhausted_goes_failed_retryable(self):
        mgr, sessions, sent, dispatcher, _ = _make_mgr()
        ws = FakeWS()
        sessions[ws] = {"sub": "alice"}
        dispatcher.return_value = "req-1"
        sid, _ = await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="c1",
            tool_name="t", agent_id="a", params={},
        )
        await mgr.handle_agent_chunk(ToolStreamData(
            request_id="req-1", stream_id=sid, agent_id="a", tool_name="t",
            seq=1, components=[{"type": "metric", "id": sid}],
        ))
        await asyncio.sleep(0.05)

        with patch("orchestrator.stream_manager.compute_backoff", return_value=0.01):
            # Three transient errors in a row, each spaced enough for the
            # retry timer to fire
            for i in range(MAX_RETRY_ATTEMPTS):
                # Locate the current request_id from the live subscription
                if sid not in [s.stream_id for s in mgr._active.values()]:
                    break
                cur_sub = next(s for s in mgr._active.values() if s.stream_id == sid)
                cur_req = cur_sub.request_id
                dispatcher.return_value = f"req-{i+2}"  # next dispatch new id
                await mgr.handle_agent_chunk(ToolStreamData(
                    request_id=cur_req, stream_id=sid, agent_id="a", tool_name="t",
                    seq=i + 2, components=[],
                    error={"code": "upstream_unavailable", "message": "down"},
                ))
                await asyncio.sleep(0.05)

            # After 3 retry attempts each emitting an error, the next error
            # should fail. We have to emit one more error to trip the
            # exhaustion check (the test loop above hit the cap).
            if sid in [s.stream_id for s in mgr._active.values()]:
                cur_sub = next(s for s in mgr._active.values() if s.stream_id == sid)
                cur_req = cur_sub.request_id
                await mgr.handle_agent_chunk(ToolStreamData(
                    request_id=cur_req, stream_id=sid, agent_id="a", tool_name="t",
                    seq=99, components=[],
                    error={"code": "upstream_unavailable", "message": "still down"},
                ))
                await asyncio.sleep(0.05)

            # Subscription is gone (FAILED → torn down)
            assert sid not in [s.stream_id for s in mgr._active.values()]
            # The user got a failed chunk with retryable=True
            msgs = [json.loads(p) for w, p in sent]
            failed = [m for m in msgs if (m.get("error") or {}).get("phase") == "failed"]
            assert len(failed) >= 1
            assert failed[-1]["error"]["retryable"] is True

    @pytest.mark.asyncio
    async def test_user_leaves_during_reconnect_goes_dormant(self):
        mgr, sessions, sent, dispatcher, _ = _make_mgr()
        ws = FakeWS()
        sessions[ws] = {"sub": "alice"}
        dispatcher.return_value = "req-1"
        sid, _ = await mgr.subscribe(
            ws=ws, user_id="alice", chat_id="c1",
            tool_name="t", agent_id="a", params={},
        )
        await mgr.handle_agent_chunk(ToolStreamData(
            request_id="req-1", stream_id=sid, agent_id="a", tool_name="t",
            seq=1, components=[{"type": "metric", "id": sid}],
        ))
        await asyncio.sleep(0.05)

        # Long backoff so we can leave during it
        with patch("orchestrator.stream_manager.compute_backoff", return_value=10.0):
            await mgr.handle_agent_chunk(ToolStreamData(
                request_id="req-1", stream_id=sid, agent_id="a", tool_name="t",
                seq=2, components=[],
                error={"code": "upstream_unavailable", "message": "blip"},
            ))
            sub = next(iter(mgr._active.values()))
            assert sub.state == StreamState.RECONNECTING
            # User leaves
            await mgr.detach(ws)
            # Should be DORMANT, with retry cancelled
            assert ("alice", "c1") in mgr._dormant
            dormant_sub = mgr._dormant[("alice", "c1")][next(iter(mgr._dormant[("alice", "c1")]))]
            assert dormant_sub.state == StreamState.DORMANT
            assert dormant_sub._retry_handle is None
            assert dormant_sub.retry_attempt == 0
