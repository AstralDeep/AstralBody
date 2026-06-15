---
description: "Task list for feature 031 — Chat Attachment Upload & Universal Parsing"
---

# Tasks: Chat Attachment Upload & Universal Parsing

**Input**: Design documents from `specs/031-attachment-upload-parsing/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (attachments-protocol.md, parser-autocreate.md), quickstart.md

**Tests**: INCLUDED — Constitution III/XI require ≥90% changed-code coverage; test tasks accompany each story.

**Organization**: Tasks grouped by user story (US1 P1 = MVP, US2 P2, US3 P3). Paths are backend-only (server-driven UI; no `frontend/` source of truth).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 / US2 / US3 (setup, foundational, polish have no story label)

## Path Conventions

Repo root `c:\Users\sear234\Desktop\Containers\MCP\AstralBody`. Backend under `backend/`. Tests under `backend/tests/`, `backend/agents/general/tests/`, `backend/orchestrator/tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Flag + scaffolding that later phases build on.

- [X] T001 Add feature flag `FF_ATTACHMENT_AUTOPARSE` (default `True`) to the `FeatureFlags` registry in `backend/shared/feature_flags.py`, following the existing `_read("FF_…", default)` idiom.
- [X] T002 [P] (Subsumed by T007) Broadened-allowlist additions implemented directly in `backend/orchestrator/attachments/content_type.py` as a localized Feature-031 block.
- [X] T003 [P] Create module `backend/orchestrator/attachment_autoparse.py` with module docstring + public function surface (`start`, `coverage_status`) referencing contracts/parser-autocreate.md (US2 fills the lifecycle wiring).

**Checkpoint**: Flag readable; edit sites exist.

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: Blocks ALL user stories. Migrations + coverage map + broadened allowlist are prerequisites for both attaching (US1) and gap detection (US2).

- [X] T004 Add idempotent guarded migrations to `backend/shared/database.py::_init_db()`: `CREATE TABLE IF NOT EXISTS message_attachment (...)` with its two indexes, per data-model.md.
- [X] T005 Add idempotent guarded migration to `_init_db()`: `CREATE TABLE IF NOT EXISTS attachment_parser (...)` with `uq_attachment_parser_gap` unique index + `idx_attachment_parser_status`, per data-model.md.
- [X] T006 Add guarded column migration to `_init_db()`: `draft_agents.source_attachment_id` via the existing `_column_exists()` guard, per data-model.md.
- [X] T007 [P] Broaden `ACCEPTED_EXTENSIONS`, add `data` and `archive` categories, and add their `MAX_BYTES_BY_CATEGORY` caps (100 MB each) in `backend/orchestrator/attachments/content_type.py`; map newly-added textual types to existing categories (text) and reserve `data`/`archive` for genuinely no-parser types. Also exports `AUTO_PARSE_CATEGORIES` and keeps every accepted ext in the sniff-consistency map.
- [X] T008 [P] Create `backend/orchestrator/parser_registry.py`: coverage map consulting the built-in category→tool map AND a `live` row in `attachment_parser`; exports `coverage()`/`is_covered()`/`covering_tool()`/`gap_fingerprint()`.
- [X] T009 [P] Add repositories: `backend/orchestrator/attachments/message_attachment_repo.py` (`insert`/`list_for_chat`/`list_for_message`) and `backend/orchestrator/attachments/parser_repo.py` (`AttachmentParserRepository` — dedup-safe `create_pending`, `mark_live`, `mark_status`, `get_by_gap`/`get_by_draft`, `list_by_status`), all ownership/format-scoped.

### Foundational tests

- [X] T010 [P] Test migration idempotency (run `_init_db` twice; assert tables/column exist, no error) in `backend/tests/attachments/test_migrations_031.py` (runs against the container Postgres; skips where DB unreachable).
- [X] T011 [P] Test broadened allowlist + new-category caps + sniff-map completeness in `backend/tests/attachments/test_content_type_broadened.py` — **47 assertions green locally**.
- [X] T012 [P] Test `parser_registry.coverage()` for builtin-covered, globally-covered (seeded `attachment_parser` live row), and uncovered types + `gap_fingerprint` stability in `backend/tests/attachments/test_parser_registry.py` — **green locally**.

