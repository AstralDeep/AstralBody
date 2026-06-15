# Feature Specification: Chat Attachment Upload & Universal Parsing

**Feature Branch**: `031-attachment-upload-parsing`
**Created**: 2026-06-15
**Status**: Draft
**Input**: User description: "Add an attachment icon to the chat input where users can upload a lot of different file types that should have already been added previously. The system and tools and agents should be able to parse these files and if there is not an agent to parse a file type a tool should be safely created on the backend to read it."

## Clarifications

### Session 2026-06-15

- Q: How broad should the set of acceptable upload file types be? → A: Broaden the curated allowlist well beyond the current ~30 types (more document/data/archive/code formats), with per-category size caps; any accepted type that lacks a parser triggers the safe auto-creation flow.
- Q: Who may trigger auto-creation of a new backend parser tool? → A: Any authenticated user may trigger a draft and see its self-test results, but an admin (not the uploading user) must give final approval before the parser goes live.
- Q: Once an auto-created parser is approved, who can use it? → A: Global — once approved it joins the live fleet as a capability available to all users (no per-user duplication).
- Q: When is the "no parser exists" gap detected? → A: Eagerly, at upload time — when an unsupported file is uploaded the system begins detecting the gap and drafting a parser, before the user sends a message that needs it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Attach files in chat and have them understood (Priority: P1)

A user is in a chat with an agent. They click an attachment (paperclip) icon next to the message input, pick one or more files from their device, see each selected file appear as a labelled chip showing its name and upload state, and then send a message. The agent that handles the message receives references to those attachments, reads their contents, and responds using what it found in them (e.g. summarizes a PDF, answers a question about a spreadsheet, describes an image).

**Why this priority**: This is the core value of the feature — the entire point is letting users bring their own documents, data, and images into a conversation and have the assistant actually use them. The upload backend and the parsers already exist; without a visible way to attach files in the chat input and a path that delivers those attachments to the agent, none of it is reachable by a user. This single story is a complete, demonstrable MVP.

**Independent Test**: Open a chat, click the attachment icon, upload a supported file (e.g. a PDF and a CSV), send a message referencing it ("summarize this"), and confirm the agent's reply reflects the file's actual contents. Fully testable with no other story implemented.

**Acceptance Scenarios**:

1. **Given** a user viewing a chat, **When** they activate the attachment icon, **Then** a file picker opens that offers the full set of accepted file types.
2. **Given** a user has picked a supported file, **When** the upload begins, **Then** a chip appears showing the file name and a visible in-progress state, transitioning to a success state when the upload completes.
3. **Given** one or more files have finished uploading, **When** the user sends their message, **Then** the message is delivered to the handling agent together with references to those attachments.
4. **Given** an agent receives a message with a supported attachment, **When** it processes the request, **Then** it reads the attachment's contents through an existing parser and its response reflects the actual file contents.
5. **Given** a user picks a file that exceeds the size limit for its category or is of a disallowed type, **When** they attempt to attach it, **Then** they receive a clear, specific rejection message and the file is not sent to any agent.
6. **Given** a user has attached a file, **When** they remove its chip before sending, **Then** that attachment is not referenced in the sent message.

---

### User Story 2 - Upload a file no existing agent can read (Priority: P2)

A user attaches a file whose type is accepted for upload but for which no existing agent or tool knows how to extract content (a format outside the current parser coverage). Rather than waiting to fail, the system recognizes the gap as soon as the file is uploaded and safely begins creating a new backend parsing capability for that file type: it drafts a parser and runs it through the security gate and an isolated self-test. The user who uploaded the file is shown the self-test result, but the new parser only goes live after an administrator reviews and approves it; once live, it becomes a capability available to every user, the original file is parsed, and the conversation continues. Until an admin approves, the file is treated as not-yet-readable.

**Why this priority**: This is the feature's differentiator — it makes the set of readable file types open-ended instead of fixed. It is P2 rather than P1 because it depends on the attach-and-parse path (US1) existing first, and because the broadened accepted-type list still maps to existing parsers for the common cases, so most users get value from US1 alone.

