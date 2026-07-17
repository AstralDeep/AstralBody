"""In-memory staging for one atomically published scheduled chat turn.

Scheduled LLM execution may take seconds, so it must not hold a PostgreSQL
transaction open while the model runs.  This module captures only the chat
history mutations produced by that turn.  The scheduler store later publishes
the frozen batch together with its effect-ledger transition in one short,
fenced transaction.
"""

from __future__ import annotations

import contextvars
import copy
import json
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator


class ScheduledPublicationEscapeError(RuntimeError):
    """A scheduled turn attempted a history write outside its owned target."""


@dataclass(frozen=True)
class StagedHistoryMessage:
    """One normalized message insert awaiting atomic publication."""

    role: str
    content: str
    title_source: str
    timestamp_ms: int


@dataclass(frozen=True)
class ScheduledHistoryBatch:
    """Immutable history mutations produced by one scheduled handler run."""

    chat_id: str
    user_id: str
    create_chat_if_missing: bool
    agent_id: str | None
    requested_title: str | None
    messages: tuple[StagedHistoryMessage, ...]
    conversation_commit_id: str | None = None
    request_generation: str | None = None
    base_render_revision: int | None = None
    committed_render_revision: int | None = None
    canvas_layouts: tuple[dict[str, Any], ...] = ()


class ScheduledHistoryStage:
    """Mutable task-local stage that becomes immutable when execution exits."""

    def __init__(
        self,
        *,
        history: Any,
        chat_id: str,
        user_id: str,
        create_chat_if_missing: bool,
        agent_id: str | None,
    ) -> None:
        if not chat_id or not user_id:
            raise ValueError("scheduled history target requires chat_id and user_id")
        self._history = history
        self.chat_id = chat_id
        self.user_id = user_id
        self.create_chat_if_missing = bool(create_chat_if_missing)
        self.agent_id = agent_id
        self.requested_title: str | None = None
        self._messages: list[StagedHistoryMessage] = []
        self._sealed = False

    def matches(self, history: Any, chat_id: str, user_id: str) -> bool:
        """Return whether a read belongs to this exact staged target."""

        return (
            history is self._history
            and str(chat_id) == self.chat_id
            and str(user_id) == self.user_id
        )

    def _assert_write_target(
        self, history: Any, chat_id: str, user_id: str
    ) -> None:
        if self._sealed:
            raise ScheduledPublicationEscapeError(
                "scheduled history stage is already sealed"
            )
        if not self.matches(history, chat_id, user_id):
            raise ScheduledPublicationEscapeError(
                "scheduled history write escaped its owned chat"
            )

    def add_message(
        self,
        history: Any,
        *,
        chat_id: str,
        user_id: str,
        role: str,
        content: Any,
    ) -> None:
        """Normalize and stage one message without touching PostgreSQL."""

        self._assert_write_target(history, chat_id, user_id)
        content_string = content if isinstance(content, str) else json.dumps(content)
        title_source = str(content)
        timestamp_ms = int(time.time() * 1000)
        if self._messages:
            timestamp_ms = max(timestamp_ms, self._messages[-1].timestamp_ms + 1)
        self._messages.append(
            StagedHistoryMessage(
                role=str(role),
                content=content_string,
                title_source=title_source,
                timestamp_ms=timestamp_ms,
            )
        )

    def update_title(
        self,
        history: Any,
        *,
        chat_id: str,
        user_id: str,
        title: str,
    ) -> None:
        """Stage an explicit title update for the atomic publication."""

        self._assert_write_target(history, chat_id, user_id)
        self.requested_title = str(title)

    @property
    def messages(self) -> tuple[StagedHistoryMessage, ...]:
        """Return the current read-only task-local message projection."""

        return tuple(self._messages)

    def seal(self) -> None:
        """Reject any late writes inherited by fire-and-forget tasks."""

        self._sealed = True

    def batch(
        self,
        *,
        conversation_commit_id: str | None = None,
        request_generation: str | None = None,
        base_render_revision: int | None = None,
        committed_render_revision: int | None = None,
        canvas_layouts: list[dict[str, Any]] | None = None,
    ) -> ScheduledHistoryBatch:
        """Return the immutable publication input after handler exit."""

        if not self._sealed:
            raise RuntimeError("scheduled history stage must be sealed first")
        return ScheduledHistoryBatch(
            chat_id=self.chat_id,
            user_id=self.user_id,
            create_chat_if_missing=self.create_chat_if_missing,
            agent_id=self.agent_id,
            requested_title=self.requested_title,
            messages=tuple(self._messages),
            conversation_commit_id=conversation_commit_id,
            request_generation=request_generation,
            base_render_revision=base_render_revision,
            committed_render_revision=committed_render_revision,
            canvas_layouts=tuple(copy.deepcopy(canvas_layouts or [])),
        )


_ACTIVE_STAGE: contextvars.ContextVar[ScheduledHistoryStage | None] = (
    contextvars.ContextVar("scheduled_history_stage", default=None)
)


def current_scheduled_history_stage() -> ScheduledHistoryStage | None:
    """Return the task-local scheduled history stage, when present."""

    return _ACTIVE_STAGE.get()


@contextmanager
def stage_scheduled_history(
    *,
    history: Any,
    chat_id: str,
    user_id: str,
    create_chat_if_missing: bool,
    agent_id: str | None,
) -> Iterator[ScheduledHistoryStage]:
    """Activate one exclusive scheduled history stage for handler execution."""

    if _ACTIVE_STAGE.get() is not None:
        raise RuntimeError("nested scheduled history stages are not supported")
    stage = ScheduledHistoryStage(
        history=history,
        chat_id=chat_id,
        user_id=user_id,
        create_chat_if_missing=create_chat_if_missing,
        agent_id=agent_id,
    )
    token = _ACTIVE_STAGE.set(stage)
    try:
        yield stage
    finally:
        stage.seal()
        _ACTIVE_STAGE.reset(token)
