---

description: "Task list for feature 002-file-uploads"
---

# Tasks: Common File Type Uploads in Chat UI

**Input**: Design documents from `/specs/002-file-uploads/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/upload-api.md, contracts/agent-tools.md, quickstart.md

**Tests**: REQUIRED. Constitution III mandates unit + integration tests at ≥90% coverage on changed code; tests precede the code they cover.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- File paths are absolute repo-root-relative

## Path Conventions

Web app per plan.md: `backend/` (FastAPI) + `frontend/` (Vite/React/TS).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, dependencies, container image.

- [X] T001 Add new Python deps to `backend/pyproject.toml` (or `requirements.txt`): `pypdf`, `python-docx`, `python-pptx`, `odfpy`, `striprtf`, `xlrd`, `Pillow`, `pytesseract`, `pdf2image`, `defusedxml`, `python-magic`. Include lead-developer approval line in PR description per Constitution V.
- [X] T002 Update `backend/Dockerfile` to install system packages `tesseract-ocr`, `poppler-utils`, `libmagic1` and verify the image still builds.
- [X] T003 [P] Add a single shared accepted-extension + 30 MB constants module at `frontend/src/lib/attachmentTypes.ts` (extension list per spec FR-001, MIME map, `MAX_FILE_BYTES = 31_457_280`).
- [X] T004 [P] Add the matching server-side allow-list and category mapping at `backend/orchestrator/attachments/content_type.py` (extension → category enum, plus a `python-magic` sniffer helper that asserts the content type is consistent with the extension).
- [X] T005 [P] Verify/extend `.gitignore` and `.dockerignore` to exclude `backend/tmp/` upload artifacts and `backend/tests/agents/general/file_tools/fixtures/.cache/` if any are produced during tests.

**Checkpoint**: Deps installed, image builds, shared constants in place.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Storage, persistence, auth-aware REST surface that every user story builds on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T006 Create the `user_attachments` table migration at `backend/migrations/0002_user_attachments.sql` with columns per `data-model.md` Attachment entity (`attachment_id` UUID PK, `user_id`, `filename`, `content_type`, `category`, `extension`, `size_bytes`, `sha256`, `storage_path`, `created_at`, `deleted_at`) and indices on (`user_id`, `created_at DESC`) and `attachment_id`.
- [X] T007 [P] Implement `Attachment` and `AttachmentRef` Pydantic models in `backend/orchestrator/attachments/models.py`.
- [X] T008 [P] Implement filesystem layout module `backend/orchestrator/attachments/store.py` with `write(user_id, attachment_id, filename, byte_iter) -> Path`, `read_path(attachment) -> Path`, and `delete(attachment) -> None` (best-effort blob removal). Storage root configurable via env, default `backend/tmp/`.
- [X] T009 [P] Implement repository module `backend/orchestrator/attachments/repository.py` with `insert`, `get_by_id`, `list_for_user(user_id, category=None, limit, cursor)`, and `soft_delete(attachment_id, user_id)`. Soft delete sets `deleted_at`; live queries filter `deleted_at IS NULL`.
- [X] T010 [US-foundation] Write integration test `backend/tests/attachments/test_store.py` exercising write/read/delete round-trip against a temp directory, including filename collision safety (same name, different attachment_id).
- [X] T011 [P] Write integration test `backend/tests/attachments/test_repository.py` covering insert/list/get/soft-delete with a sqlite-backed test DB and assert ownership filter (`user_id` mismatch returns nothing).
- [X] T012 Modify `POST /api/upload` in `backend/orchestrator/auth.py` to: accept the FR-001 extension set; enforce 30 MB via streamed read returning HTTP 413; sniff content-type via `content_type.py` and return HTTP 415 on mismatch; store under `{user_id}/{attachment_id}/{filename}`; insert a `user_attachments` row; return the response shape from `contracts/upload-api.md` (201 with `attachment_id`, `category`, `sha256`, etc.). Path traversal sanitization unchanged.
- [X] T013 Add new attachment endpoints to `backend/orchestrator/api.py`: `GET /api/attachments`, `GET /api/attachments/{attachment_id}`, `DELETE /api/attachments/{attachment_id}`. All require `Depends(require_user_id)`. Non-owner reads return `404` (not `403`) per contract.
- [X] T014 Write contract test `backend/tests/attachments/test_upload_endpoint.py` covering: happy path for one file per category, oversize → 413, unsupported extension → 415, mislabeled extension (e.g., `.exe` renamed `.pdf`) → 415, missing token → 401, ownership isolation across two test users.
- [X] T015 [P] Write contract test `backend/tests/attachments/test_attachments_endpoint.py` for list/get/delete behavior, including pagination cursor and that deleted attachments disappear from list and become 404 on GET.
- [X] T016 [P] Hook account-deletion in the existing user-management module to call `repository.soft_delete` for every Attachment owned by the deleted user and `shutil.rmtree` the user's blob directory. Add unit test in `backend/tests/attachments/test_account_deletion.py`.

**Checkpoint**: Foundation ready — agent file tools and frontend chip work can now begin.

---

## Phase 3: User Story 1 - Attach a document for the agent to analyze (Priority: P1) 🎯 MVP

**Goal**: From any chat, a user picks one file (any FR-001 type), sends a message, and the AstralBody general agent demonstrably reads the file's contents and replies. Files are user-scoped and visible inline in any of the user's chats.

**Independent Test**: Per `quickstart.md` step 5 — attach one PDF, send "summarize this", confirm the reply quotes content only present in the PDF. Repeat for one DOCX, one XLSX, one PNG, one `.py`.

### Tests for User Story 1

- [X] T017 [P] [US1] Create test fixtures (one minimal sample per supported extension, ≤ 50 KB each) under `backend/tests/agents/general/file_tools/fixtures/`. Include a text-bearing PDF, a scanned/image-only PDF, a DOCX, an RTF, an ODT, an XLSX, an XLS, an ODS, a TSV, a PPTX, an ODP, a JSON, a YAML, an XML, an HTML, a `.py`, a PNG, a JPG, a WEBP.
- [X] T018 [P] [US1] Write `backend/tests/agents/general/file_tools/test_read_document.py` covering PDF text extraction, OCR fallback path on the scanned-PDF fixture, vision fallback when OCR yields nothing (assert `images` populated), DOCX/RTF/ODT text extraction, `not_found` on foreign `attachment_id`, `unreadable_file` on truncated bytes.
- [X] T019 [P] [US1] Write `backend/tests/agents/general/file_tools/test_read_spreadsheet.py` covering XLSX (multi-sheet `sheet_names`), XLS, ODS, TSV, CSV, default-first-sheet behavior, `max_rows` truncation flag, ownership rejection.
- [X] T020 [P] [US1] Write `backend/tests/agents/general/file_tools/test_read_presentation.py` covering PPTX + ODP slide text and speaker notes, and that legacy `.ppt` is rejected at upload time (verifies the upload rule, not the tool).
- [X] T021 [P] [US1] Write `backend/tests/agents/general/file_tools/test_read_text.py` covering UTF-8 text, charset fallback on a non-UTF-8 fixture, JSON/YAML/XML/HTML parsing (XML via `defusedxml`), `max_chars` truncation, ownership rejection.
- [X] T022 [P] [US1] Write `backend/tests/agents/general/file_tools/test_read_image.py` covering PNG/JPG/WEBP normalization (`Pillow`), max-dimension cap (2048 px), base64 envelope shape, ownership rejection.
- [X] T023 [P] [US1] Write `backend/tests/agents/general/file_tools/test_ocr_fallback.py` exercising the shared OCR helper against the scanned-PDF fixture and an image-only PDF that yields no OCR text (assert vision-fallback path).
- [X] T024 [P] [US1] Write `frontend/src/test/useAttachments.test.ts` covering: select-and-upload flow calling `/api/upload`, oversize rejection (no network call), unsupported-extension rejection, removing a pending attachment, listing user attachments via `/api/attachments`.
- [X] T025 [P] [US1] Write `frontend/src/test/ChatInterface.attachments.test.tsx` covering the paperclip click → file picker `accept` includes the FR-001 extensions, single-attachment chip rendering with filename + category icon, and that sending a message includes the `attachment_id` in the outbound payload.
- [X] T026 [P] [US1] Write `frontend/src/test/AttachmentLibrary.test.tsx` covering: listing the user's uploaded files, attaching from the library into the current chat, and that another user's files never appear (mocked auth context).

### Implementation for User Story 1

- [X] T027 [P] [US1] Implement shared dispatcher helper at `backend/agents/general/file_tools/__init__.py` that resolves `attachment_id` → `Attachment`, enforces user ownership, re-sniffs content type, and returns either `(Attachment, blob_path)` or a structured error.
- [X] T028 [P] [US1] Implement OCR helper at `backend/agents/general/file_tools/ocr.py` (rasterize via `pdf2image`, OCR via `pytesseract`, returns `(text, page_images)` so callers can choose the vision-fallback path).
- [X] T029 [US1] Implement `backend/agents/general/file_tools/read_document.py` per `contracts/agent-tools.md`. PDF flow: `pypdf` → if extracted length below threshold, OCR → if still empty, return base64 page images in `images`. DOCX via `python-docx`, RTF via `striprtf`, ODT via `odfpy`. (Depends on T027, T028.)
- [X] T030 [P] [US1] Implement `backend/agents/general/file_tools/read_spreadsheet.py`: XLSX via `openpyxl`, XLS via `xlrd`, ODS via `odfpy`, TSV/CSV via stdlib `csv`. Returns `columns`, `rows`, `sheet_names`, `truncated`. (Depends on T027.)
- [X] T031 [P] [US1] Implement `backend/agents/general/file_tools/read_presentation.py` (PPTX via `python-pptx`, ODP via `odfpy`). (Depends on T027.)
- [X] T032 [P] [US1] Implement `backend/agents/general/file_tools/read_text.py` (UTF-8 + charset fallback; HTML via stdlib `html.parser`, XML via `defusedxml`; YAML/JSON returned as raw text). (Depends on T027.)
- [X] T033 [P] [US1] Implement `backend/agents/general/file_tools/read_image.py` (Pillow decode, resize ≤ 2048 px, re-encode PNG/JPEG, base64). (Depends on T027.)
- [X] T034 [US1] Register the six new tools in `TOOL_REGISTRY` inside `backend/agents/general/mcp_tools.py`: `read_document`, `read_spreadsheet`, `read_presentation`, `read_text`, `read_image`, `list_attachments`. Each entry includes `function`, `scope`, `description`, and `input_schema` exactly as in `contracts/agent-tools.md`. Also add a `list_attachments` thin wrapper around the repository's `list_for_user`. (Depends on T029–T033.)
- [X] T035 [P] [US1] Implement `frontend/src/hooks/useAttachments.ts`: state for pending attachments, `upload(file)` calling `/api/upload`, `remove(attachment_id)`, `listLibrary()` calling `/api/attachments`, error states for size/type/network failures.
- [X] T036 [US1] Modify `frontend/src/components/ChatInterface.tsx` paperclip `accept` to use the shared list from `attachmentTypes.ts`, render attachment chips from `useAttachments`, and include the resulting `attachment_id`(s) in the outbound message payload (replace today's inline `<10 KB` text-injection path with a uniform attachment-ref path). (Depends on T035, T013.)
- [X] T037 [US1] Implement `frontend/src/components/AttachmentLibrary.tsx`: a panel listing the current user's attachments grouped by category, with "attach to current chat" and "delete" actions. Wired into the chat shell so it is visible from any chat. (Depends on T035, T013.)
- [X] T038 [US1] Render historical-message attachment chips in a "no longer available" greyed state when the underlying Attachment has `deleted_at` set (per data-model.md AttachmentRef). Update message-rendering code in `ChatInterface.tsx`.
- [X] T039 [US1] Run the full test suite for this story and confirm `pytest --cov` reports ≥ 90% coverage on `backend/orchestrator/attachments/` and `backend/agents/general/file_tools/` per Constitution III.

**Checkpoint**: User Story 1 is independently functional — single-file attach across all categories works end-to-end and is visible cross-chat.

---

## Phase 4: User Story 2 - Attach multiple files in one turn (Priority: P2)

**Goal**: A user attaches more than one file before sending a single message; all attachments are sent together with no per-message cap (per the FR-004 + clarification).

**Independent Test**: Attach two files of different types in one message; confirm both `attachment_id`s travel in the outbound payload and the agent's reply references both files.

### Tests for User Story 2

- [X] T040 [P] [US2] Extend `frontend/src/test/ChatInterface.attachments.test.tsx` with a multi-attach scenario: select two files via the picker, both render as chips, removing one leaves the other, sending posts both refs.
- [X] T041 [P] [US2] Add backend integration test in `backend/tests/attachments/test_message_with_multiple_attachments.py` confirming a chat-message payload carrying multiple `attachment_id`s is accepted and routed to the agent with both refs intact.

### Implementation for User Story 2

- [X] T042 [US2] Extend `useAttachments` (`frontend/src/hooks/useAttachments.ts`) to manage a list rather than a single pending attachment, with stable `id` keys for chip removal. (Depends on T035.)
- [X] T043 [US2] Update the paperclip `<input type="file">` in `ChatInterface.tsx` with `multiple` and adjust the chip list to render N items in a wrapping row that stays usable when the count is large (no fixed cap). (Depends on T036, T042.)
- [X] T044 [US2] Update the message send path in `ChatInterface.tsx` to serialize all pending `attachment_id`s into the outbound message and clear the pending list on success. (Depends on T043.)

**Checkpoint**: Multi-file attach works in a single message.

---

## Phase 5: User Story 3 - Drag and drop a file onto the chat (Priority: P2)

**Goal**: Dragging any FR-001 file (or several) onto the chat window attaches them with the same validation as the picker.

**Independent Test**: Drag a PDF, drag a PNG, drag an unsupported `.dwg`. First two attach; third produces a clear rejection.

### Tests for User Story 3

- [X] T045 [P] [US3] Add tests in `frontend/src/test/ChatInterface.attachments.test.tsx` simulating drag-over → drop events for (a) a single supported file, (b) multiple supported files, (c) one supported + one unsupported (mixed batch — supported attaches, unsupported is rejected with a named message).

### Implementation for User Story 3

- [X] T046 [US3] Update `handleDragOver`/`handleDragLeave`/`handleDrop` in `ChatInterface.tsx` to route every dropped file through the same `useAttachments.upload` path used by the picker, applying the shared accept-list from `attachmentTypes.ts`. Mixed batches process valid files and surface a per-file rejection message for invalid ones. (Depends on T042.)

**Checkpoint**: Drag-drop reaches feature parity with the picker.

---

## Phase 6: User Story 4 - Clear feedback when an upload is rejected (Priority: P3)

**Goal**: Rejection messages name the file, state the reason, preserve other composer state, and offer retry on transient failures.

**Independent Test**: Per `quickstart.md` negative-path checks — oversize file, unsupported extension, mid-upload network failure (mocked).

### Tests for User Story 4

- [X] T047 [P] [US4] Add tests in `frontend/src/test/useAttachments.test.ts` for: oversize rejection message includes filename + size + 30 MB limit; unsupported-extension rejection lists supported categories; simulated mid-upload failure surfaces a retry control and preserves typed text + other valid pending attachments.

### Implementation for User Story 4

- [X] T048 [US4] Add a typed `AttachmentError` discriminator in `frontend/src/lib/attachmentTypes.ts` covering `oversize`, `unsupported`, `mismatch`, `network` cases.
- [X] T049 [US4] Update `useAttachments` (`frontend/src/hooks/useAttachments.ts`) to expose `errors` per attachment slot and a `retry(attachment_local_id)` method that re-runs the failed upload without disturbing other state. (Depends on T048.)
- [X] T050 [US4] Update the chip rendering in `ChatInterface.tsx` to show error chips with reason text and a "Retry" affordance for `network` errors; ensure typed message text is never lost when an attachment is rejected. (Depends on T049.)

**Checkpoint**: All four user stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T051 [P] Add Google-style docstrings to every new public function in `backend/orchestrator/attachments/` and `backend/agents/general/file_tools/` per Constitution VI.
- [X] T052 [P] Add JSDoc to every exported symbol in `frontend/src/hooks/useAttachments.ts`, `frontend/src/lib/attachmentTypes.ts`, and `frontend/src/components/AttachmentLibrary.tsx` per Constitution VI.
- [X] T053 [P] Confirm `/docs` (FastAPI Swagger) renders the modified `POST /api/upload` and the three new `/api/attachments*` endpoints with their request/response schemas; no manual doc file is required.
- [X] T054 [P] Run `ruff` / `flake8` and `eslint` and resolve any new findings; verify CI lint job passes (Constitution IV).
- [X] T055 Run `pytest --cov` across `backend/tests/attachments/` and `backend/tests/agents/general/file_tools/` with `--cov-fail-under=90` and `npm test` for the new frontend specs; confirm both gates are green (Constitution III).
- [X] T056 Execute the `quickstart.md` validation matrix end-to-end against a running dev environment and record results in the PR description.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational. Required for MVP.
- **User Story 2 (Phase 4)**: Depends on Foundational; integrates with US1 chip code but is independently testable.
- **User Story 3 (Phase 5)**: Depends on Foundational and on US2's multi-file `useAttachments` (T042) for mixed-batch drops. Sequencing US3 after US2 keeps `useAttachments` evolution clean.
- **User Story 4 (Phase 6)**: Depends on Foundational and the existing chip rendering from US1.
- **Polish (Phase 7)**: Depends on all four user stories being complete.

### Within Each User Story

- Tests written and FAILING before the implementation tasks they cover.
- Models / store / repository before endpoints.
- Endpoints before frontend integration.
- Tool implementations before `TOOL_REGISTRY` registration.

### Parallel Opportunities

- Setup: T003, T004, T005 in parallel.
- Foundational: T007, T008, T009 in parallel; tests T011 and T015 in parallel; T016 (account deletion) parallel to T012/T013.
- US1 tests T017–T026 all in parallel (different files / fixtures).
- US1 tool implementations T030, T031, T032, T033 in parallel after T027 lands; T029 sequential because it depends on T028.

---

## Parallel Example: User Story 1 implementation wave

```bash
# After T027 (dispatcher) and T028 (OCR helper) land, launch in parallel:
Task: "Implement read_document.py"          # T029 (waits for T028)
Task: "Implement read_spreadsheet.py"       # T030 [P]
Task: "Implement read_presentation.py"      # T031 [P]
Task: "Implement read_text.py"              # T032 [P]
Task: "Implement read_image.py"             # T033 [P]
Task: "Implement useAttachments hook"       # T035 [P] (frontend, fully independent)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (US1).
2. **STOP and VALIDATE**: Run `quickstart.md` step 5 for one file per category.
3. Demo / merge MVP.

### Incremental Delivery

1. MVP (US1) shipped → users can attach one file of any supported type per message and reuse it across chats.
2. Add US2 (multi-file) → ship.
3. Add US3 (drag-drop parity) → ship.
4. Add US4 (rejection UX polish) → ship.
5. Polish phase last.

### Parallel Team Strategy

- One developer owns Phase 1+2 (storage/REST).
- After Foundational checkpoint:
  - Backend developer takes US1 file_tools (T027–T034) and US1 backend tests.
  - Frontend developer takes US1 hooks/components (T035–T038) and US1 frontend tests.
  - US2/US3/US4 split between frontend + backend developers as capacity allows; their backend coupling is small.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in the same phase.
- Every task lists an absolute repo-relative file path so it can be executed without further clarification.
- Constitution V (dependency approval) is satisfied at PR-review time; T001 is the placeholder where the approval line is recorded.
- The plan's storage-layout migration (`{user_id}/{session_id}/` → `{user_id}/{attachment_id}/`) is delivered atomically by T012; no production data migration is required because today's uploads are treated as transient session blobs (see quickstart.md Rollout notes).
