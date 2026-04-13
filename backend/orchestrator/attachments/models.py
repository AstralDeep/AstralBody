"""Pydantic models for the Attachment domain.

See ``specs/002-file-uploads/data-model.md`` for the authoritative shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

AttachmentCategory = Literal["document", "spreadsheet", "presentation", "text", "image"]


class Attachment(BaseModel):
    """A user-owned uploaded file."""

    attachment_id: str = Field(..., description="UUIDv4")
    user_id: str = Field(..., description="Keycloak sub of the owning user")
    filename: str
    content_type: str
    category: AttachmentCategory
    extension: str
    size_bytes: int
    sha256: str
    storage_path: str = Field(..., description="Path relative to the upload root")
    created_at: datetime
    deleted_at: Optional[datetime] = None


class AttachmentRef(BaseModel):
    """Lightweight pointer embedded in a chat message.

    Kept intentionally tiny so message rendering does not require joining
    the attachment table, and so historical chats stay readable even if the
    underlying Attachment is later deleted.
    """

    attachment_id: str
    filename: str
    category: AttachmentCategory


class AttachmentList(BaseModel):
    """Cursor-paginated listing response."""

    attachments: List[Attachment]
    next_cursor: Optional[str] = None


__all__ = ["Attachment", "AttachmentRef", "AttachmentList", "AttachmentCategory"]
