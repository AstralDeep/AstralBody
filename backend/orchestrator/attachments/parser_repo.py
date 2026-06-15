"""SQL persistence for the global auto-parser registry (``attachment_parser``).

Feature 031-attachment-upload-parsing. One row per file-type gap, keyed by a
unique ``gap_fingerprint`` so the same unreadable type never spawns a second
draft while one is pending/live (FR-018). Carries the dedup key, lifecycle
status, the backing draft/live agent + tool, and provenance (who requested it,
which attachment/chat triggered it, which admin approved it).
"""

from __future__ import annotations

import time
import uuid
from typing import List, Optional

# Lifecycle states for a registry row.
STATUS_PENDING = "pending"
STATUS_LIVE = "live"
STATUS_FAILED = "failed"
STATUS_DISCARDED = "discarded"


class AttachmentParserRepository:
    """Data-access object over :class:`Database` for ``attachment_parser``."""

    def __init__(self, db) -> None:
        self.db = db

    def get_by_gap(self, gap_fingerprint: str) -> Optional[dict]:
        """Return the registry row for *gap_fingerprint*, or ``None``."""
        row = self.db.fetch_one(
            "SELECT * FROM attachment_parser WHERE gap_fingerprint = ?",
            (gap_fingerprint,),
        )
        return dict(row) if row else None

    def get_by_draft(self, draft_agent_id: str) -> Optional[dict]:
        """Return the registry row backed by *draft_agent_id*, or ``None``."""
        row = self.db.fetch_one(
            "SELECT * FROM attachment_parser WHERE draft_agent_id = ?",
            (draft_agent_id,),
        )
        return dict(row) if row else None

    def create_pending(
        self,
        *,
        gap_fingerprint: str,
        category: str,
        extension: Optional[str],
        draft_agent_id: Optional[str],
        source_attachment_id: Optional[str],
        source_chat_id: Optional[str],
        requested_by: Optional[str],
    ) -> dict:
        """Insert a new ``pending`` registry row and return it.

        Idempotent against the unique ``gap_fingerprint``: if a row already
        exists for this gap it is returned unchanged (the caller treats that as
        a dedup hit and does NOT create a second draft).
        """
        existing = self.get_by_gap(gap_fingerprint)
        if existing is not None:
            return existing
        row_id = str(uuid.uuid4())
        now_ms = int(time.time() * 1000)
        self.db.execute(
            """
            INSERT INTO attachment_parser (
                id, extension, category, gap_fingerprint, status,
                draft_agent_id, live_agent_id, tool_name,
                source_attachment_id, source_chat_id, requested_by, approved_by,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, NULL, ?, ?)
            """,
            (
                row_id, extension, category, gap_fingerprint, STATUS_PENDING,
                draft_agent_id, source_attachment_id, source_chat_id,
                requested_by, now_ms, now_ms,
            ),
        )
        return self.get_by_gap(gap_fingerprint)  # type: ignore[return-value]

    def mark_live(
        self,
        gap_fingerprint: str,
        *,
        live_agent_id: str,
        tool_name: str,
        approved_by: Optional[str],
    ) -> None:
        """Promote a registry row to ``live`` (global coverage)."""
        now_ms = int(time.time() * 1000)
        self.db.execute(
            """
            UPDATE attachment_parser
            SET status = ?, live_agent_id = ?, tool_name = ?, approved_by = ?, updated_at = ?
            WHERE gap_fingerprint = ?
            """,
            (STATUS_LIVE, live_agent_id, tool_name, approved_by, now_ms, gap_fingerprint),
        )

    def mark_status(self, gap_fingerprint: str, status: str) -> None:
        """Set the lifecycle *status* (``failed``/``discarded``/``pending``)."""
        now_ms = int(time.time() * 1000)
        self.db.execute(
            "UPDATE attachment_parser SET status = ?, updated_at = ? WHERE gap_fingerprint = ?",
            (status, now_ms, gap_fingerprint),
        )

    def list_by_status(self, status: str) -> List[dict]:
        """All registry rows in a given lifecycle *status*."""
        rows = self.db.fetch_all(
            "SELECT * FROM attachment_parser WHERE status = ? ORDER BY created_at DESC",
            (status,),
        )
        return [dict(r) for r in (rows or [])]


__all__ = [
    "AttachmentParserRepository",
    "STATUS_PENDING",
    "STATUS_LIVE",
    "STATUS_FAILED",
    "STATUS_DISCARDED",
]