**Checkpoint**: Schema + coverage map + broadened allowlist ready. User stories can begin.

---

## Phase 3: User Story 1 — Attach files in chat and have them understood (Priority: P1) 🎯 MVP

**Goal**: A paperclip control in the chat input lets a user attach broadly-typed files; the handling agent receives structured references and reads supported files with existing parsers.

**Independent Test**: Click paperclip, upload a PDF + CSV (chips show progress), send "summarize these", confirm the reply reflects file contents and the `chat_message` WS frame carried `payload.attachments[]`. A second user cannot reference the first's `attachment_id`.

### Implementation — server-rendered affordance

- [ ] T013 [US1] Add paperclip `<button class="astral-attach-btn">`, hidden `<input type="file" class="astral-file-upload" multiple>` (with broadened `accept`), and a `#astral-attachments` chips row inside `#astral-form` in `backend/webrender/templates/shell.html`.
- [ ] T014 [P] [US1] Add chip + paperclip styles (uploading/ready/failed states, remove control) in `backend/webrender/static/astral.css`.
- [ ] T015 [US1] In `backend/webrender/static/client.js`: on file pick → `POST /api/upload` per file (≤10), render a chip per file with state transitions and a remove control, track ready `attachment_id`s, show server rejection reasons inline; clear chips after send.
- [ ] T016 [US1] In `client.js` `sendChat`: include `payload.attachments = [{attachment_id, filename, category}]` on the `chat_message` event when chips are ready (per contracts/attachments-protocol.md §2); stop using the `"[Attachment: …]"` text hack for new sends.

### Implementation — server wiring & delivery to agent

- [ ] T017 [US1] In `backend/orchestrator/orchestrator.py` chat_message handling: parse `payload.attachments`, validate each `attachment_id` is live & owned by sender (drop foreign/invalid with a `file`-class audit + user-visible note), cap at 10.
- [ ] T018 [US1] In `orchestrator.py`: persist accepted attachments as `message_attachment` rows (via T009 repo) keyed to the chat/user message.
- [ ] T019 [US1] In `orchestrator.py` user-message assembly (~the messages-list build before `_call_llm`): inject the structured **"Attachments on this turn"** block (id/name/category/readable-tool) per contracts §2, replacing the legacy regex hack path for new turns (keep legacy regex tolerant for old transcripts).
- [ ] T020 [US1] In `orchestrator.py` `load_chat`/`chat_loaded`: re-hydrate `message_attachment` references so chips render in transcript history.

### Tests for User Story 1

- [ ] T021 [P] [US1] Integration test: `chat_message` with `attachments[]` → `message_attachment` rows inserted, structured block injected, a stub agent's `read_document`/`read_spreadsheet` receives the real `attachment_id` in `backend/tests/test_chat_attachments_wiring.py`.
- [ ] T022 [P] [US1] Test ownership: a foreign/deleted `attachment_id` is dropped + audited and never reaches a tool, in `backend/tests/test_chat_attachments_ownership.py`.
- [ ] T023 [P] [US1] Test per-message cap (>10 attachments rejected with a clear note) and `load_chat` re-hydration in `backend/tests/attachments/test_message_attachment_repo.py`.
- [ ] T023a [P] [US1] Test FR-010/FR-011: a supported-but-corrupt/protected file surfaces a clear, specific error and the turn continues (no silent empty result); a no-extractable-text PDF routes to the vision path (`read_document` `vision_required=true` returns page images) — in `backend/tests/test_chat_attachments_parse_failure.py`.

**Checkpoint**: US1 fully functional — attach + parse via existing tools, independently testable. **MVP deliverable.**

---

