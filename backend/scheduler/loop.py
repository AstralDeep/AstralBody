"""The single in-process asyncio scheduler loop (feature 025, US5/T047).

On startup it reconciles interrupted runs (FR-025), then wakes every
``SCHEDULER_TICK_SECONDS`` to dispatch jobs whose ``next_run_at`` has passed,
running each through the ``JobRunner`` under the existing background-task
concurrency cap. Single-orchestrator design (spec assumption); not distributed.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from agentic_settings import SCHEDULER_TICK_SECONDS

logger = logging.getLogger("scheduler.loop")


class SchedulerLoop:
    def __init__(self, store, runner, task_manager) -> None:
        self.store = store
        self.runner = runner
        self.task_manager = task_manager
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._dispatched: set = set()  # run-ids in flight this process

    def start(self) -> None:
        if self._task is not None:
            return
        # Restart recovery: any run left 'running' is now interrupted (FR-025).
        try:
            n = self.store.reconcile_interrupted()
            if n:
                logger.info("scheduler reconciled %s interrupted run(s) on startup", n)
        except Exception:  # pragma: no cover
            logger.warning("scheduler reconcile failed (non-fatal)", exc_info=True)
        self._stop.clear()
        self._task = asyncio.create_task(self._run())
        logger.info("scheduler loop started (tick=%ss)", SCHEDULER_TICK_SECONDS)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:  # pragma: no cover - loop must never die
                logger.exception("scheduler tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=SCHEDULER_TICK_SECONDS)
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        now_ms = int(time.time() * 1000)
        due = self.store.list_due(now_ms)
        for job in due:
            # Fairness/concurrency: hand each due job to the existing background
            # task manager (which enforces MAX_CONCURRENT_TASKS) rather than
            # blocking the tick. Jobs across users interleave naturally.
            try:
                await self.task_manager.submit(
                    job.get("target_chat_id") or f"job:{job['id']}",
                    job["user_id"],
                    self._job_coro,
                    job,
                )
            except Exception:  # pragma: no cover
                logger.exception("failed to dispatch job %s", job.get("id"))

    async def _job_coro(self, virtual_ws, job):
        """Coroutine handed to BackgroundTaskManager.submit (signature: (vws, *args))."""
        return await self.runner.run_job(job)