**Independent Test**: Attach a file of an accepted type that has no existing parser, confirm the system begins a "new capability" draft on upload with self-test results visible, have an admin approve it, and confirm the file is then parsed and the agent answers using its contents — without any human editing backend code.

**Acceptance Scenarios**:

1. **Given** a user uploads a file of an accepted type that has no existing parser, **When** the upload completes, **Then** the system detects the gap and begins drafting a new parsing capability rather than waiting for or returning an unrecoverable error.
2. **Given** a draft parser has been generated, **When** it is evaluated, **Then** it passes through the same security gate and isolated self-test used for all auto-created capabilities before anything is offered for approval.
3. **Given** a draft parser passed its checks, **When** it is surfaced, **Then** the uploading user sees the self-test outcome and pending state, and the parser does not go live until an administrator approves it.
4. **Given** an administrator approves the draft parser, **When** approval completes, **Then** the parser joins the live fleet as a capability available to all users, the original attachment is parsed, and the agent's response reflects its contents.
5. **Given** a draft parser fails the security gate or its self-test, **When** the result is reported, **Then** the parser is not made available, the failure reason is shown, and it can be refined or discarded.
6. **Given** an administrator discards or declines the proposed parser, **When** they do so, **Then** no new capability is added and the uploading user is told the file type could not be read.
7. **Given** the same unreadable file type is uploaded again before the first draft is resolved, **When** the gap is re-encountered, **Then** the system does not generate a second redundant draft for the same file-type gap.

---

### User Story 3 - Reuse and manage previously uploaded attachments (Priority: P3)

A user who has uploaded files in earlier chats can browse their previously uploaded attachments, attach an existing one to a new message without re-uploading, and remove attachments they no longer want stored.

**Why this priority**: Convenience and housekeeping that build on US1. Valuable for repeat users working with the same documents across conversations, but not required for the core attach-parse loop to deliver value.

**Independent Test**: Upload a file in one chat, open a second chat, choose the file from the existing-attachments list, send a message, confirm the agent reads it; then delete an attachment and confirm it no longer appears in the list and can no longer be attached.

**Acceptance Scenarios**:

1. **Given** a user has previously uploaded attachments, **When** they open the attachment affordance, **Then** they can browse and pick from their existing attachments in addition to uploading new ones.
2. **Given** a user attaches an existing file by reference, **When** they send the message, **Then** the agent reads it exactly as it would a freshly uploaded file, with no duplicate stored copy.
3. **Given** a user deletes one of their attachments, **When** the deletion completes, **Then** it no longer appears in their list and can no longer be referenced in new messages.
4. **Given** an attachment belonging to another user, **When** a user attempts to reference it, **Then** the request is refused and the attachment is treated as not found.

---

### Edge Cases

- **Oversized file**: a file above its category limit is rejected before transfer completes, with a message naming the limit; no partial attachment is stored or referenced.
- **Disallowed / unrecognized type**: a file whose type is not on the accepted list is rejected at selection with a clear reason.
- **Extension/content mismatch**: a file whose actual content does not match its claimed type is rejected rather than parsed.
- **Parse failure on a supported type**: when a parser exists but fails on a specific file (corrupt, password-protected, truncated), the user gets a clear, specific error instead of a silent empty result, and the conversation can continue.
- **Upload interrupted**: a connection drop mid-upload leaves no half-stored attachment; the chip shows a failed state and can be retried or removed.
- **Attachment deleted before use**: a message references an attachment that was deleted; the agent reports the reference is no longer available rather than crashing.
- **Auto-created parser that misbehaves**: a drafted parser that fails the security gate, times out, errors, or produces no usable output during self-test is never made live.
- **Repeated unreadable type**: uploading the same unreadable file type again while a draft for that type is still pending does not spawn a second duplicate capability draft.
- **Very large specialized files** (e.g. medical imaging): files within the larger category limit upload and are referenced without blocking the chat; their handling respects the higher size ceiling defined for that category.
- **Many attachments at once**: a user attaches more files than the per-message limit; the system clearly indicates the limit and which files were and were not accepted.
- **No-text / image-only document**: a document with no extractable text is handled (e.g. routed to visual understanding) rather than returning empty content silently.

## Requirements *(mandatory)*

### Functional Requirements

#### Attachment affordance & upload (US1)

