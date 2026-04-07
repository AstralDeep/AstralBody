"""
Task State Machine — Formal state tracking for multi-step Re-Act operations.

Provides inspect, resume, and recovery capabilities for tasks that may be
interrupted by WebSocket disconnects or other failures.

Inspired by Claude Code's task states (pending/running/completed/failed/killed).
"""
import time
import uuid
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger("Orchestrator.TaskState")


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_TOOL = "awaiting_tool"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """Represents a single Re-Act loop execution."""
    task_id: str
    chat_id: str
    user_id: str
    state: TaskState = TaskState.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    turn_count: int = 0
    max_turns: int = 10
    tool_calls_made: List[str] = field(default_factory=list)
    current_tool: Optional[str] = None
    error: Optional[str] = None
    message: str = ""

    def transition(self, new_state: TaskState, **kwargs):
        """Transition to a new state with optional metadata updates."""
        old_state = self.state
        self.state = new_state
        self.updated_at = time.time()
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        logger.debug(f"Task {self.task_id}: {old_state.value} → {new_state.value}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "chat_id": self.chat_id,
            "user_id": self.user_id,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "turn_count": self.turn_count,
            "max_turns": self.max_turns,
            "tool_calls_made": self.tool_calls_made,
            "current_tool": self.current_tool,
            "error": self.error,
            "message": self.message,
            "elapsed_seconds": round(time.time() - self.created_at, 1),
        }


class TaskManager:
    """In-memory task registry for tracking active Re-Act operations."""

    def __init__(self):
        self._tasks: Dict[str, Task] = {}
        self._chat_tasks: Dict[str, str] = {}  # chat_id -> active task_id

    def create_task(self, chat_id: str, user_id: str, message: str = "") -> Task:
        """Create a new task for a chat session."""
        # Cancel any existing task for this chat
        existing_id = self._chat_tasks.get(chat_id)
        if existing_id and existing_id in self._tasks:
            existing = self._tasks[existing_id]
            if existing.state in (TaskState.PENDING, TaskState.RUNNING, TaskState.AWAITING_TOOL):
                existing.transition(TaskState.CANCELLED)

        task_id = f"task_{uuid.uuid4().hex[:8]}"
        task = Task(
            task_id=task_id,
            chat_id=chat_id,
            user_id=user_id,
            message=message,
        )
        self._tasks[task_id] = task
        self._chat_tasks[chat_id] = task_id
        logger.info(f"Created task {task_id} for chat {chat_id}")
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def get_active_task(self, chat_id: str) -> Optional[Task]:
        """Get the currently active task for a chat session."""
        task_id = self._chat_tasks.get(chat_id)
        if task_id:
            task = self._tasks.get(task_id)
            if task and task.state in (TaskState.PENDING, TaskState.RUNNING, TaskState.AWAITING_TOOL):
                return task
        return None

    def get_chat_tasks(self, chat_id: str) -> List[Task]:
        """Get all tasks (active and completed) for a chat session."""
        return [t for t in self._tasks.values() if t.chat_id == chat_id]

    def cleanup_old_tasks(self, max_age_seconds: float = 3600):
        """Remove completed/failed/cancelled tasks older than max_age_seconds."""
        cutoff = time.time() - max_age_seconds
        to_remove = [
            tid for tid, task in self._tasks.items()
            if task.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED)
            and task.updated_at < cutoff
        ]
        for tid in to_remove:
            task = self._tasks.pop(tid, None)
            if task:
                self._chat_tasks.pop(task.chat_id, None)
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old tasks")
