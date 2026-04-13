"""Attachments package: storage, persistence, and content-type sniffing for
chat-message file uploads (feature 002-file-uploads)."""

from orchestrator.attachments.models import (
    Attachment,
    AttachmentRef,
    AttachmentCategory,
)

__all__ = ["Attachment", "AttachmentRef", "AttachmentCategory"]
