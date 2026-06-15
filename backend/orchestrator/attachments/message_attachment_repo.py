"""SQL persistence for per-turn attachment links (table ``message_attachment``).

Feature 031-attachment-upload-parsing. Records which attachments a user
included on a sent chat turn so the orchestrator can (a) deliver structured
references to the handling agent and (b) re-hydrate them on ``load_chat``.

All reads are user-scoped; a caller only ever sees its own links.
"""

from __future__ import annotations

import time
import uuid
from typing import List, Optional


class MessageAttachmentRepository:
    """Thin data-access object over :class:`Database` for ``message_attachment``."""

    def __init__(self, db) -> None:
        self.db = db

    def insert(
        self,
        *,
        chat_id: str,
        attachment_id: str,
        user_id: str,
        message_id: Optional[str] = None,
    ) -> str:
        """Insert one turn→attachment link and return its row id."""
        row_id = str(uuid.uuid4())
        now_ms = int(time.time() * 1000)
        self.db.execute(
            """
            INSERT INTO message_attachment (
                id, chat_id, message_id, attachment_id, user_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (row_id, chat_id, message_id, attachment_id, user_id, now_ms),
        )
        return row_id

    def list_for_chat(self, chat_id: str, user_id: str) -> List[dict]:
        """All attachment links for *chat_id* owned by *user_id*, oldest first."""
        rows = self.db.fetch_all(
            """
            SELECT * FROM message_attachment
            WHERE chat_id = ? AND user_id = ?
            ORDER BY created_at ASC
            """,
            (chat_id, user_id),
        )
        return [dict(r) for r in (rows or [])]

    def list_for_message(self, message_id: str, user_id: str) -> List[dict]:
        """All attachment links for a specific persisted user message."""
        rows = self.db.fetch_all(
            """
            SELECT * FROM message_attachment
            WHERE message_id = ? AND user_id = ?
            ORDER BY created_at ASC
            """,
            (message_id, user_id),
        )
        return [dict(r) for r in (rows or [])]


__all__ = ["MessageAttachmentRepository"]
