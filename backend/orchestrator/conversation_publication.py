"""Task-local authority for one staged conversation-canvas publication.

The durable rows for a not-yet-committed canvas live in ``saved_components``
under their conversation commit identity.  This module supplies only the
task-local selector for those rows; it does not publish them or own the
database transaction.  :class:`contextvars.ContextVar` is intentional:
``asyncio.to_thread`` copies the caller's context, so existing synchronous
workspace methods keep seeing the correct stage when invoked by their async
facades without introducing process-global mutable state.
"""

from __future__ import annotations

import copy
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any


def _uuid4_text(value: Any, field_name: str) -> str:
    """Return one canonical UUID4 string or reject an unsafe stage identity."""
    try:
        parsed = uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a UUID4") from exc
    if parsed.version != 4 or parsed.variant != uuid.RFC_4122:
        raise ValueError(f"{field_name} must be a UUID4")
    return str(parsed)


@dataclass(slots=True)
class ConversationPublicationStage:
    """Complete staged canvas selected for the current logical turn.

    ``layouts`` is an in-memory deep copy of the current authoritative
    layouts. Component rows are durable and commit-versioned in PostgreSQL;
    layouts remain private to this object until the owning repository writes
    both surfaces at its fenced atomic publication boundary.
    """

    history: Any
    commit_id: str
    chat_id: str
    user_id: str
    base_render_revision: int
    next_render_revision: int
    operation_fence: Any = None
    layouts: list[dict[str, Any]] = field(default_factory=list)
    dirty: bool = False
    snapshot_cause: str | None = None
    sealed: bool = False
    committed: bool = False

    def __post_init__(self) -> None:
        if self.history is None:
            raise ValueError("history is required")
        self.commit_id = _uuid4_text(self.commit_id, "commit_id")
        self.chat_id = _uuid4_text(self.chat_id, "chat_id")
        if not isinstance(self.user_id, str) or not self.user_id.strip():
            raise ValueError("user_id is required")
        self.user_id = self.user_id.strip()
        if (
            isinstance(self.base_render_revision, bool)
            or not isinstance(self.base_render_revision, int)
            or self.base_render_revision < 0
        ):
            raise ValueError("base_render_revision must be a non-negative integer")
        if (
            isinstance(self.next_render_revision, bool)
            or not isinstance(self.next_render_revision, int)
            or self.next_render_revision != self.base_render_revision + 1
        ):
            raise ValueError("next_render_revision must equal base_render_revision + 1")
        if not isinstance(self.layouts, list) or any(
            not isinstance(layout, dict) for layout in self.layouts
        ):
            raise ValueError("layouts must be an array of layout objects")
        self.layouts = copy.deepcopy(self.layouts)
        if self.committed and not self.sealed:
            raise ValueError("a committed stage must be sealed")

    def matches(self, history: Any, chat_id: str, user_id: str) -> bool:
        """Return whether this stage owns the exact workspace access."""
        return (
            self.history is history
            and str(chat_id) == self.chat_id
            and str(user_id) == self.user_id
        )

    def ensure_mutable(self) -> None:
        """Reject a late staged mutation after publication finalization."""
        if self.sealed:
            raise RuntimeError("conversation publication stage is sealed")

    def mark_dirty(self) -> None:
        """Record that this stage now differs from its authoritative base."""

        self.ensure_mutable()
        self.dirty = True

    def seal(self, *, committed: bool) -> None:
        """Finalize this task-local stage with an immutable outcome.

        Repeating the same outcome is idempotent. Reclassifying a rolled-back
        stage as committed (or vice versa) is rejected so late cleanup cannot
        rewrite the publication result observed by callers.
        """
        committed = bool(committed)
        if self.sealed:
            if self.committed != committed:
                raise ValueError("sealed stage committed outcome cannot change")
            return
        self.committed = committed
        self.sealed = True


_CURRENT_CONVERSATION_PUBLICATION: ContextVar[
    ConversationPublicationStage | None
] = ContextVar("astraldeep_conversation_publication", default=None)


def current_conversation_publication() -> ConversationPublicationStage | None:
    """Return the publication stage active in this task context, if any."""
    return _CURRENT_CONVERSATION_PUBLICATION.get()


def activate_conversation_publication(
    stage: ConversationPublicationStage,
) -> Token[ConversationPublicationStage | None]:
    """Activate ``stage`` and return the exact token required for reset."""
    if not isinstance(stage, ConversationPublicationStage):
        raise TypeError("stage must be a ConversationPublicationStage")
    stage.ensure_mutable()
    return _CURRENT_CONVERSATION_PUBLICATION.set(stage)


def reset_conversation_publication(
    token: Token[ConversationPublicationStage | None],
) -> None:
    """Restore the task context captured before activation."""
    _CURRENT_CONVERSATION_PUBLICATION.reset(token)
