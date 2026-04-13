# Phase 1 Data Model: Common File Type Uploads

**Feature**: 002-file-uploads
**Date**: 2026-04-13

## Entities

### Attachment

A file uploaded by a user. User-scoped (FR-009), persisted across chats (FR-012).

| Field | Type | Notes |
|-------|------|-------|
| `attachment_id` | UUIDv4 (string) | Primary key. Generated server-side at upload. |
| `user_id` | string | Keycloak `sub` of the uploading user. Indexed. |
| `filename` | string | Original filename, after `os.path.basename` sanitization. ≤ 255 chars. |
| `content_type` | string | Detected MIME type from `python-magic`, not the browser-claimed type. |
| `category` | enum | One of `document`, `spreadsheet`, `presentation`, `text`, `image`. Drives tool dispatch. |
| `extension` | string | Lowercased canonical extension (e.g., `pdf`, `xlsx`). |
| `size_bytes` | int64 | Final stored size; ≤ 31_457_280 (30 MB, FR-003). |
| `sha256` | string (hex) | Content hash; used for de-duplication suggestions (not enforced) and integrity checks. |
| `storage_path` | string | Relative path under the configured upload root: `{user_id}/{attachment_id}/{filename}`. |
| `created_at` | timestamp | UTC. |
| `deleted_at` | timestamp, nullable | Set when the user removes the file or the account is deleted. Soft-delete. |

**Validation rules**:
- `size_bytes ≤ 30 MB` (FR-003). Enforced at upload; never written for oversized files.
- `extension` MUST be in the allow-list defined in `attachmentTypes.ts` / `content_type.py` (FR-001).
- `content_type` MUST be consistent with `extension`; mismatch is an upload error (FR-008).
- `user_id` MUST come from the validated Keycloak token; never client-supplied.

**Lifecycle / state transitions**:

```
        upload accepted
NONE  ─────────────────►  ACTIVE
                            │
                            │  user removes file
                            │  OR account deleted
                            ▼
                         DELETED  (deleted_at set, blob purged)
```

`DELETED` is terminal. A `DELETED` attachment MUST NOT be returned by listing endpoints, MUST NOT be readable by any agent tool, and its on-disk blob MUST be removed (best-effort; orphan blobs are reaped by a periodic janitor).

**Authorization invariant**: For every read or delete of an Attachment, the calling user's Keycloak `sub` MUST equal `Attachment.user_id`. Enforced both at the REST layer (`/api/attachments/*`) and inside each agent file tool's dispatcher.

---

### ChatMessage (existing — extension only)

The existing ChatMessage entity gains an optional list of attachment references.

| New field | Type | Notes |
|-----------|------|-------|
| `attachments` | `AttachmentRef[]` (optional) | Zero or more references to `Attachment`s the user attached when sending this message. Stored by reference, not by value. |

**Validation rules**:
- Every `attachment_id` in `attachments` MUST resolve to an `Attachment` owned by the message's sender at send time. A message referencing a foreign or `DELETED` attachment is rejected.
- A message MAY reference an attachment that was originally uploaded in a different chat by the same user (cross-chat reuse, per FR-009).

---

### AttachmentRef (value object on a message)

Lightweight pointer embedded in a ChatMessage so the message itself can be rendered without joining the attachment table on every read.

| Field | Type | Notes |
|-------|------|-------|
| `attachment_id` | UUIDv4 | FK into `user_attachments`. |
| `filename` | string | Snapshot of the filename at attach time, for display in chat history even if the user later renames or deletes the file. |
| `category` | enum | Snapshot, same reason. |

If the underlying Attachment is later `DELETED`, the chat message renders the chip in a "no longer available" state (greyed out), preserving conversation history without resurrecting the file.

---

### Agent File Tool (capability descriptor — not persisted)

Conceptual entity that lives in `TOOL_REGISTRY`. One per category (see research.md §8).

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | e.g., `read_document`, `read_spreadsheet`, `read_presentation`, `read_text`, `read_image`. |
| `scope` | string | Existing field in TOOL_REGISTRY; uses the standard general-agent scope. |
| `description` | string | Human-readable; consumed by the agent's planner. |
| `input_schema` | JSON Schema | Declares `attachment_id` (required) plus category-specific optional args (e.g., `sheet_name`, `page_range`, `max_chars`). |
| `function` | callable | Dispatcher → reader implementation in `backend/agents/general/file_tools/`. |

---

## Storage / persistence summary

- **SQL table `user_attachments`** holds Attachment rows. Indexed on (`user_id`, `created_at DESC`) for the cross-chat library panel and on `attachment_id` for direct lookup.
- **Filesystem** holds blobs at `${UPLOAD_ROOT}/{user_id}/{attachment_id}/{filename}`. The directory-per-attachment layout avoids filename collisions and makes deletion atomic (`rmdir` after `unlink`).
- **No new caches** are introduced. Parsed text is computed on each tool call; if a parse becomes a hot path, a future iteration can add a content-addressed cache keyed by `sha256` + tool args.
