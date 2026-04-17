"""Account-deletion hook for attachments.

Called by the user-management subsystem when an account is removed (per
contracts/upload-api.md "Account deletion" section). Soft-deletes every
attachment row owned by *user_id* and recursively removes the user's blob
directory under ``ATTACHMENT_UPLOAD_ROOT``.
"""

from __future__ import annotations

import logging

from orchestrator.attachments import store
from orchestrator.attachments.repository import AttachmentRepository

logger = logging.getLogger("AttachmentsLifecycle")


def purge_user_attachments(db, user_id: str) -> int:
    """Soft-delete all of *user_id*'s attachments and remove their blobs.

    Args:
        db: A :class:`backend.shared.database.Database` (or compatible) instance.
        user_id: The Keycloak ``sub`` of the deleted account.

    Returns:
        Number of attachment rows that were soft-deleted.
    """
    repo = AttachmentRepository(db)
    deleted = repo.soft_delete_all_for_user(user_id)
    try:
        store.delete_user(user_id)
    except Exception as exc:  # pragma: no cover - log and swallow
        logger.warning(f"Blob purge failed for user {user_id}: {exc}")
    return deleted


__all__ = ["purge_user_attachments"]
