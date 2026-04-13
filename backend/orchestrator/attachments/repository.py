"""SQL persistence for attachments (table ``user_attachments``).

Wraps the existing :class:`backend.shared.database.Database` helper. All
methods enforce user ownership; non-owner reads return ``None`` rather than
the row, so callers get a uniform "not found" surface (per
contracts/upload-api.md).
"""

from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from orchestrator.attachments.models import Attachment


def _to_attachment(row: dict) -> Attachment:
    """Convert a DB row (RealDictRow) to an :class:`Attachment`."""
    created_at = row["created_at"]
    if isinstance(created_at, (int, float)):
        created_at_dt = datetime.fromtimestamp(created_at / 1000.0, tz=timezone.utc)
    else:
        created_at_dt = created_at
    deleted_at = row.get("deleted_at")
    deleted_at_dt = None
    if deleted_at is not None:
        if isinstance(deleted_at, (int, float)):
            deleted_at_dt = datetime.fromtimestamp(deleted_at / 1000.0, tz=timezone.utc)
        else:
            deleted_at_dt = deleted_at
    return Attachment(
        attachment_id=row["attachment_id"],
        user_id=row["user_id"],
        filename=row["filename"],
        content_type=row["content_type"],
        category=row["category"],
        extension=row["extension"],
        size_bytes=row["size_bytes"],
        sha256=row["sha256"],
        storage_path=row["storage_path"],
        created_at=created_at_dt,
        deleted_at=deleted_at_dt,
    )


def _encode_cursor(created_at_ms: int, attachment_id: str) -> str:
    payload = json.dumps(
        {"created_at": created_at_ms, "attachment_id": attachment_id},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> Optional[Tuple[int, str]]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + padding).encode()).decode()
        data = json.loads(raw)
        return int(data["created_at"]), str(data["attachment_id"])
    except Exception:
        return None


class AttachmentRepository:
    """Thin data-access object over :class:`Database`."""

    def __init__(self, db) -> None:
        self.db = db

    def insert(
        self,
        *,
        attachment_id: str,
        user_id: str,
        filename: str,
        content_type: str,
        category: str,
        extension: str,
        size_bytes: int,
        sha256: str,
        storage_path: str,
    ) -> Attachment:
        """Insert a new attachment row and return the materialised model."""
        now_ms = int(time.time() * 1000)
        self.db.execute(
            """
            INSERT INTO user_attachments (
                attachment_id, user_id, filename, content_type, category,
                extension, size_bytes, sha256, storage_path, created_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                attachment_id, user_id, filename, content_type, category,
                extension, size_bytes, sha256, storage_path, now_ms,
            ),
        )
        row = self.db.fetch_one(
            "SELECT * FROM user_attachments WHERE attachment_id = ?",
            (attachment_id,),
        )
        return _to_attachment(dict(row))

    def get_by_id(self, attachment_id: str, user_id: str) -> Optional[Attachment]:
        """Return the live attachment for *user_id*, or ``None`` if missing/foreign/deleted."""
        row = self.db.fetch_one(
            """
            SELECT * FROM user_attachments
            WHERE attachment_id = ? AND user_id = ? AND deleted_at IS NULL
            """,
            (attachment_id, user_id),
        )
        return _to_attachment(dict(row)) if row else None

    def list_for_user(
        self,
        user_id: str,
        *,
        category: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Tuple[List[Attachment], Optional[str]]:
        """Cursor-paginated listing of a user's live attachments, newest first."""
        limit = max(1, min(int(limit), 200))
        params: list = [user_id]
        sql = (
            "SELECT * FROM user_attachments "
            "WHERE user_id = ? AND deleted_at IS NULL"
        )
        if category:
            sql += " AND category = ?"
            params.append(category)
        decoded = _decode_cursor(cursor) if cursor else None
        if decoded:
            cursor_created_at, cursor_id = decoded
            sql += " AND (created_at < ? OR (created_at = ? AND attachment_id < ?))"
            params.extend([cursor_created_at, cursor_created_at, cursor_id])
        sql += " ORDER BY created_at DESC, attachment_id DESC LIMIT ?"
        params.append(limit + 1)

        rows = self.db.fetch_all(sql, tuple(params)) or []
        items = [_to_attachment(dict(r)) for r in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = _encode_cursor(int(last["created_at"]), str(last["attachment_id"]))
        return items, next_cursor

    def soft_delete(self, attachment_id: str, user_id: str) -> bool:
        """Mark an attachment deleted. Returns True if a row was updated."""
        now_ms = int(time.time() * 1000)
        cursor = self.db.execute(
            """
            UPDATE user_attachments
            SET deleted_at = ?
            WHERE attachment_id = ? AND user_id = ? AND deleted_at IS NULL
            """,
            (now_ms, attachment_id, user_id),
        )
        return getattr(cursor, "rowcount", 0) > 0

    def soft_delete_all_for_user(self, user_id: str) -> int:
        """Soft-delete every live attachment for *user_id* (account-deletion path)."""
        now_ms = int(time.time() * 1000)
        cursor = self.db.execute(
            """
            UPDATE user_attachments
            SET deleted_at = ?
            WHERE user_id = ? AND deleted_at IS NULL
            """,
            (now_ms, user_id),
        )
        return getattr(cursor, "rowcount", 0)


__all__ = ["AttachmentRepository"]