- **FR-001**: The chat input MUST present a visible attachment (paperclip) control that lets the user choose one or more files to attach to their next message.
- **FR-002**: The attachment control MUST be delivered through the project's server-driven UI path so it renders consistently for every supported client target and adapts to the connecting device, with no separate standalone client application.
- **FR-003**: When the user selects files, the system MUST display, for each file, a chip showing the file name and its current state (uploading, uploaded/ready, or failed), and MUST let the user remove any chip before sending.
- **FR-004**: The system MUST accept a broadened, curated allowlist of file types that extends well beyond the previously defined set (documents, spreadsheets, presentations, plain-text and code files, images, and specialized/medical formats) to include additional common document, data, archive, and code formats, each with a per-category size cap. The allowlist remains curated (not "any arbitrary binary"); an accepted type that has no existing parser is what drives the auto-creation path (US2).
- **FR-005**: The system MUST enforce the per-category size limits already defined for attachments and MUST reject files that exceed their category's limit with a message that states the limit.
- **FR-006**: The system MUST reject files whose type is not on the accepted list, and files whose actual content does not match their claimed type, with a clear, specific reason, before the file is referenced in any message.
- **FR-007**: Every uploaded attachment MUST be owned by the uploading user, and ownership MUST be verified on every subsequent read or reference; a user MUST NOT be able to read or reference another user's attachment.

#### Delivering attachments to agents & parsing (US1)

- **FR-008**: When a user sends a message that has attachments, the system MUST deliver references to those attachments to the agent that handles the message.
- **FR-009**: The handling agent MUST be able to read the contents of an attached file of a supported type using the existing parsing capabilities (documents, spreadsheets, presentations, text/code, images), and its response MUST be able to reflect that content.
- **FR-010**: When a supported file cannot be parsed for a file-specific reason (corrupt, protected, truncated, or empty of extractable content), the system MUST surface a clear, specific error and MUST allow the conversation to continue.
- **FR-011**: A document that contains no extractable text MUST be routed to an appropriate alternative understanding path (e.g. visual interpretation) rather than silently returning empty content.

#### Auto-creating a parser for an unsupported type (US2)

- **FR-012**: When an accepted-type file is uploaded and no existing agent or tool can extract its contents, the system MUST detect this gap **eagerly at upload time** (not only when an agent later attempts to read it) rather than returning an unrecoverable failure.
- **FR-013**: On detecting such a gap, the system MUST create a draft backend parsing capability for that file type by reusing the established agentic-creation lifecycle (draft → security gate → isolated self-test → approval decision → live).
- **FR-014**: A draft parser MUST pass the same automated security gate applied to all auto-created capabilities, and MUST be exercised in an isolated self-test, before it is offered for approval.
- **FR-015**: No auto-created parser may become live without **administrator approval**. Any authenticated user may trigger the draft and MUST be shown the self-test outcome and a pending state, but final approve / refine / discard authority rests with an administrator (who is not required to be the uploading user).
- **FR-016**: When a draft parser fails the security gate or self-test, the system MUST NOT make it available, MUST report the failure reason, and MUST allow it to be refined or discarded.
- **FR-017**: After an administrator approves a parser, the system MUST add it to the live fleet as a capability available to **all users** (global scope, no per-user duplication), then parse the originating attachment with it and continue the originating user's request using the extracted content.
- **FR-018**: The system MUST NOT generate more than one concurrent draft parser for the same unreadable file-type gap (deduplicated by file type) while a prior draft for that type is still pending.
- **FR-019**: The system MUST NEVER execute auto-generated parsing code against a user's file outside the security gate and approval flow described above (fail-closed: an unapproved, pending, or failed parser yields a "could not read this type yet" outcome, never silent execution).

#### Reuse & management (US3)

- **FR-020**: Users MUST be able to browse their previously uploaded attachments and attach an existing one to a new message without re-uploading it.
- **FR-021**: Referencing an existing attachment MUST NOT create a duplicate stored copy and MUST be read by agents identically to a freshly uploaded file.
- **FR-022**: Users MUST be able to delete their attachments; a deleted attachment MUST no longer appear in their list and MUST no longer be referenceable in new messages.

#### Observability, audit & persistence (cross-cutting)

