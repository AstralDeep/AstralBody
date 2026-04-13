# Contract: Attachment REST API

**Feature**: 002-file-uploads
**Authoritative source**: FastAPI route definitions in `backend/orchestrator/auth.py` (existing endpoint, modified) and `backend/orchestrator/api.py` (new endpoints). Interactive schema is published at `/docs` per Constitution VI.

All endpoints require a valid Keycloak bearer token; the user identity is the validated `sub` claim. No endpoint accepts a client-supplied `user_id`.

---

## POST /api/upload

Upload a single file. Modified from today's behavior to: (a) accept the expanded type list, (b) enforce 30 MB, (c) store under `{user_id}/{attachment_id}/{filename}` instead of `{user_id}/{session_id}/{filename}`, (d) return an `attachment_id`.

**Request**: `multipart/form-data`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `file` | file | yes | The single file being uploaded. |

**Validation**:
- Content-Length (or streamed total) ≤ 31_457_280 bytes → else `413 Payload Too Large`.
- Extension MUST be in the allow-list (FR-001) → else `415 Unsupported Media Type`.
- Sniffed content type (via `python-magic`) MUST be consistent with extension → else `415 Unsupported Media Type` with body explaining the mismatch (FR-008).
- Filename sanitized via `os.path.basename`; path traversal characters are rejected.

**Response** `201 Created`:

```json
{
  "attachment_id": "f3b1c2e0-9c4f-4f3a-9d2e-7b0a8e6c5d12",
  "filename": "Q4-report.pdf",
  "category": "document",
  "extension": "pdf",
  "content_type": "application/pdf",
  "size_bytes": 4823104,
  "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "created_at": "2026-04-13T17:42:11Z"
}
```

**Errors**:

| Status | When |
|--------|------|
| `401 Unauthorized` | Missing/invalid Keycloak token. |
| `413 Payload Too Large` | File exceeds 30 MB. Body names the file and the limit (SC-003). |
| `415 Unsupported Media Type` | Extension not in allow-list, or content/extension mismatch. Body lists supported categories. |
| `500 Internal Server Error` | Unexpected storage failure. Partial files MUST be cleaned up. |

---

## GET /api/attachments

List the calling user's non-deleted attachments. Powers the cross-chat AttachmentLibrary panel (FR-009).

**Query parameters**:

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `category` | enum, optional | none | Filter to one category. |
| `limit` | int | 50 | Max 200. |
| `cursor` | string, optional | none | Opaque cursor for pagination, returned as `next_cursor` in the previous response. |

**Response** `200 OK`:

```json
{
  "attachments": [
    {
      "attachment_id": "...",
      "filename": "...",
      "category": "document",
      "extension": "pdf",
      "size_bytes": 4823104,
      "created_at": "2026-04-13T17:42:11Z"
    }
  ],
  "next_cursor": "eyJjcmVhdGVkX2F0IjogIjIwMjYtMDQtMTNUMTc6NDA6MDBaIn0="
}
```

---

## GET /api/attachments/{attachment_id}

Return metadata for a single attachment. The blob itself is not transferred over this endpoint; agent tools read it directly from the filesystem via the storage module.

**Authorization**: The Attachment's `user_id` MUST equal the calling Keycloak `sub`. Otherwise `404 Not Found` (not 403 — we do not confirm or deny existence to non-owners).

**Response** `200 OK`: Same shape as items in the `GET /api/attachments` list.

**Errors**: `401`, `404`.

---

## DELETE /api/attachments/{attachment_id}

Soft-delete an attachment (FR-012). Marks `deleted_at`, then best-effort removes the on-disk blob.

**Authorization**: same ownership rule as GET.

**Response** `204 No Content`.

**Side effects**:
- Subsequent reads via `GET /api/attachments(/...)` MUST omit this attachment.
- Subsequent agent tool calls referencing this `attachment_id` MUST fail with a "not found" error.
- Existing `ChatMessage.attachments` references remain in chat history but render in the "no longer available" state; the message itself is not modified.

---

## Account deletion (out-of-band, contract for downstream)

When a user account is deleted (existing flow elsewhere in the auth subsystem), the account-deletion handler MUST:

1. Soft-delete every Attachment with the user's `user_id`.
2. Recursively remove the on-disk directory `${UPLOAD_ROOT}/{user_id}/`.

This is documented here so the account-deletion code owner has the contract; the implementation lives in the existing user-management module.
