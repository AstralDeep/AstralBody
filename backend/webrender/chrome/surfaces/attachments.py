"""Feature 031 — Attachments library surface (US3).

Browse the user's previously uploaded attachments, attach an existing one to
the next message without re-uploading, and delete attachments. The "attach"
action is handled client-side (it stages a chip in the compose tray — no server
round-trip and no duplicate blob); "delete" routes through the existing
soft-delete via the ``chrome_attachment_delete`` handler.

Renders for the web target only (chrome layer). All reads are user-scoped.
"""
import json
import logging

from webrender import esc
from webrender.chrome import notice_block

logger = logging.getLogger("Orchestrator.Chrome")

TITLE = "Attachments"

_CATEGORY_LABEL = {
    "document": "document", "spreadsheet": "spreadsheet", "presentation": "presentation",
    "text": "text/code", "image": "image", "medical": "medical",
    "data": "data", "archive": "archive",
}


def _human_size(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def _repo(orch):
    from orchestrator.attachments.repository import AttachmentRepository
    return AttachmentRepository(orch.history.db)


def _row_html(att) -> str:
    cat = _CATEGORY_LABEL.get(att.category, att.category)
    data = (
        f'data-attachment-id="{esc(att.attachment_id)}" '
        f'data-filename="{esc(att.filename)}" '
        f'data-category="{esc(att.category)}"'
    )
    del_payload = esc(json.dumps({"attachment_id": att.attachment_id}))
    return (
        f'<div class="flex items-center gap-2 bg-white/5 border border-white/10 rounded-lg p-3">'
        f'<div class="min-w-0 flex-1">'
        f'<div class="text-sm text-astral-text truncate">{esc(att.filename)}</div>'
        f'<div class="text-xs text-astral-muted">{esc(cat)} · {esc(_human_size(att.size_bytes))}</div>'
        f'</div>'
        f'<button type="button" class="astral-attach-existing px-3 py-1.5 rounded-lg text-xs '
        f'font-medium bg-astral-primary text-white" {data}>Attach</button>'
        f'<button type="button" class="px-3 py-1.5 rounded-lg text-xs text-red-400 '
        f'hover:bg-red-500/10" data-ui-action="chrome_attachment_delete" '
        f"data-ui-payload='{del_payload}'>Delete</button>"
        f'</div>'
    )


async def render(orch, user_id, roles, params) -> str:
    """List the caller's live attachments with attach/delete controls."""
    try:
        items, _ = _repo(orch).list_for_user(user_id, limit=100)
    except Exception:
        logger.exception("attachments surface: list failed")
        return notice_block("error", "Could not load your attachments.")
    if not items:
        return (
            '<div class="text-sm text-astral-muted italic">No uploads yet. Use the '
            "paperclip in the chat box to attach a file — it will appear here so you can "
            "reuse it in other chats.</div>"
        )
    rows = "".join(_row_html(a) for a in items)
    return (
        '<div class="text-xs text-astral-muted mb-2">Attach a previously uploaded file to '
        "your next message (no re-upload), or delete files you no longer need.</div>"
        f'<div class="space-y-2">{rows}</div>'
    )


async def _h_attachment_delete(orch, websocket, user_id, roles, payload):
    """Soft-delete an attachment (reuses the existing repository path)."""
    attachment_id = str((payload or {}).get("attachment_id") or "")
    if not attachment_id:
        return ("attachments", {}, notice_block("error", "No attachment specified."))
    try:
        from orchestrator.attachments import store
        deleted = _repo(orch).soft_delete(attachment_id, user_id)
        if deleted:
            store.delete(user_id, attachment_id)  # best-effort blob removal
    except Exception:
        logger.exception("attachments surface: delete failed")
        return ("attachments", {}, notice_block("error", "Delete failed — please try again."))
    if not deleted:
        return ("attachments", {}, notice_block("error", "Attachment not found."))
    return ("attachments", {}, notice_block("success", "Attachment deleted."))


HANDLERS = {
    "chrome_attachment_delete": _h_attachment_delete,
}
