# Contract — Windows Attachment Lifecycle (044)

**Satisfies**: FR-020, FR-021, US4 | **Research**: R10
**Reference implementation**: Android (`AstralRest.uploadAttachment`, `StagedAttachment`
staging, chip strip) and the web composer — no new backend surface; the wire already supports
everything.

## 1. REST upload (existing endpoint, new Windows helper)

```
rest.upload_attachment(http_base, token, filename, mime, data: bytes)
  → POST {http_base}/api/upload   (multipart/form-data, field "file"; stdlib urllib — no new dependency)
  ← {attachment_id, filename, category, parser_status}
  parser_status ∈ {covered, preparing, pending_admin_approval, unavailable}
errors: server rejection (4xx body) surfaces on the chip; network failure → chip state "failed"
```

Uploads run on a worker thread (existing `_download` pattern); UI stays responsive; ≤10
staged files per message (web parity).

## 2. Composer affordance

- Paperclip button beside the input with a two-entry menu (web parity):
  **Upload files…** → multi-select `QFileDialog` → stage+upload each;
  **Choose from your files** → `chrome_open {surface:"attachments"}`
  ([chrome-parity.md §3.3](chrome-parity.md)) — rows' `attach_existing` stages a chip with no
  re-upload.
- **Chip strip** above the input row: per chip — filename, parser-status glyph + tooltip
  (ready / preparing / pending admin approval / unavailable — same escalation story and
  wording family as web/Android), remove ✕. Failed uploads show state on the chip and are
  removable.

## 3. Send & re-hydration

- Send maps `ready`-state chips to
  `chat_message.payload.attachments = [{attachment_id, filename, category}]` via the existing
  `send_chat(attachments=…)` parameter; the strip clears on send. Non-covered statuses ride
  along exactly as on Android (the server's turn block explains parser status to the agent).
- Reloading a chat (`load_chat`) renders each turn's attachments as chips in the transcript
  rail — consistent with web chips and Android (US4.3).
- Staged-but-never-sent uploads orphan a server row (identical to web/Android; the library
  surface lists and can delete them) — spec Edge Case 6: no session corruption, clean reopen.

## 4. Acceptance mapping

- US4.1 chips + statuses + removal + sent payload → §2–§3.
- US4.2 no-parser escalation story visible → §1 statuses + chip presentation.
- US4.3 cross-client turn-attachment consistency on reload → §3.
