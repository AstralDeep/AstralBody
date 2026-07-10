# Quickstart: Chat Attachment Upload & Universal Parsing

How to run, exercise, and verify feature 031 locally. Everything runs in the `astraldeep` container (backend needs py3.11); `.env` must have `ASTRAL_ENV=development`.

## Boot

```bash
docker compose up -d                       # postgres + astraldeep (idempotent _init_db runs the new tables/column)
# open the web client (orchestrator shell) on :8001 and log in via Keycloak
```

Confirm migrations applied (guarded, safe to re-run):
```bash
docker exec astraldeep bash -c "cd /app/backend && python -c \"from shared.database import Database; d=Database(); cur=d.conn.cursor(); \
cur.execute(\\\"select to_regclass('message_attachment'), to_regclass('attachment_parser')\\\"); print(cur.fetchone())\""
# → ('message_attachment', 'attachment_parser')
```

## US1 — attach a supported file and have it parsed (P1, MVP)

1. In a chat, click the **paperclip** in the input. The picker offers the broadened accepted-type list.
2. Select a PDF and a CSV. Two chips appear (`uploading` → `ready`); remove one to confirm removal works.
3. Send "summarize these". 
4. **Verify**: the agent calls `read_document`/`read_spreadsheet` with the real `attachment_id`s and its reply reflects the file contents. Network: the `chat_message` WS frame carries `payload.attachments[]` (not a `"[Attachment: …]"` string).
5. **Ownership**: as a second user, attempt to reference the first user's `attachment_id` → refused (treated as not found).

## US2 — upload a type with no parser → safe auto-creation (P2)

1. Upload a file of an **uncovered** accepted type (e.g. `.parquet`/`.zip`). The upload response shows `parser_status: "preparing"`; the chat shows "No reader exists for .parquet yet — a parser is being prepared and is pending admin approval."
2. **Background**: a draft `<EXT> Parser` agent is created (`draft_agents.origin='auto_attachment'`), security-gated, and self-tested **against the uploaded file**. An `attachment_parser` row is `pending`.
3. Re-upload the same type → `parser_status: "pending_admin_approval"` and **no second draft** (dedup; `attachment_parser` has one row for the gap).
4. As a **non-admin**, try to approve the draft → refused (audited). As an **admin**, open the drafts chrome surface, review the self-test, and **approve**.
5. **Verify**: on approval the parser goes **global** (`agent_ownership.is_public=true`, `attachment_parser.status='live'`), the original file is re-parsed, and the uploader's chat continues. A different user can now upload that type and gets `parser_status: "covered"`.
6. **Fail-closed**: discard a draft, or set `FF_ATTACHMENT_AUTOPARSE=false` and upload an uncovered type → user is told the type cannot be read; no parser code runs against the file.

## US3 — reuse & manage attachments (P3)

1. Upload a file in chat A. Open chat B, click the paperclip → **Attachments** library → attach the existing file (no re-upload, no duplicate blob) → send → agent reads it.
2. Delete an attachment from the library → it disappears and can no longer be attached or read.

## Tests

```bash
docker exec astraldeep bash -c "cd /app/backend && python -m pytest -q tests/attachments tests/chrome agents/general/tests/file_tools orchestrator/tests"
docker exec astraldeep bash -c "cd /app/backend && python -m pytest -q"     # full suite
docker exec astraldeep bash -c "cd /app/backend && python -m ruff check ."  # lint
```

Key cases to look for (added by this feature):
- broadened allowlist accepts new types; new categories enforce their size caps; mismatch/oversize rejected pre-reference.
- `chat_message.attachments[]` → `message_attachment` rows; structured block injected; foreign id dropped + audited.
- coverage lookup; eager gap detection on upload; format-scoped dedup (one draft per gap).
- admin-only approval (non-admin denied + audited); global promotion sets `is_public=true` + `attachment_parser.status='live'`; original file re-parsed.
- fail-closed: flag off / failed self-test / discard → "cannot read this type yet", no execution.

## Audit trail

Trace one parser's full lifecycle by `correlation_id` (= draft id):
```sql
SELECT action_type, outcome, recorded_at FROM audit_events
WHERE correlation_id = '<draft_id>' AND event_class='agent_lifecycle' ORDER BY recorded_at;
-- gap_detected → auto_created → self_test → approved (or rejected)
```

## Manual UI verification (Constitution X)

Exercise against a real browser on `:8001` against the live backend: paperclip → pick → chips → send → parsed reply; admin approval flow; library reuse/delete. Type-checks and unit tests do not substitute for this.
