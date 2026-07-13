"""
020-async-queries: Background task infrastructure for asynchronous chat processing.

Provides:
- VirtualWebSocket: captures outputs from background agent runs
- BackgroundTaskManager: submits, tracks, and notifies on async tasks
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from shared.feature_flags import flags

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BackgroundTask:
    """Tracks a single async query execution."""
    task_id: str
    chat_id: str
    user_id: str
    status: TaskStatus = TaskStatus.QUEUED
    # 055 bg-continuity: what kind of work this is and a short user-facing
    # label (derived from the originating message) for cross-device frames.
    kind: str = "async_chat"
    title: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    asyncio_task: Optional[asyncio.Task] = None
    # Captured outputs from the VirtualWebSocket
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    # Subscribers waiting for completion (WS ids or callback coros)
    watchers: List[Any] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "chat_id": self.chat_id,
            "user_id": self.user_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class VirtualWebSocket:
    """Captures output messages that would normally be sent via WebSocket.

    Used during background task execution to collect all UI messages
    (component renders, status updates, etc.) into a buffer that gets
    persisted as chat history when the task completes.
    """

    def __init__(self, task: BackgroundTask):
        self.task = task
        self._closed = False

    async def send_text(self, data: str):
        """Receive string data, parse as JSON if possible."""
        if self._closed:
            return
        try:
            parsed = json.loads(data)
            self.task.outputs.append(parsed)
        except json.JSONDecodeError:
            self.task.outputs.append({"type": "raw", "data": data})

    async def send_json(self, data: Any, mode: str = "text"):
        """Receive dict data directly (used by _safe_send)."""
        if self._closed:
            return
        if isinstance(data, dict):
            self.task.outputs.append(data)
        elif isinstance(data, str):
            await self.send_text(data)

    async def receive_text(self) -> str:
        """Simulate receiving — returns empty (background tasks don't receive)."""
        return ""

    async def receive_json(self, mode: str = "text"):
        """Simulate receiving — returns empty."""
        return {}

    async def close(self, code: int = 1000):
        self._closed = True

    @property
    def client(self):
        """Pretend to have a client attribute for audit logging."""
        return ("background", self.task.task_id)

    def __repr__(self):
        return f"VirtualWebSocket(task={self.task.task_id})"


class BackgroundTaskManager:
    """Manages async background tasks with a maximum concurrent limit."""

    MAX_CONCURRENT_TASKS = 5

    def __init__(self):
        self._tasks: Dict[str, BackgroundTask] = {}
        self._lock = asyncio.Lock()
        # 055 bg-continuity: optional durable write-through + completion fan,
        # bound by the orchestrator once its DB handle exists. Unbound, the
        # manager stays memory-only with watcher-only notification as before.
        self._db = None
        self._on_complete = None

    def bind(self, *, db=None, on_complete=None):
        """Wire the durable task store and the orchestrator's completion fan
        (055 bg-continuity). Both optional; existing behavior when unbound."""
        if db is not None:
            self._db = db
        if on_complete is not None:
            self._on_complete = on_complete

    def _record(self, query: str, params):
        """Fire-and-forget durable bookkeeping (055 bg-continuity). Fail-open
        by design — task execution never blocks on (or fails with) it."""
        if self._db is None or not flags.is_enabled("bg_continuity"):
            return

        async def _write():
            try:
                await self._db.aexecute(query, params)
            except Exception:
                logger.debug("background_task bookkeeping failed", exc_info=True)

        asyncio.create_task(_write())

    async def submit(
        self,
        chat_id: str,
        user_id: str,
        coro_factory,
        *args,
        kind: str = "async_chat",
        title: str = "",
        **kwargs,
    ) -> BackgroundTask:
        """Create a background task and start executing it.

        Args:
            chat_id: The chat session ID
            user_id: The authenticated user ID
            coro_factory: Async callable that takes (virtual_ws, *args, **kwargs)
            kind: Task kind for the durable record (055 bg-continuity)
            title: Short user-facing label for cross-device task frames
        """
        async with self._lock:
            # Capacity check
            running = sum(1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING)
            if running >= self.MAX_CONCURRENT_TASKS:
                # Queue it
                pass  # We still accept and run; asyncio handles scheduling

            task_id = str(uuid.uuid4())[:8]
            bg_task = BackgroundTask(
                task_id=task_id,
                chat_id=chat_id,
                user_id=user_id,
                status=TaskStatus.QUEUED,
                kind=kind,
                title=title,
            )
            self._tasks[task_id] = bg_task

        self._record(
            "INSERT INTO background_task (task_id, user_id, chat_id, kind, status, title) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (task_id) DO NOTHING",
            (task_id, user_id, chat_id, kind, bg_task.status.value, title),
        )

        vws = VirtualWebSocket(bg_task)
        atask = asyncio.create_task(self._run_task(bg_task, vws, coro_factory, *args, **kwargs))
        bg_task.asyncio_task = atask

        return bg_task

    async def _run_task(self, bg_task: BackgroundTask, vws: VirtualWebSocket, coro_factory, *args, **kwargs):
        """Execute the task, capture results, and notify watchers."""
        try:
            bg_task.status = TaskStatus.RUNNING
            logger.info("Background task %s started (chat=%s user=%s)", bg_task.task_id, bg_task.chat_id, bg_task.user_id)
            await coro_factory(vws, *args, **kwargs)
            bg_task.status = TaskStatus.COMPLETED
            logger.info("Background task %s completed with %d outputs", bg_task.task_id, len(bg_task.outputs))
        except asyncio.CancelledError:
            bg_task.status = TaskStatus.CANCELLED
            logger.info("Background task %s cancelled", bg_task.task_id)
        except Exception as e:
            bg_task.status = TaskStatus.FAILED
            bg_task.errors.append(str(e))
            logger.error("Background task %s failed: %s", bg_task.task_id, e, exc_info=True)
        finally:
            bg_task.completed_at = datetime.now(timezone.utc)
            await self._notify_watchers(bg_task)

    async def _notify_watchers(self, bg_task: BackgroundTask):
        """Notify all watchers of task completion."""
        notification = {
            "type": "task_completed",
            "payload": {
                "task_id": bg_task.task_id,
                "chat_id": bg_task.chat_id,
                "status": bg_task.status.value,
                "completed_at": bg_task.completed_at.isoformat() if bg_task.completed_at else None,
            },
        }
        summary = self._summary_from_outputs(bg_task)
        # 055 bg-continuity: the orchestrator fan reaches EVERY socket of the
        # user — the originator may be long gone. Watchers still get the frame
        # (clients de-dupe by task_id), covering the fan-failure case too.
        fanned = 0
        if self._on_complete is not None and flags.is_enabled("bg_continuity"):
            notification["payload"]["summary"] = summary
            try:
                fanned = int(await self._on_complete(bg_task, notification) or 0)
            except Exception:
                logger.debug("completion fan failed for task %s", bg_task.task_id, exc_info=True)
        # Watchers are WS objects that we can send to. send_text — FastAPI's
        # send_json would re-encode the already-dumped string and clients
        # would receive (and drop) a JSON string literal.
        for ws in bg_task.watchers:
            try:
                await ws.send_text(json.dumps(notification))
            except Exception:
                logger.debug("Failed to notify watcher for task %s", bg_task.task_id, exc_info=True)
        bg_task.watchers.clear()
        self._record(
            "INSERT INTO background_task (task_id, user_id, chat_id, kind, status, title, summary, completed_at, notified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (task_id) DO UPDATE SET "
            "status = EXCLUDED.status, summary = EXCLUDED.summary, "
            "completed_at = EXCLUDED.completed_at, notified = EXCLUDED.notified",
            (bg_task.task_id, bg_task.user_id, bg_task.chat_id, bg_task.kind,
             bg_task.status.value, bg_task.title, summary, bg_task.completed_at,
             fanned > 0),
        )

    @staticmethod
    def _summary_from_outputs(bg_task: BackgroundTask) -> str:
        """One-line completion summary: the last narrative/status text the
        turn captured (mirrors ``run_scheduled_turn``), else the last error."""
        summary = ""
        for out in bg_task.outputs:
            if not isinstance(out, dict):
                continue
            if out.get("type") == "ui_render" and out.get("target") == "chat":
                for comp in out.get("components") or []:
                    content = comp.get("content") if isinstance(comp, dict) else None
                    if isinstance(content, str) and content.strip():
                        summary = content.strip()
                        break
                continue
            txt = out.get("text") or out.get("message")
            if not txt and isinstance(out.get("payload"), dict):
                txt = out["payload"].get("text") or out["payload"].get("message")
            if isinstance(txt, str) and txt.strip():
                summary = txt.strip()
        if not summary and bg_task.errors:
            summary = str(bg_task.errors[-1])
        return " ".join(summary.split())[:200]

    async def cancel(self, task_id: str) -> bool:
        """Cancel a running background task."""
        async with self._lock:
            bg_task = self._tasks.get(task_id)
            if bg_task and bg_task.asyncio_task and not bg_task.asyncio_task.done():
                bg_task.asyncio_task.cancel()
                return True
        return False

    async def get(self, task_id: str) -> Optional[BackgroundTask]:
        return self._tasks.get(task_id)

    async def list_for_user(self, user_id: str, limit: int = 20) -> List[BackgroundTask]:
        """Return recent tasks for a user, newest first."""
        user_tasks = [t for t in self._tasks.values() if t.user_id == user_id]
        user_tasks.sort(key=lambda t: t.created_at, reverse=True)
        return user_tasks[:limit]

    async def get_active_for_chat(self, chat_id: str) -> Optional[BackgroundTask]:
        """Return the currently active task for a chat, if any."""
        for t in self._tasks.values():
            if t.chat_id == chat_id and t.status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
                return t
        return None
