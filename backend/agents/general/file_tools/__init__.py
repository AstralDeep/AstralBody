"""File-handling tools for the AstralBody general agent.

Each public reader function (``read_document``, ``read_spreadsheet``,
``read_presentation``, ``read_text``, ``read_image``, ``list_attachments``)
is registered in :data:`backend.agents.general.mcp_tools.TOOL_REGISTRY`.

All readers route through :func:`resolve_attachment` which:

  * Verifies the calling user owns the attachment (FR-009).
  * Re-sniffs content type via libmagic (FR-008).
  * Returns ``(Attachment, blob_path)`` or a structured error dict.

The orchestrator injects ``user_id`` into tool-call ``arguments`` before
dispatch (see ``orchestrator.py:2325``), so each reader receives it as a
kwarg. Calls without a ``user_id`` are refused.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from orchestrator.attachments import content_type as ct
from orchestrator.attachments import store
from orchestrator.attachments.repository import AttachmentRepository
from orchestrator.attachments.models import Attachment

logger = logging.getLogger("FileTools")


def _error(code: str, message: str) -> Dict[str, Any]:
    return {"error": {"code": code, "message": message}}


_NotFound = object()


def _get_database():
    """Resolve the shared Database instance.

    Production: lifted off the orchestrator singleton. Tests inject a stub
    via :func:`set_database_for_testing` below.
    """
    if _DB_OVERRIDE is not None:
        return _DB_OVERRIDE
    try:
        # Late import to avoid circular references at module load.
        from orchestrator.orchestrator import Orchestrator  # noqa: F401
    except Exception:
        pass
    # The orchestrator stores its singleton on app.state in production. For
    # in-process tool calls we accept a lazily-resolved global.
    global _RESOLVED_DB
    if _RESOLVED_DB is not None:
        return _RESOLVED_DB
    raise RuntimeError(
        "file_tools: no Database wired. Call set_database_for_testing() "
        "or ensure the orchestrator has registered itself."
    )


_DB_OVERRIDE = None
_RESOLVED_DB = None


def set_database_for_testing(db) -> None:
    """Test-only hook to inject a database stub."""
    global _DB_OVERRIDE
    _DB_OVERRIDE = db


def register_database(db) -> None:
    """Production hook called by the orchestrator at startup."""
    global _RESOLVED_DB
    _RESOLVED_DB = db


def resolve_attachment(
    attachment_id: str,
    user_id: Optional[str],
) -> Tuple[Optional[Attachment], Optional[Path], Optional[Dict[str, Any]]]:
    """Resolve an attachment_id to ``(Attachment, blob_path, error)``.

    Returns ``(attachment, path, None)`` on success, or
    ``(None, None, error_dict)`` on any failure (foreign owner, deleted,
    missing on disk, content-type mismatch).
    """
    if not user_id:
        return None, None, _error(
            "not_found",
            "Tool was called without a user context; refusing to read.",
        )
    if not attachment_id:
        return None, None, _error("not_found", "attachment_id is required.")

    try:
        repo = AttachmentRepository(_get_database())
    except RuntimeError as exc:
        return None, None, _error("not_found", str(exc))

    att = repo.get_by_id(attachment_id, user_id)
    if att is None:
        return None, None, _error("not_found", f"Attachment {attachment_id} not found.")

    upload_root = store.get_upload_root()
    blob_path = upload_root / att.storage_path
    if not blob_path.exists():
        return None, None, _error(
            "not_found",
            f"Attachment {attachment_id} has no on-disk blob.",
        )

    sniffed = ct.sniff_content_type(blob_path)
    if sniffed and not ct.is_consistent(att.extension, sniffed):
        return None, None, _error(
            "unreadable_file",
            f"File contents (sniffed: {sniffed}) do not match extension '.{att.extension}'.",
        )

    return att, blob_path, None


__all__ = [
    "resolve_attachment",
    "register_database",
    "set_database_for_testing",
]