## Phase 4: User Story 2 — Upload a type no existing tool can read → safe auto-creation (Priority: P2)

**Goal**: Uploading an accepted but uncovered type eagerly drafts a parser (reusing 027's gate + self-test), surfaces a pending state to the uploader, requires **admin** approval, and on approval promotes the parser **globally** and re-parses the original file.

**Independent Test**: Upload `.parquet`/`.zip` → response `parser_status:"preparing"`; a draft is gated + self-tested against the file; re-upload → no second draft (dedup); non-admin approve → denied+audited; admin approve → parser global + original re-parsed + a different user sees `parser_status:"covered"`.

### Implementation — eager trigger + background creation

- [ ] T024 [US2] In `backend/orchestrator/attachments/router.py` `POST /api/upload`: after successful insert, call `parser_registry.coverage(...)`; if uncovered + `FF_ATTACHMENT_AUTOPARSE` on + no pending `attachment_parser` row → enqueue `attachment_autoparse.start(...)` (background `asyncio.create_task`); set `parser_status` in the 201 response (`covered|preparing|pending_admin_approval|unavailable`) per contracts/attachments-protocol.md §1.
- [ ] T025 [US2] Implement `attachment_autoparse.start(...)` in `backend/orchestrator/attachment_autoparse.py`: insert `attachment_parser` row `status='pending'` with format-scoped `gap_fingerprint`; `lifecycle.create_draft(...)` (agent `"<EXT> Parser"`, tool `parse_<ext>`, `origin='auto_attachment'`, `source_attachment_id`, `source_chat_id`); link `draft_agent_id`; emit `agent_lifecycle/gap_detected` (correlation_id=draft_id) per contracts/parser-autocreate.md.
- [ ] T026 [US2] In `attachment_autoparse.start(...)`: `generate_code` → `code_security.analyze` → `start_draft_agent` → self-test against the **uploaded file** (reuse `_self_test_draft` / VirtualWebSocket, 120 s, ≤1 auto-refine); persist `self_test`; emit `auto_created` + `self_test` audit; mark `attachment_parser.status` (`pending` on success, `failed` on irrecoverable gate/self-test failure).
- [ ] T027 [P] [US2] Add the **stdlib + already-installed packages only** constraint to the parser codegen prompt in `backend/orchestrator/agent_generator.py` (research.md R7): forbid assuming any pip install; instruct best-effort structural extraction (zip/XML for OOXML/epub/archives) + explicit limitation notice in output.
- [ ] T028 [US2] Notify the uploader: send the "preparing / pending admin approval / could not prepare a reader" status card to ALL of the user's sockets on `source_chat_id` (feature-028 fan-out) from `attachment_autoparse`.

### Implementation — admin-gated approval + global promotion

- [ ] T029 [US2] Admin-gate the draft-decision handlers for `auto_attachment` drafts in `backend/orchestrator/agentic_creation.py` (`_h_draft_approve`, `_h_draft_refine`, `_h_draft_discard`): require `"admin" in roles` server-side; audit non-admin attempts as `agent_lifecycle` `outcome=failure`; show "requires admin" to the uploader (FR-015, contracts §"Approval"). Mark the drafts chrome surface `ADMIN_ONLY` for this origin so `chrome_events.py` admin re-check also applies.
- [ ] T030 [US2] On admin approval of an `auto_attachment` draft: in the approval path (agentic_creation.py / agent_lifecycle.approve_agent caller) set system/public ownership (`agent_ownership.is_public=True`, not the uploading user's email) and enable the read scope so `parse_<ext>` is dispatchable by all users; update `attachment_parser` → `status='live'`, `live_agent_id`, `tool_name`, `approved_by`; emit `agent_lifecycle/approved` (FR-017, contracts §"Global promotion").
- [ ] T030a [US2] Constitution VII posture: ensure the promoted public parser agent registers with a valid `AGENT_API_KEY` and uses the standard RFC 8693 attenuated/delegated-scope agent auth (feature-028 fail-closed) — a promoted agent that cannot satisfy agent auth MUST NOT go live; cover in `backend/tests/chrome/test_autoparse_admin_approval.py`.
- [ ] T031 [US2] On approval, re-parse the originating attachment via `draft_agents.source_attachment_id` and deliver the result to the uploader's chat; on discard/failure deliver "could not read this type".
- [ ] T032 [US2] Dedup enforcement: `attachment_autoparse` checks `attachment_parser` (unique `gap_fingerprint`) + `find_gap_draft` before creating; a duplicate upload returns `pending_admin_approval` without a new draft (FR-018, SC-007).

### Tests for User Story 2

- [ ] T033 [P] [US2] Test eager trigger: uncovered upload enqueues autoparse and returns `parser_status:"preparing"`; covered upload returns `"covered"`; flag off returns `"unavailable"` — in `backend/tests/attachments/test_autoparse_trigger.py`.
- [ ] T034 [P] [US2] Test dedup: two uploads of the same uncovered type create exactly one `attachment_parser` row / one draft, in `backend/tests/attachments/test_autoparse_dedup.py`.
- [ ] T035 [P] [US2] Test admin gating: non-admin approve denied + audited; admin approve promotes global (`is_public=true`, `attachment_parser.status='live'`) — in `backend/tests/chrome/test_autoparse_admin_approval.py`.
- [ ] T036 [P] [US2] Test fail-closed: security-gate CRITICAL → `failed`/never live; self-test failure → not live; discard → no capability; each yields "cannot read this type yet" — in `backend/tests/attachments/test_autoparse_fail_closed.py`.
- [ ] T037 [P] [US2] Test re-parse on approval uses `source_attachment_id` and a second user then gets `parser_status:"covered"`, in `backend/tests/attachments/test_autoparse_global_reuse.py`.
- [ ] T038 [P] [US2] Test codegen constraint: generated parser passes `code_security.analyze` and imports only allowed modules (assert the prompt constraint is present + a fixture parser is gate-clean), in `backend/tests/attachments/test_autoparse_codegen_constraint.py`.

**Checkpoint**: US1 + US2 both work independently. Auto-creation is safe, admin-gated, global, deduped.

---

## Phase 5: User Story 3 — Reuse & manage previously uploaded attachments (Priority: P3)

**Goal**: Browse prior uploads, attach an existing file without re-uploading, delete attachments.

**Independent Test**: Upload in chat A; in chat B open the paperclip → Attachments library → attach existing (no duplicate blob) → send → agent reads it; delete one → it disappears and can no longer be attached/read.

### Implementation

- [ ] T039 [US3] Create chrome surface `backend/webrender/chrome/surfaces/attachments.py`: `TITLE="Attachments"`, `async render(orch, user_id, roles, params)` listing the user's live attachments (via repository) with attach/delete controls, plus `HANDLERS = {chrome_attach_existing, chrome_attachment_delete}` (ownership-checked) per contracts §4.
- [ ] T040 [US3] Register the surface in `backend/webrender/chrome/surfaces/__init__.py` `SURFACE_MODULES`.
- [ ] T041 [US3] In `client.js`: paperclip menu opens the Attachments library via `chrome_open`; `chrome_attach_existing` adds an existing `attachment_id` to the compose tray (chip) without re-upload; reflect deletes.
- [ ] T042 [US3] Ensure `chrome_attachment_delete` routes through the existing soft-delete (repository) so the deleted id can no longer be referenced (reuse, no new delete path).

### Tests for User Story 3

- [ ] T043 [P] [US3] Test surface render lists only the caller's live attachments; `chrome_attach_existing` references an existing id with no duplicate `user_attachments`/blob row, in `backend/tests/chrome/test_surface_attachments.py`.
- [ ] T044 [P] [US3] Test delete removes from list and a subsequent `chat_message` referencing the deleted id is refused, in `backend/tests/chrome/test_surface_attachments_delete.py`.

**Checkpoint**: All three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T045 [P] Add a feature-029-style section to `CLAUDE.md` summarizing feature 031 (attachment wiring, broadened allowlist, eager autoparse, admin-gated global parser promotion, new tables/flag).
- [ ] T046 [P] Update `/docs` reflection of changed REST behavior (upload `parser_status`) and ensure FastAPI endpoint docstrings are accurate.
- [ ] T047 Verify audit trail end-to-end: one parser lifecycle traceable by `correlation_id` (gap_detected→auto_created→self_test→approved/rejected); rejected upload / ownership-denial / parse-failure logged (FR-023/FR-024).
- [ ] T048 Run `ruff check .` from repo root and fix any lint; confirm render-layer JS is lint-clean.
- [ ] T049 Run both pytest invocations inside the `astralbody` container and confirm changed-code coverage ≥90% (Constitution III/XI): `tests/` default suite + module suites.
- [ ] T050 Execute `specs/031-attachment-upload-parsing/quickstart.md` against a real browser on `:8001` + live backend (US1/US2/US3 manual verification per Constitution X).

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (P1)**: no deps.
- **Foundational (P2)**: depends on Setup; **blocks all stories** (migrations + coverage map + broadened allowlist).
- **US1 (P3)**: depends on Foundational. MVP.
- **US2 (P4)**: depends on Foundational; logically builds on US1's delivery path but is independently testable (its trigger is the upload endpoint, not the chat turn).
- **US3 (P5)**: depends on Foundational; independent of US2.
- **Polish (P6)**: after desired stories complete.

### Within stories

- US1: shell/css/client (T013–T016) and server wiring (T017–T020) can proceed in parallel up to T021–T023 tests; T018 depends on T009 (repo); T019 depends on T017.
- US2: T024 depends on T008/T009 + T025/T026 module; T030/T031 depend on T029; T032 depends on T025.
- US3: T039 before T040/T041; T043/T044 after.

### Parallel opportunities

- Foundational `[P]`: T007, T008, T009 (+ tests T010–T012) run together (different files).
- US1 `[P]`: T014 (css) parallel to JS/server tasks; tests T021–T023 parallel.
- US2 `[P]`: T027 (codegen prompt) parallel to trigger/approval tasks; tests T033–T038 parallel.
- US3 `[P]`: tests T043–T044 parallel.

---

## Parallel Example: Foundational

```bash
# After T004–T006 migrations land, run together:
Task: "Broaden ACCEPTED_EXTENSIONS + new categories in attachments/content_type.py"   # T007
Task: "Create parser_registry.py coverage map"                                          # T008
Task: "Add message_attachment repository functions"                                     # T009
```

## Parallel Example: User Story 2 tests

```bash
Task: "test_autoparse_trigger.py"        # T033
Task: "test_autoparse_dedup.py"          # T034
Task: "test_autoparse_admin_approval.py" # T035
Task: "test_autoparse_fail_closed.py"    # T036
Task: "test_autoparse_global_reuse.py"   # T037
Task: "test_autoparse_codegen_constraint.py"  # T038
```

---

## Implementation Strategy

### MVP first (US1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (CRITICAL) → 3. Phase 3 US1 → **STOP & VALIDATE** attach+parse end-to-end in a real browser → demo.

### Incremental delivery

1. Setup + Foundational → foundation ready.
2. US1 → attach + parse with existing tools (MVP).
3. US2 → safe, admin-gated, global auto-creation for unknown types.
4. US3 → cross-chat reuse + management.
5. Polish → docs, audit verification, coverage, manual UX.

---

## Notes

- `[P]` = different files, no incomplete-task dependency.
- Every changed code path needs tests to hold the ≥90% changed-code coverage gate (Constitution III/XI).
- Fail-closed everywhere: an unapproved/failed parser yields "cannot read this type yet", never silent execution (FR-019, SC-005).
- No new third-party runtime dependency anywhere in this feature (Constitution V); auto-created parsers are stdlib/installed-only.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.