- **FR-023**: The lifecycle of an auto-created parser (gap detected, draft generated, gate/self-test result, approval/refinement/discard, going live) MUST be recorded in the audit trail under the existing agent-lifecycle audit class, correlated so a single gap can be traced end to end.
- **FR-024**: Attachment events relevant to security and diagnosis (rejected upload, ownership-denied reference, parse failure) MUST be logged with enough structured detail to diagnose issues without code changes.
- **FR-025**: Any schema change required by this feature MUST be applied through the project's idempotent, guarded startup-migration mechanism, with a documented rollback path.
- **FR-026**: The feature MUST be delivered without adding any new third-party runtime dependency.

### Key Entities *(include if feature involves data)*

- **Attachment**: A file a user has uploaded. Owned by exactly one user. Has a display name, a detected type/category, a size, an integrity fingerprint, a storage reference, and a lifecycle state (active or deleted). Referenced by messages; never readable by a non-owner.
- **Attachment reference on a message**: The association between a sent chat message and one or more attachments the user included, used to deliver those attachments to the handling agent.
- **Parser capability**: A backend ability to extract content from a given file type. May be pre-existing (covering the common types) or auto-created on demand for a previously unreadable type. An auto-created parser carries provenance linking it to the gap, the uploading user/conversation that triggered it, and the administrator approval that made it live. Once approved it is global — a single fleet capability serving all users for that file type.
- **Capability-creation record**: The audit/lifecycle trail for an auto-created parser — gap detection, draft, security-gate and self-test outcomes, the user's decision, and the live transition — correlated by a single identifier.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can attach a supported file and receive an agent response that demonstrably uses its contents in a single chat turn, with no manual setup.
- **SC-002**: For the common accepted file categories (documents, spreadsheets, presentations, text/code, images), 100% are read by an existing parser without invoking the auto-creation path.
- **SC-003**: When a file of an accepted type has no existing parser, a working, self-tested parser is drafted on upload and presented for administrator approval without any human editing backend code, and on approval the file is read successfully and the capability is available to all users.
- **SC-004**: 100% of attachment reads are blocked when attempted by a user who does not own the attachment.
- **SC-005**: No auto-generated parser is ever executed against a user file without having passed the security gate and self-test and received explicit user approval (zero exceptions).
- **SC-006**: Every rejected upload (oversize, disallowed type, or content mismatch) is refused before the file is referenced in a message, with a message that tells the user why.
- **SC-007**: Re-uploading an unreadable file type while a draft for that type is still pending produces at most one capability-creation proposal.
- **SC-008**: Users can attach a previously uploaded file to a new chat without re-uploading, and a deleted attachment can no longer be attached or read.

## Assumptions

- **Existing upload foundation is reused**: the upload endpoint, user-scoped attachment storage, the accepted-type/size-limit definitions, content-type sniffing, and the existing per-category parser tools already exist (from the earlier file-uploads work) and are consumed by this feature rather than rebuilt.
- **Agentic-creation lifecycle is reused**: the auto-creation of a parser for an unsupported type reuses the established draft → security-gate → isolated self-test → approve/refine/discard → live lifecycle and its audit class, rather than introducing a new creation mechanism.
- **Server-driven UI only**: the attachment affordance is added within the server-driven UI / render layer; no React/Vite or other standalone client is introduced.
- **Accepted-type list is a broadened curated allowlist** (per clarification): the previously enumerated attachment types plus additional common document, data, archive, and code formats — curated, not an unbounded "any binary." An accepted type lacking a parser is what drives auto-creation.
- **Default per-message attachment count**: a tunable upper bound of **10 attachments per message** is applied to keep turns manageable.
- **Auto-creation trigger eligibility and parser scope** (per clarification): any authenticated user may trigger a draft eagerly on upload; an administrator must approve before it goes live; once approved the parser is a global fleet capability for all users. This reuses the existing agentic-creation security gate and self-test rather than loosening that posture.
- **Images and no-text documents** are routed to the existing visual-understanding path where appropriate.
- **Auth and fail-closed posture**: all attachment and capability-creation operations require an authenticated user and inherit the project's fail-closed security posture (unset environment defaults to the stricter production behavior).
