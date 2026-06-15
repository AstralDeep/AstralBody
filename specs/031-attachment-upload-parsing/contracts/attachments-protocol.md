# Contract: Attachment Protocol (REST + WebSocket + Chrome)

This feature is server-driven; its "interfaces" are the REST upload endpoints (existing), the WS `chat_message` payload (extended), WS status/render messages, and the attachment chrome surface. All shapes below are additive and backward-compatible.

## 1. REST — upload & manage (existing, behavior extended)

### `POST /api/upload`  (auth: `require_user_id`)
Multipart `file`. Streams to disk (256 KiB chunks), validates extension∈allowlist (now broadened), enforces per-category size cap, sniffs content-type for consistency.

**Response 201** (extended with `parser_status`):
```json
{
  "attachment_id": "uuid",
  "filename": "design.parquet",
  "category": "data",
  "extension": "parquet",
  "content_type": "application/octet-stream",
  "size_bytes": 1048576,
  "sha256": "…",
  "created_at": "2026-06-15T12:00:00Z",
  "parser_status": "covered | preparing | pending_admin_approval | unavailable"
}
```
- `covered` — a built-in or already-live global parser handles this type.
- `preparing` — uncovered type; an autoparse draft has been enqueued (eager, FF_ATTACHMENT_AUTOPARSE on).
- `pending_admin_approval` — a draft for this format already exists and is awaiting an admin (dedup hit).
- `unavailable` — uncovered and autoparse disabled (flag off) or creation failed; the type cannot be read yet.

**Errors**: `413` (over cap, message names the limit), `415` (type not on allowlist), `422` (extension/content mismatch). Each rejection happens **before** the file is referenced in any message.

### `GET /api/attachments?category=&limit=&cursor=`  (auth)
Cursor-paginated list of the caller's live attachments (newest first). Unchanged.

### `GET /api/attachments/{attachment_id}`  (auth)
Single attachment metadata; `404` for non-owner/deleted (no existence disclosure). Unchanged.

### `DELETE /api/attachments/{attachment_id}`  (auth)
Soft-delete (`204`); `404` for non-owner. After delete, the id can no longer be referenced in new turns. Unchanged.

## 2. WebSocket — sending a turn with attachments

### Client → server: `ui_event` / `chat_message` (payload extended)
```json
{
  "type": "ui_event",
  "action": "chat_message",
  "session_id": "chat-uuid",
  "payload": {
    "message": "Summarize these for me",
    "chat_id": "chat-uuid",
    "attachments": [
      { "attachment_id": "uuid", "filename": "report.pdf", "category": "document" },
      { "attachment_id": "uuid", "filename": "design.parquet", "category": "data" }
    ]
  }
}
```
- `attachments` is OPTIONAL and additive; absent → current behavior. Max 10 entries.
- Server validates each `attachment_id` is live & owned by the sender; invalid/foreign ids are dropped with a logged `file` audit and a user-visible note (never silently parsed).
- Server inserts `message_attachment` rows and injects a structured **"Attachments on this turn"** block into the agent-facing user message:
  ```
  [Attachments on this turn]
  - id=<attachment_id> name="report.pdf" category=document (readable: read_document)
  - id=<attachment_id> name="design.parquet" category=data (readable: pending parser)
  ```
- The model calls the indicated `read_*` / `parse_<fmt>` tool with the `attachment_id`; `user_id` is injected at dispatch for ownership enforcement.

### Server → client: attachment status card
Reuses existing chat-card delivery (`chat_step`/chrome card). For an uncovered upload the uploader receives, on their chat socket(s):
```json
{ "type": "chat_status", "status": "info",
  "message": "No reader exists for .parquet yet — a parser is being prepared and is pending admin approval." }
```
Delivered to ALL of the user's sockets on that chat (feature-028 fan-out).

### Server → client: `load_chat` re-hydration
`chat_loaded` transcript messages that had attachments include their `message_attachment` references so chips re-render in history.

## 3. Chat-input affordance (server-rendered)

- `shell.html` `#astral-form` gains: a paperclip `<button type="button" class="astral-attach-btn">`, a hidden `<input type="file" class="astral-file-upload" multiple>` honoring the broadened `accept` list, and a `#astral-attachments` chips row.
- `client.js`: on file pick → `POST /api/upload` per file → push a chip (`badge`-styled) showing filename + state (`uploading|ready|failed`), each with a remove control; track ready `attachment_id`s and include them in the next `chat_message`; clear chips after send. Honors the 10-file cap and shows server rejection reasons inline.

## 4. Attachment library chrome surface (US3)

New surface `webrender/chrome/surfaces/attachments.py` (NOT astralprims):
- Exports `TITLE = "Attachments"`, `async def render(orch, user_id, roles, params)`, `HANDLERS`.
- `render` lists the user's attachments (via repository) with attach/delete controls.
- Handlers (dispatched through `chrome_events.py`, all ownership-checked):
  - `chrome_attach_existing` → adds an existing `attachment_id` to the compose tray (no re-upload, no duplicate blob).
  - `chrome_attachment_delete` → soft-delete; re-render list.
- Opened from the paperclip menu via `chrome_open` → pushed as `chrome_render {region:"modal", html}`.

## Backward compatibility

- Turns without `attachments[]` behave exactly as before.
- The legacy `"[Attachment: …]"` / `"I have uploaded …"` text remains tolerated for old transcripts (regex path retained, not extended).
