# Feature Specification: Common File Type Uploads in Chat UI

**Feature Branch**: `002-file-uploads`
**Created**: 2026-04-13
**Status**: Draft
**Input**: User description: "I want to add common file type uploads to this dynamic UI interface. I want to expand the paperclip icon in the chat window to take in a variety of common file types. Reference claude-code/ to see how this project does file uploads and the file types it accepts. In the AstralBody general agent there should be tools to handle the upload of the variety of file types."

## Clarifications

### Session 2026-04-13

- Q: How long does an uploaded file persist on the server after the message is sent? → A: Retain for the lifetime of the chat; purged when the chat is deleted or the user account is deleted.
- Q: Is the agent's current model vision-capable, or does this feature need to add vision? → A: A vision-capable model will be connected separately; this feature only needs to deliver the uploaded image bytes to it.
- Q: How should scanned / image-only PDFs (no extractable text) be handled? → A: Attempt OCR first; if OCR fails or yields no usable text, fall back to delivering the page images to the vision model.
- Q: What is the maximum number of attachments per message? → A: No fixed per-message cap; only the 30 MB per-file size limit applies.
- Q: Can the same user access files they uploaded in one chat from a different chat? → A: Yes. Uploaded files are global to the user and appear inline in any of that user's chat interfaces. Because files are user-scoped (not chat-scoped), they are purged on explicit user removal or account deletion; deleting a single chat does not delete the file.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Attach a document for the agent to analyze (Priority: P1)

A clinician or analyst is chatting with the AstralBody general agent and wants to ground the conversation in a real artifact (a PDF report, a spreadsheet of patient cohorts, a Markdown protocol, a Word memo). They click the paperclip icon next to the chat input, pick a file from their computer, and send a message asking the agent to summarize, extract, or reason over the file's contents.

**Why this priority**: This is the core value of the feature. Today the paperclip only supports four plain-text formats (`.csv`, `.txt`, `.json`, `.md`), which forces users to convert documents externally before they can talk to the agent about them. Removing that friction is the whole point of the work.

**Independent Test**: Open the chat, click the paperclip, attach a single PDF (and separately a DOCX, XLSX, image, and code file), send a message, and confirm the agent's reply demonstrates it actually read the file's contents (not just the filename).

**Acceptance Scenarios**:

1. **Given** the chat is open, **When** the user clicks the paperclip icon, **Then** the file picker offers all supported categories (documents, spreadsheets, presentations, text/code, images) and accepts them without an "unsupported type" error.
2. **Given** a user attaches a 5 MB PDF, **When** they send a message asking "summarize this", **Then** the agent's response references content that only appears inside the PDF.
3. **Given** a user attaches an XLSX with a sheet of patient IDs, **When** they ask the agent to graph the data, **Then** the agent treats the spreadsheet as structured data (not as opaque bytes) and produces a chart or a clear explanation of why it cannot.
4. **Given** a user attaches a PNG screenshot, **When** they ask "what does this image show?", **Then** the agent's reply describes elements visible in the image.

---

### User Story 2 - Attach multiple files in one turn (Priority: P2)

The user wants to compare two reports, or pair a data file with a written brief, in a single message.

**Why this priority**: Common in real workflows (e.g., "compare last quarter's report to this quarter's"). Valuable, but the single-file path in Story 1 already unlocks the bulk of the value.

**Independent Test**: Attach two files of different types in one message, send it, and confirm the agent receives and can reason about both.

**Acceptance Scenarios**:

1. **Given** a user has selected one file, **When** they click the paperclip again and pick a second file, **Then** both attachments appear in the composer and both are sent with the next message.
2. **Given** multiple attachments are pending, **When** the user removes one before sending, **Then** only the remaining attachments are sent.

---

### User Story 3 - Drag and drop a file onto the chat (Priority: P2)

The user drags a file from their file explorer directly onto the chat window instead of using the picker.

**Why this priority**: Drag-and-drop already exists for the current limited types; extending it to cover the new types is a small addition that meaningfully improves ergonomics.

**Independent Test**: Drag each newly supported file type onto the chat window and confirm it is accepted with the same behavior as the picker.

**Acceptance Scenarios**:

1. **Given** the chat is visible, **When** the user drags a supported file over it, **Then** a drop target indicator appears.
2. **Given** the user drops a supported file, **When** the drop completes, **Then** the file is attached identically to a picker selection.
3. **Given** the user drops an unsupported file, **When** the drop completes, **Then** the user sees a clear message naming the rejected file and the reason, and no attachment is added.

---

### User Story 4 - Clear feedback when an upload is rejected (Priority: P3)

The user attaches a file that is too large, of an unsupported type, or otherwise fails to upload, and needs to understand why.

**Why this priority**: Important for trust, but a fallback path rather than the main flow.

**Independent Test**: Attempt to attach (a) a file larger than the size limit, (b) a file with an unsupported extension, (c) a file that fails mid-upload (e.g., network drop). Confirm each produces a distinct, actionable message and leaves the composer in a usable state.

**Acceptance Scenarios**:

1. **Given** the user picks a file larger than the maximum allowed size, **When** the picker closes, **Then** an error names the file, the size, and the limit, and the file is not attached.
2. **Given** the user picks an unsupported extension, **When** the picker closes, **Then** an error names the extension and lists the supported categories.
3. **Given** an upload fails partway, **When** the failure is detected, **Then** the user is offered a retry and the rest of the composer state (typed text, other attachments) is preserved.

---

### Edge Cases

