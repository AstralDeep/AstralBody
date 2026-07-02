"""Feature 044 (FR-003) — desktop transport: backoff, bounded queue, resume.

Pure logic tests: no real socket. The reconnect loop's decision points are
factored (`backoff_delay_s`, `_should_reconnect`, `_flush_pending`, `_send`
offline path) so they are testable without networking.
"""
import asyncio
import json

import pytest

pytest.importorskip("PySide6")

from astral_client.protocol import (  # noqa: E402
    BACKOFF_MAX_S,
    MAX_QUEUE,
    OrchestratorClient,
    backoff_delay_s,
)


def _client(qapp):
    return OrchestratorClient("ws://127.0.0.1:9/ws", "tok")


def test_backoff_doubles_and_caps():
    assert backoff_delay_s(1) == 1.0
    assert backoff_delay_s(2) == 2.0
    assert backoff_delay_s(3) == 4.0
    assert backoff_delay_s(6) == 30.0  # 32 capped
    assert backoff_delay_s(50) == BACKOFF_MAX_S


def test_should_reconnect_states(qapp):
    c = _client(qapp)
    assert c._should_reconnect() is True
    c._auth_hold = True
    assert c._should_reconnect() is False  # app owns refresh + rebuild
    c._auth_hold = False
    c._stop = True
    assert c._should_reconnect() is False


def test_offline_sends_queue_fifo(qapp):
    c = _client(qapp)
    c.send_event("get_history", {})
    c.send_chat("hello", chat_id="c1")
    assert len(c._pending) == 2
    first = json.loads(c._pending[0])
    assert first["action"] == "get_history"


def test_queue_overflow_drops_oldest_and_signals(qapp):
    c = _client(qapp)
    drops: list[str] = []
    c.status.connect(lambda s: drops.append(s) if s.startswith("send_dropped:") else None)
    for i in range(MAX_QUEUE + 3):
        c.send_event("chat_message", {"message": f"m{i}"})
    assert len(c._pending) == MAX_QUEUE
    assert len(drops) == 3  # overflow surfaced, never a silent vanish
    # oldest were dropped: the queue starts at m3
    assert json.loads(c._pending[0])["payload"]["message"] == "m3"


def test_flush_pending_sends_fifo_then_empties(qapp):
    c = _client(qapp)
    c.send_event("a", {})
    c.send_event("b", {})

    sent: list[str] = []

    class FakeWs:
        async def send(self, frame):
            sent.append(frame)

    asyncio.run(c._flush_pending(FakeWs()))
    assert [json.loads(f)["action"] for f in sent] == ["a", "b"]
    assert not c._pending


def test_auth_required_holds_reconnect(qapp):
    c = _client(qapp)
    # simulate the inbound handling contract: transport flags the hold
    c._auth_hold = True
    assert c._should_reconnect() is False
