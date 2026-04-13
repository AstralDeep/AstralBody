"""FastAPI router for the Attachment REST surface (feature 002-file-uploads).

Implements the contract from ``specs/002-file-uploads/contracts/upload-api.md``:

* ``POST   /api/upload``                  (replaces the legacy implementation in auth.py)
* ``GET    /api/attachments``             (list current user's live attachments)
* ``GET    /api/attachments/{id}``        (one attachment's metadata)
* ``DELETE /api/attachments/{id}``        (soft-delete)

All endpoints are gated by the existing ``require_user_id`` dependency. Non-owner
reads return ``404`` (we do not confirm or deny the existence of foreign rows).
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response

from orchestrator.attachments import content_type as ct
from orchestrator.attachments import store
from orchestrator.attachments.repository import AttachmentRepository
from orchestrator.auth import require_user_id

logger = logging.getLogger("AttachmentsAPI")

# 30 MiB hard cap (FR-003). Mirrored on the client.
MAX_UPLOAD_BYTES = 30 * 1024 * 1024

# Stream upload in modest chunks so we can short-circuit oversize files without
# buffering them in memory.
_CHUNK_SIZE = 1024 * 256  # 256 KiB

attachments_router = APIRouter(tags=["Files"])


def _get_repository(request: Request) -> AttachmentRepository:
    """Resolve the AttachmentRepository from the orchestrator on app state."""
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        root_app = getattr(request.app, "_root_app", None) or request.app
        orch = getattr(root_app.state, "orchestrator", None)
    if orch is None or not getattr(orch, "history", None):
        raise HTTPException(status_code=500, detail="Database not initialised")
    return AttachmentRepository(orch.history.db)


def _attachment_to_response(att) -> dict:
    return {
        "attachment_id": att.attachment_id,
        "filename": att.filename,
        "category": att.category,
        "extension": att.extension,
        "content_type": att.content_type,
        "size_bytes": att.size_bytes,
        "sha256": att.sha256,
        "created_at": att.created_at.isoformat() if att.created_at else None,
    }


# ---------------------------------------------------------------------------
# POST /api/upload
# ---------------------------------------------------------------------------


@attachments_router.post(
    "/api/upload",
    summary="Upload a file",
    description=(
        "Upload a single file (≤ 30 MB). Returns the new attachment's metadata. "
        "Files are user-scoped and visible across the user's chats."
    ),
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    user_id: str = Depends(require_user_id),
):
    raw_filename = file.filename or ""
    safe_filename = os.path.basename(raw_filename)
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    extension = ct.normalise_extension(safe_filename)
    category = ct.category_for_extension(extension)
    if category is None or extension in ct.LEGACY_BINARY_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file extension '.{extension or '?'}'. "
                "Supported: documents (pdf, docx, rtf, odt), spreadsheets "
                "(xlsx, xls, ods, tsv, csv), presentations (pptx, odp), "
                "text/code, and images."
            ),
        )

    attachment_id = str(uuid.uuid4())

    async def _stream_chunks():
        while True:
            chunk = await file.read(_CHUNK_SIZE)
            if not chunk:
                break
            yield chunk

    # We need a sync iterable for store.write; bridge via a small pre-read loop.
    chunks: list[bytes] = []
    total = 0
    async for chunk in _stream_chunks():
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"{safe_filename} exceeds the 30 MB upload limit "
                    f"({MAX_UPLOAD_BYTES} bytes)."
                ),
            )
        chunks.append(chunk)

    try:
        path, size_bytes, sha256 = store.write(
            user_id=user_id,
            attachment_id=attachment_id,
            filename=safe_filename,
            chunks=iter(chunks),
            max_bytes=MAX_UPLOAD_BYTES,
        )
    except ValueError as exc:
        # Should be unreachable because the loop above already enforces the cap,
        # but treat defensively.
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        )

    sniffed = ct.sniff_content_type(path)
    if not ct.is_consistent(extension, sniffed):
        # Roll back the on-disk blob so we never persist a row for an
        # extension/content-type mismatch.
        store.delete(user_id, attachment_id)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"{safe_filename} has extension '.{extension}' but its content "
                f"appears to be '{sniffed}'. Please upload a file whose contents "
                "match its extension."
            ),
        )

    rel_storage = str(path.relative_to(store.get_upload_root()))
    repo = _get_repository(request)
    try:
        attachment = repo.insert(
            attachment_id=attachment_id,
            user_id=user_id,
            filename=safe_filename,
            content_type=sniffed,
            category=category,
            extension=extension,
            size_bytes=size_bytes,
            sha256=sha256,
            storage_path=rel_storage,
        )
    except Exception:
        store.delete(user_id, attachment_id)
        raise

    logger.info(
        f"Uploaded attachment {attachment_id} ({size_bytes} bytes, {category}) "
        f"for user={user_id}"
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=_attachment_to_response(attachment),
    )


# ---------------------------------------------------------------------------
# GET /api/attachments
# ---------------------------------------------------------------------------


@attachments_router.get(
    "/api/attachments",
    summary="List the calling user's attachments",
)
async def list_attachments(
    request: Request,
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    user_id: str = Depends(require_user_id),
):
    repo = _get_repository(request)
    items, next_cursor = repo.list_for_user(
        user_id, category=category, limit=limit, cursor=cursor,
    )
    return {
        "attachments": [_attachment_to_response(a) for a in items],
        "next_cursor": next_cursor,
    }


@attachments_router.get(
    "/api/attachments/{attachment_id}",
    summary="Get one attachment's metadata",
)
async def get_attachment(
    request: Request,
    attachment_id: str,
    user_id: str = Depends(require_user_id),
):
    repo = _get_repository(request)
    att = repo.get_by_id(attachment_id, user_id)
    if att is None:
        # Deliberately 404, not 403, so we don't confirm existence to non-owners.
        raise HTTPException(status_code=404, detail="Attachment not found")
    return _attachment_to_response(att)


@attachments_router.delete(
    "/api/attachments/{attachment_id}",
    summary="Soft-delete an attachment",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_attachment(
    request: Request,
    attachment_id: str,
    user_id: str = Depends(require_user_id),
):
    repo = _get_repository(request)
    deleted = repo.soft_delete(attachment_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Attachment not found")
    # Best-effort blob removal.
    store.delete(user_id, attachment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["attachments_router", "MAX_UPLOAD_BYTES"]