- A file with a supported extension but corrupt/unreadable contents (e.g., a PDF that is actually a renamed binary).
- A file whose extension is supported but whose content is many times larger than typical (e.g., a 25 MB CSV) — must still respect the global size cap.
- A password-protected document (PDF/DOCX/XLSX) that the agent cannot open.
- Files with non-ASCII filenames or unusual whitespace.
- Image files larger than typical chat thumbnails (the UI must not lock up rendering them).
- The user attaches a file, then closes the chat or navigates away before sending — the pending attachment should not silently persist into a later, unrelated conversation.
- The user attaches a file containing potentially sensitive data (PHI). The system must not log file contents in plain text in places not already approved for PHI.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The chat composer's paperclip control MUST allow the user to attach files in the following categories, in addition to the currently supported `.csv`, `.txt`, `.json`, `.md`:
  - **Documents**: `.pdf`, `.docx`, `.doc`, `.rtf`, `.odt`
  - **Spreadsheets**: `.xlsx`, `.xls`, `.ods`, `.tsv`
  - **Presentations**: `.pptx`, `.ppt`, `.odp`
  - **Structured text & config**: `.yaml`, `.yml`, `.xml`, `.html`, `.htm`, `.log`
  - **Code**: `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.sql`, `.sh`, `.ps1`, `.css`
  - **Images**: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`
- **FR-002**: The same set of file types in FR-001 MUST also be accepted via drag-and-drop onto the chat window.
- **FR-003**: The system MUST enforce a maximum per-file upload size of 30 MB (matching the reference behavior in `claude-code`'s upload pipeline) and reject larger files with a clear, named error.
- **FR-004**: The user MUST be able to attach more than one file to a single message and remove individual attachments before sending.
- **FR-005**: The UI MUST render a recognizable preview or chip for each attachment (filename, type icon or thumbnail for images, size) before the message is sent.
- **FR-006**: When an attachment is rejected (unsupported type, oversize, upload failure), the system MUST display a message that names the file, states the reason, and preserves any other in-progress composer state (typed text, other valid attachments).
- **FR-007**: The AstralBody general agent MUST expose tools that can read and reason over each supported file category, producing structured content suitable for the agent's response (e.g., extracted text for documents, tabular data for spreadsheets, parsed structure for code/markup, visual description for images).
- **FR-008**: The agent's tool surface MUST handle a file by its actual content type, not solely by extension, so that a mislabeled or corrupt file produces a meaningful error rather than silent garbage in the conversation.
- **FR-009**: Attached files MUST be scoped to the uploading user. They MUST be accessible to that same user across any of their chats and MUST appear inline in any of that user's chat interfaces, but MUST NOT be accessible to any other user.
- **FR-010**: The system MUST deliver image attachments to a vision-capable model in a form it can visually interpret (not just a filename or path). Selecting, hosting, or configuring the vision model itself is out of scope for this feature; this feature is responsible only for routing the image bytes to it.
- **FR-011**: The system MUST not transmit, log, or persist file contents in any location not already authorized to hold the data class involved (notably PHI in any clinical files).
- **FR-012**: Uploaded files MUST be retained as long as the uploading user's account exists, remain accessible inline whenever the user opens any of their chats, and MUST be purged on explicit user removal of the file or on account deletion. Deleting a single chat that referenced a file MUST NOT delete the file itself. No automatic time-based expiry applies.
- **FR-013**: For PDFs and image-based document content, the system MUST first attempt to extract embedded text (including via OCR for scanned pages). If text extraction fails or returns no usable content, the system MUST fall back to delivering the page images to the connected vision-capable model so the agent can still reason about the document.

### Key Entities *(include if feature involves data)*

- **Attachment**: A file the user has uploaded. Has a filename, a detected type/category, a size, an upload status (pending/uploaded/failed), and an owning-user association. Persists across the user's chats and appears inline in any of them; lifetime is bounded by explicit user removal or account deletion, not by the lifetime of any single chat.
- **Conversation Message**: An existing entity; gains the ability to carry zero or more Attachments and to surface them back to the agent's tool layer.
- **Agent File Tool**: A capability registered on the general agent that, given an Attachment reference, returns content the agent can reason over (text, table, structured tree, or image).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can attach any file type listed in FR-001 and receive an agent reply that demonstrably uses the file's contents within 15 seconds for files up to 5 MB.
- **SC-002**: At least 95% of upload attempts for files of supported type and within the size limit succeed on the first try (measured over a representative test set).
- **SC-003**: When a user attaches an unsupported or oversize file, 100% of attempts produce an on-screen error that names both the file and the specific reason within 2 seconds.
- **SC-004**: The number of distinct file types a user can usefully share with the agent grows from 4 today to at least 25, covering documents, spreadsheets, presentations, code/markup, and images.
- **SC-005**: For a representative set of test attachments (one per category in FR-001), the agent's response correctly references file content in at least 90% of cases, as judged by a reviewer comparing the reply to the source file.
- **SC-006**: No file uploaded by one user is ever visible to or retrievable by any other user across all test runs. Files uploaded by a given user are reachable from any of that same user's chats.

## Assumptions

- The 30 MB per-file cap is a reasonable starting point because it matches the cap used in the reference `claude-code` upload pipeline; it can be tuned later without changing the user-facing flow.
- Office formats (`.docx`, `.xlsx`, `.pptx`, and their legacy `.doc`/`.xls`/`.ppt` variants) are expected to be readable as text/structure; rendered fidelity (fonts, layout) is not a goal.
- Image understanding is performed by a separately-connected vision-capable model. This feature is responsible only for delivering image bytes to that model; selecting or configuring the model is out of scope.
- Drag-and-drop and the file picker share the same accepted-type list and the same size limit — there is no "power user" bypass.
- There is no fixed cap on the number of attachments per message; only the 30 MB per-file size limit applies. The composer UI must remain usable when many attachments are pending.
- "Common file types" is interpreted as the categories listed in FR-001; rarer formats (e.g., `.epub`, `.dwg`, audio, video) are explicitly out of scope for this iteration.
