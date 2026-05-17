"""020-async-queries: Tests for background task infrastructure."""

import asyncio
import json
import pytest

from orchestrator.async_tasks import (
    BackgroundTaskManager,
    BackgroundTask,
    VirtualWebSocket,
    TaskStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _collect(mgr):
    """Wait for all known tasks in the manager to finish."""
    tasks = [t.asyncio_task for t in mgr._tasks.values() if t.asyncio_task]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


# ---------------------------------------------------------------------------
# VirtualWebSocket Tests
# ---------------------------------------------------------------------------

class TestVirtualWebSocket:
    def test_send_text_json(self):
        task = BackgroundTask(task_id="t1", chat_id="c1", user_id="u1")
        vws = VirtualWebSocket(task)
        asyncio.run(vws.send_text('{"type": "test", "data": "hello"}'))
        assert task.outputs == [{"type": "test", "data": "hello"}]

    def test_send_text_raw(self):
        task = BackgroundTask(task_id="t1", chat_id="c1", user_id="u1")
        vws = VirtualWebSocket(task)
        asyncio.run(vws.send_text("plain text"))
        assert task.outputs == [{"type": "raw", "data": "plain text"}]

    def test_send_json_dict(self):
        task = BackgroundTask(task_id="t1", chat_id="c1", user_id="u1")
        vws = VirtualWebSocket(task)
        asyncio.run(vws.send_json({"type": "direct", "val": 42}))
        assert task.outputs == [{"type": "direct", "val": 42}]

    def test_no_capture_after_close(self):
        task = BackgroundTask(task_id="t1", chat_id="c1", user_id="u1")
        vws = VirtualWebSocket(task)
        asyncio.run(vws.close())
        asyncio.run(vws.send_json({"type": "after_close"}))
        assert task.outputs == []


# ---------------------------------------------------------------------------
# BackgroundTaskManager Tests
# ---------------------------------------------------------------------------

class TestBackgroundTaskManager:

    @pytest.mark.asyncio
    async def test_submit_creates_task(self):
        mgr = BackgroundTaskManager()
        async def dummy(vws, **kw):
            vws.task.outputs.append({"type": "done"})
        t = await mgr.submit("c1", "u1", dummy)
        await _collect(mgr)
        assert t.chat_id == "c1"
        assert t.user_id == "u1"
        assert t.status == TaskStatus.COMPLETED
        assert t.task_id is not None

    @pytest.mark.asyncio
    async def test_task_runs_to_completion(self):
        mgr = BackgroundTaskManager()
        async def dummy(vws, **kw):
            pass
        t = await mgr.submit("c1", "u1", dummy)
        await _collect(mgr)
        assert t.status == TaskStatus.COMPLETED
        assert t.completed_at is not None

    @pytest.mark.asyncio
    async def test_task_handles_exception(self):
        mgr = BackgroundTaskManager()
        async def failing(vws, **kw):
            raise ValueError("test-explosion")
        t = await mgr.submit("c1", "u1", failing)
        await _collect(mgr)
        assert t.status == TaskStatus.FAILED
        assert "test-explosion" in t.errors[0]

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        mgr = BackgroundTaskManager()
        started = asyncio.Event()
        async def slow(vws, **kw):
            started.set()
            await asyncio.sleep(600)
        t = await mgr.submit("c1", "u1", slow)
        await started.wait()
        cancelled = await mgr.cancel(t.task_id)
        assert cancelled is True
        await asyncio.sleep(0.1)
        assert t.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_list_for_user(self):
        mgr = BackgroundTaskManager()
        async def dummy(vws, **kw):
            pass
        t1 = await mgr.submit("c1", "u1", dummy)
        t2 = await mgr.submit("c2", "u1", dummy)
        t3 = await mgr.submit("c3", "u2", dummy)
        await _collect(mgr)
        u1_tasks = await mgr.list_for_user("u1")
        assert len(u1_tasks) == 2
        ids = {t.task_id for t in u1_tasks}
        assert t1.task_id in ids
        assert t2.task_id in ids

    @pytest.mark.asyncio
    async def test_get_active_for_chat(self):
        mgr = BackgroundTaskManager()
        started = asyncio.Event()
        async def slow(vws, **kw):
            started.set()
            await asyncio.sleep(600)
        t1 = await mgr.submit("c1", "u1", slow)
        await started.wait()
        active = await mgr.get_active_for_chat("c1")
        assert active is not None
        assert active.task_id == t1.task_id

    @pytest.mark.asyncio
    async def test_watchers_notified(self):
        mgr = BackgroundTaskManager()
        notifications = []

        class FakeWS:
            async def send_json(self, data):
                notifications.append(json.loads(data))

        async def dummy(vws, **kw):
            pass
        t = await mgr.submit("c1", "u1", dummy)
        t.watchers.append(FakeWS())
        await _collect(mgr)
        assert len(notifications) == 1
        assert notifications[0]["type"] == "task_completed"
        assert notifications[0]["payload"]["task_id"] == t.task_id

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self):
        """Cancelling a non-existent task returns False."""
        mgr = BackgroundTaskManager()
        result = await mgr.cancel("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        """Getting a non-existent task returns None."""
        mgr = BackgroundTaskManager()
        result = await mgr.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_active_for_idle_chat(self):
        """get_active_for_chat on a chat with no tasks returns None."""
        mgr = BackgroundTaskManager()
        result = await mgr.get_active_for_chat("idle-chat")
        assert result is None

    def test_background_task_to_dict(self):
        """BackgroundTask.to_dict produces expected shape."""
        from datetime import datetime, timezone
        t = BackgroundTask(task_id="t99", chat_id="c99", user_id="u99")
        d = t.to_dict()
        assert d["task_id"] == "t99"
        assert d["chat_id"] == "c99"
        assert d["user_id"] == "u99"
        assert d["status"] == "queued"
        assert d["completed_at"] is None
