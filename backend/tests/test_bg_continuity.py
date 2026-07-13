"""055 — cross-device background-task continuity (FF_BG_CONTINUITY).

A long-running job started on ONE device surfaces on every other connected
device, pushed as it happens: task_started/task_completed fan to all the
user's sockets (completion works with the originator gone), a background
(VirtualWebSocket) turn's chat-rail narrative + terminal chat_status mirror
to real sockets on the chat, register_ui with a session_id resumes the chat
context and replays task state, completed-but-unnotified tasks replay once,
and the scheduled fallback chat is created before the turn so its output is
not silently dropped. Flag off restores originator-only frames
byte-identically. Requires the docker-compose Postgres; skipped where
unreachable.
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from shared.feature_flags import flags  # noqa: E402

pytestmark = pytest.mark.asyncio


@pytest.fixture
def bg_flag():
    prior = flags._flags.get("bg_continuity")
    flags._flags["bg_continuity"] = True
    yield
    flags._flags["bg_continuity"] = prior


@pytest.fixture
def orch(bg_flag, monkeypatch):
    monkeypatch.setenv("USE_MOCK_AUTH", "true")
    from orchestrator.orchestrator import Orchestrator
    try:
        o = Orchestrator()
    except Exception as exc:
        pytest.skip(f"orchestrator/database unavailable: {exc}")
    return o


def _capture_socket(orch, user_id):
    """A registered capture socket (the established VirtualWebSocket test
    stand-in; its own empty task identity never re-fans)."""
    from orchestrator.async_tasks import BackgroundTask, VirtualWebSocket
    task = BackgroundTask(task_id=uuid.uuid4().hex, chat_id="", user_id="")
    ws = VirtualWebSocket(task)
    orch.ui_sessions[ws] = {"sub": user_id, "preferred_username": user_id}
    orch.ui_clients.append(ws)
    orch.rote.register_device(ws, {})
    return ws


def _frames(ws, ftype):
    return [f for f in ws.task.outputs if f.get("type") == ftype]


async def _await_manager_tasks(orch):
    tasks = [t.asyncio_task for t in orch.async_task_manager._tasks.values()
             if t.asyncio_task]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    # Let the fire-and-forget bookkeeping writes land.
    await asyncio.sleep(0.2)


async def _cleanup(orch, user_id, chat_ids=()):
    await orch.history.db.aexecute(
        "DELETE FROM background_task WHERE user_id = ?", (user_id,))
    for cid in chat_ids:
        try:
            await asyncio.to_thread(orch.history.delete_chat, cid, user_id=user_id)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Items 1+2 — task frames fan to all the user's sockets
# ---------------------------------------------------------------------------

async def test_task_started_fans_to_second_socket(orch):
    user_id = f"bgc-{uuid.uuid4().hex[:8]}"
    ws1, ws2 = _capture_socket(orch, user_id), _capture_socket(orch, user_id)
    chat_id = await asyncio.to_thread(orch.history.create_chat, user_id=user_id)

    async def fake_handle(websocket, message, chat_id, *args, **kwargs):
        pass

    orch.handle_chat_message = fake_handle
    message = "analyze the quarterly report thoroughly"
    await orch._dispatch_async_chat(ws1, message, chat_id, user_id=user_id)

    for ws in (ws1, ws2):
        started = _frames(ws, "task_started")
        assert len(started) == 1, f"task_started missing on {ws}"
        assert started[0]["payload"]["chat_id"] == chat_id
        assert started[0]["payload"]["title"] == message[:60]
    # processing_async stays originator-only (other devices key off
    # task_started; a bare chat_status has no chat_id to scope it).
    assert _frames(ws1, "chat_status")
    assert not _frames(ws2, "chat_status")

    await _await_manager_tasks(orch)
    await _cleanup(orch, user_id, [chat_id])


async def test_completion_fan_reaches_socket_joined_after_start(orch):
    user_id = f"bgc-{uuid.uuid4().hex[:8]}"
    ws1 = _capture_socket(orch, user_id)
    chat_id = await asyncio.to_thread(orch.history.create_chat, user_id=user_id)
    hold = asyncio.Event()

    async def fake_handle(websocket, message, chat_id, *args, **kwargs):
        await hold.wait()
        # The narrative the turn would have produced (drives the summary).
        await websocket.send_text(json.dumps({
            "type": "ui_render", "target": "chat",
            "components": [{"type": "text", "content": "Report finished."}],
        }))

    orch.handle_chat_message = fake_handle
    await orch._dispatch_async_chat(ws1, "run the report", chat_id, user_id=user_id)

    # The originator disconnects; a NEW device connects after start.
    del orch.ui_sessions[ws1]
    orch.ui_clients.remove(ws1)
    ws3 = _capture_socket(orch, user_id)

    hold.set()
    await _await_manager_tasks(orch)

    completed = _frames(ws3, "task_completed")
    assert len(completed) == 1, "completion must reach a late-joined socket"
    payload = completed[0]["payload"]
    assert payload["chat_id"] == chat_id
    assert payload["status"] == "completed"
    assert payload["summary"] == "Report finished."

    row = await orch.history.db.afetch_one(
        "SELECT status, summary, notified FROM background_task WHERE task_id = ?",
        (payload["task_id"],))
    assert row is not None
    assert row["status"] == "completed"
    assert row["summary"] == "Report finished."
    assert row["notified"] is True

    await _cleanup(orch, user_id, [chat_id])


# ---------------------------------------------------------------------------
# Item 3 — VirtualWebSocket turns fan narrative + terminal status
# ---------------------------------------------------------------------------

async def test_vws_narrative_and_done_reach_chat_socket(orch):
    from orchestrator.async_tasks import BackgroundTask, VirtualWebSocket
    user_id = f"bgc-{uuid.uuid4().hex[:8]}"
    ws2 = _capture_socket(orch, user_id)
    chat_id = await asyncio.to_thread(orch.history.create_chat, user_id=user_id)
    orch._ws_active_chat[id(ws2)] = chat_id
    vws = VirtualWebSocket(BackgroundTask(
        task_id="bgturn01", chat_id=chat_id, user_id=user_id))

    await orch.send_ui_render(
        vws, [{"type": "text", "content": "All done, here is the answer."}],
        target="chat")
    chat_renders = [f for f in _frames(ws2, "ui_render") if f.get("target") == "chat"]
    assert len(chat_renders) == 1, "chat narrative must mirror to the real socket"
    assert chat_renders[0]["components"][0]["content"] == "All done, here is the answer."

    # Canvas renders do NOT fan here (the workspace upsert path owns those).
    await orch.send_ui_render(
        vws, [{"type": "metric", "title": "M", "value": 1}], target="canvas")
    assert [f for f in _frames(ws2, "ui_render") if f.get("target") != "chat"] == []

    await orch._send_chat_status(vws, "done")
    done = [f for f in _frames(ws2, "chat_status") if f.get("status") == "done"]
    assert len(done) == 1, "terminal chat_status must mirror to the real socket"
    # The vws itself still captured its own copy (originator delivery intact).
    assert [f for f in vws.task.outputs
            if f.get("type") == "chat_status" and f.get("status") == "done"]

    await _cleanup(orch, user_id, [chat_id])


# ---------------------------------------------------------------------------
# Item 4 — register_ui session resume (+ item 5 in-flight replay)
# ---------------------------------------------------------------------------

async def test_register_ui_session_resume_replays_in_flight_task(orch):
    user_id = "test_user"  # mock-auth dev-token subject
    await _cleanup(orch, user_id)
    chat_id = await asyncio.to_thread(orch.history.create_chat, user_id=user_id)
    hold = asyncio.Event()

    async def slow(vws, **kw):
        await hold.wait()

    bg = await orch.async_task_manager.submit(
        chat_id, user_id, slow, title="slow analysis")

    ws = _capture_socket(orch, user_id)
    orch._registered_events[id(ws)] = asyncio.Event()
    await orch.handle_ui_message(ws, json.dumps({
        "type": "register_ui", "token": "dev-token", "device": {},
        "session_id": chat_id}))

    assert orch._ws_active_chat.get(id(ws)) == chat_id, \
        "session_id must resume the chat context"
    statuses = [f for f in _frames(ws, "chat_status")
                if f.get("status") == "processing_async"]
    assert statuses, "joining device must see the running state"
    replays = [f for f in _frames(ws, "task_started")
               if f["payload"].get("task_id") == bg.task_id]
    assert replays and replays[0]["payload"]["replay"] is True
    assert replays[0]["payload"]["title"] == "slow analysis"

    # Foreign/invalid session_id: ignored silently, registration succeeds.
    other_user = f"someone-else-{uuid.uuid4().hex[:6]}"
    other_chat = await asyncio.to_thread(
        orch.history.create_chat, user_id=other_user)
    ws2 = _capture_socket(orch, user_id)
    orch._registered_events[id(ws2)] = asyncio.Event()
    await orch.handle_ui_message(ws2, json.dumps({
        "type": "register_ui", "token": "dev-token", "device": {},
        "session_id": other_chat}))
    assert orch._ws_active_chat.get(id(ws2)) is None
    assert _frames(ws2, "rote_config"), "register must still succeed"

    hold.set()
    await _await_manager_tasks(orch)
    await _cleanup(orch, user_id, [chat_id])
    await _cleanup(orch, other_user, [other_chat])


# ---------------------------------------------------------------------------
# Item 5 — completed-but-unnotified replay marks notified
# ---------------------------------------------------------------------------

async def test_completed_unnotified_replay_marks_notified(orch):
    user_id = "test_user"
    await _cleanup(orch, user_id)
    task_id = uuid.uuid4().hex[:8]
    await orch.history.db.aexecute(
        "INSERT INTO background_task (task_id, user_id, chat_id, kind, status, "
        "title, summary, completed_at, notified) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, now(), FALSE)",
        (task_id, user_id, "chat-x", "async_chat", "completed",
         "old job", "Finished while you were away."))

    ws = _capture_socket(orch, user_id)
    orch._registered_events[id(ws)] = asyncio.Event()
    await orch.handle_ui_message(ws, json.dumps({
        "type": "register_ui", "token": "dev-token", "device": {}}))

    replays = [f for f in _frames(ws, "task_completed")
               if f["payload"].get("task_id") == task_id]
    assert len(replays) == 1
    assert replays[0]["payload"]["summary"] == "Finished while you were away."
    assert replays[0]["payload"]["replay"] is True

    row = await orch.history.db.afetch_one(
        "SELECT notified FROM background_task WHERE task_id = ?", (task_id,))
    assert row["notified"] is True

    # A second registration replays nothing (notified sticks).
    ws2 = _capture_socket(orch, user_id)
    orch._registered_events[id(ws2)] = asyncio.Event()
    await orch.handle_ui_message(ws2, json.dumps({
        "type": "register_ui", "token": "dev-token", "device": {}}))
    assert [f for f in _frames(ws2, "task_completed")
            if f["payload"].get("task_id") == task_id] == []

    await _cleanup(orch, user_id)


# ---------------------------------------------------------------------------
# Kill switch — flag off restores originator-only frames byte-identically
# ---------------------------------------------------------------------------

async def test_flag_off_all_new_sends_absent(orch):
    from orchestrator.async_tasks import BackgroundTask, VirtualWebSocket
    flags._flags["bg_continuity"] = False  # bg_flag fixture restores it
    user_id = f"bgc-{uuid.uuid4().hex[:8]}"
    ws1, ws2 = _capture_socket(orch, user_id), _capture_socket(orch, user_id)
    chat_id = await asyncio.to_thread(orch.history.create_chat, user_id=user_id)
    orch._ws_active_chat[id(ws2)] = chat_id

    async def fake_handle(websocket, message, chat_id, *args, **kwargs):
        pass

    orch.handle_chat_message = fake_handle
    await orch._dispatch_async_chat(ws1, "legacy behavior", chat_id, user_id=user_id)
    await _await_manager_tasks(orch)

    # Originator frames: pre-055 shapes exactly (no title, no summary).
    started = _frames(ws1, "task_started")
    assert len(started) == 1
    assert list(started[0]["payload"].keys()) == ["task_id", "chat_id", "status"]
    completed = _frames(ws1, "task_completed")
    assert len(completed) == 1, "watcher notification must still arrive (item 1 fix)"
    assert list(completed[0]["payload"].keys()) == [
        "task_id", "chat_id", "status", "completed_at"]

    # The second socket sees nothing at all.
    assert ws2.task.outputs == []

    # No durable record with the flag off.
    row = await orch.history.db.afetch_one(
        "SELECT 1 FROM background_task WHERE task_id = ?",
        (started[0]["payload"]["task_id"],))
    assert row is None

    # VirtualWebSocket turn frames stay captured-only.
    vws = VirtualWebSocket(BackgroundTask(
        task_id="bgoff01", chat_id=chat_id, user_id=user_id))
    await orch.send_ui_render(vws, [{"type": "text", "content": "hi"}], target="chat")
    await orch._send_chat_status(vws, "done")
    assert ws2.task.outputs == []
    assert [f for f in vws.task.outputs
            if f.get("type") == "chat_status" and f.get("status") == "done"] == \
        [{"type": "chat_status", "status": "done", "message": ""}]

    # register_ui ignores session_id with the flag off.
    ws3 = _capture_socket(orch, "test_user")
    orch._registered_events[id(ws3)] = asyncio.Event()
    await orch.handle_ui_message(ws3, json.dumps({
        "type": "register_ui", "token": "dev-token", "device": {},
        "session_id": chat_id}))
    assert orch._ws_active_chat.get(id(ws3)) is None

    await _cleanup(orch, user_id, [chat_id])


# ---------------------------------------------------------------------------
# Item 6 — scheduled fallback chat exists before the turn runs
# ---------------------------------------------------------------------------

async def test_scheduled_fallback_chat_created(orch, monkeypatch):
    user_id = f"bgc-sched-{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(orch._llm_store, "get_system",
                        AsyncMock(return_value=object()))

    async def fake_handle(websocket, message, chat_id, **kwargs):
        pass

    monkeypatch.setattr(orch, "handle_chat_message", fake_handle)
    await orch.run_scheduled_turn(
        user_id=user_id, chat_id=None, instruction="daily digest",
        agent_id=None, access_token="tok", allowed_scopes=[],
        correlation_id="bgc-corr-1")

    fallback = f"scheduled-{user_id}"
    row = await orch.history.db.afetch_one(
        "SELECT id FROM chats WHERE id = ? AND user_id = ?", (fallback, user_id))
    assert row is not None, "fallback chat must exist so history writes persist"

    # Flag off: pre-055 behavior (no chat created).
    flags._flags["bg_continuity"] = False
    off_user = f"bgc-sched-{uuid.uuid4().hex[:8]}"
    await orch.run_scheduled_turn(
        user_id=off_user, chat_id=None, instruction="daily digest",
        agent_id=None, access_token="tok", allowed_scopes=[],
        correlation_id="bgc-corr-2")
    assert await orch.history.db.afetch_one(
        "SELECT id FROM chats WHERE id = ? AND user_id = ?",
        (f"scheduled-{off_user}", off_user)) is None

    await _cleanup(orch, user_id, [fallback])
