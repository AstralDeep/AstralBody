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

- [X] T013 [US1] Add paperclip button, hidden multi-file `astral-file-upload` input (server-injected `accept` list via `%%ASTRAL_ACCEPT%%` from `ACCEPTED_EXTENSIONS`), and a `#astral-attachments` chips row inside `#astral-form` in `backend/webrender/templates/shell.html`; injection wired in `serve_shell`.
- [X] T014 [P] [US1] Add chip + paperclip styles (uploading/ready/failed states, remove control) in `backend/webrender/static/astral.css`.
- [X] T015 [US1] In `backend/webrender/static/client.js`: paperclip → file pick → `POST /api/upload` per file (≤10), chip per file with state transitions + remove control, server rejection reasons inline, parser_status hint on chip; clear chips after send.
- [X] T016 [US1] In `client.js` `sendChat`/submit: include `payload.attachments = [{attachment_id, filename, category}]` when chips are ready (and allow attachment-only sends); legacy `"[Attachment: …]"` text hack no longer emitted by new sends.

### Implementation — server wiring & delivery to agent

- [X] T017 [US1] In `orchestrator.py`: parse `payload.attachments`, thread through `_serialized_chat`/`_dispatch_async_chat`/`handle_chat_message`; new `_attach_turn_attachments` validates each id is live & owned (drops foreign/invalid with a `file`-class audit + user note), caps at 10, collapses dupes.
- [X] T018 [US1] `_attach_turn_attachments` persists accepted attachments as `message_attachment` rows keyed to the persisted user message (`turn_message_id`).
- [X] T019 [US1] `_attach_turn_attachments` injects the structured **"Attachments on this turn"** block (id/name/category/readable-tool via `parser_registry.coverage`) into the LLM-facing message; saved history text stays clean; attachments-only turns synthesize a minimal prompt.
- [X] T020 [US1] In `orchestrator.py` `load_chat`: re-hydrate `message_attachment` refs onto loaded user messages; `client.js` `chat_loaded` renders a 📎 chip line in history.

### Tests for User Story 1

- [X] T021 [P] [US1] Wiring test: `_attach_turn_attachments` links rows + injects the block naming the reader tool (read_document / pending parser), cap-of-10, dupe-collapse — `backend/tests/test_chat_attachments_wiring.py` (**green locally**).
- [X] T022 [P] [US1] Ownership test: a foreign/unknown `attachment_id` is dropped + user notified, never linked — `backend/tests/test_chat_attachments_ownership.py` (**green locally**).
- [X] T023 [P] [US1] Repo tests: `message_attachment` insert/list (ownership-scoped) + `attachment_parser` dedup-safe create/mark — `backend/tests/attachments/test_message_attachment_repo.py` (**green locally**).
- [X] T023a [P] [US1] FR-010/FR-011: corrupt/foreign file → structured error (no crash); no-text PDF → vision path — `backend/tests/agents/general/file_tools/test_parse_failure_031.py` (**green locally**). (Also discovered+fixed: `Attachment.category` Literal needed `data`/`archive` or uploads of new types would 500.)

**Checkpoint**: US1 fully functional — attach + parse via existing tools, independently testable. **MVP deliverable.**

---

## Phase 4: User Story 2 — Upload a type no existing tool can read → safe auto-creation (Priority: P2)

**Goal**: Uploading an accepted but uncovered type eagerly drafts a parser (reusing 027's gate + self-test), surfaces a pending state to the uploader, requires **admin** approval, and on approval promotes the parser **globally** and re-parses the original file.

**Independent Test**: Upload `.parquet`/`.zip` → response `parser_status:"preparing"`; a draft is gated + self-tested against the file; re-upload → no second draft (dedup); non-admin approve → denied+audited; admin approve → parser global + original re-parsed + a different user sees `parser_status:"covered"`.

### Implementation — eager trigger + background creation

- [X] T024 [US2] In `router.py` `POST /api/upload`: after insert, `attachment_autoparse.coverage_status(...)` sets `parser_status` (`covered|preparing|pending_admin_approval|unavailable`); `preparing` enqueues `attachment_autoparse.start(...)` via `asyncio.create_task` (background). Resolves orch via new `_get_orchestrator`.
- [X] T025 [US2] `attachment_autoparse.start(...)`: dedup-check registry → `lifecycle.create_draft` (agent `"<EXT> Parser"`, tool `parse_<ext>`, identifier-safe), `update_draft_agent(origin='auto_attachment', source_chat_id, gap_fingerprint, source_attachment_id)`, `parser_repo.create_pending`, emit `agent_lifecycle/gap_detected` (correlation_id=draft_id).
- [X] T026 [US2] `start(...)`: `generate_code` → `start_draft_agent` → self-test against the **uploaded file** (reuses `_self_test_draft`, now with an `attachments=` param, ≤1 auto-refine); persists `self_test`; emits `auto_created` + `self_test`; marks registry `failed` on hard generation failure (else stays `pending` for admin).
- [X] T027 [P] [US2] Added the **stdlib + already-installed packages only** + best-effort-extraction constraint to the codegen SECURITY RULES in `agent_generator.py` (benefits all generated agents; the security gate already blocks the shell/install escape hatch).
- [X] T028 [US2] `_notify_user` fans a status toast ("preparing / pending admin approval / could not prepare a reader" and, on go-live, "reader is live") to all of the user's connected sockets (upload is chat-agnostic, so no single chat_id).

### Implementation — admin-gated approval + global promotion

- [X] T029 [US2] Admin-gated `_h_draft_approve` for `auto_attachment` drafts (`"admin" in roles` required, non-admin audited + refused; uploader cannot self-approve); `_h_draft_refine`/`_h_draft_discard` use `_decidable_draft` (owner OR admin-on-autoparse). Discard marks the registry row `discarded` (re-attemptable).
- [X] T030 [US2] `_promote_parser_global` on admin go-live: `set_agent_visibility(agent_id, True)` (public/global), enable the parser's read scopes for the originating user, `attachment_parser.mark_live(live_agent_id, tool_name, approved_by)`; emit `agent_lifecycle/approved`. Fleet-wide availability rides the existing public-catalog consent path (030).
- [X] T030a [US2] Constitution VII posture: promotion goes through the existing `approve_agent` path, which already only promotes when the agent subprocess actually starts (registered agent-auth posture preserved) — a parser that can't come up is NOT promoted. Admin-gate covered in `tests/chrome/test_autoparse_admin_approval.py`.
- [~] T031 [US2] On go-live the originating user is notified the reader is live ("ask again to read your file"), their read scope enabled so it works immediately. NOTE: full *automatic* re-parse-and-deliver is simplified to a notify (admin approves out of the uploader's chat context); the parser is live + scoped so the next ask parses the file. **Follow-up: auto-continue the original turn.**
- [X] T032 [US2] Dedup: `start(...)` and `coverage_status(...)` consult `attachment_parser` (unique `gap_fingerprint`); a pending/live row returns `pending_admin_approval`/`covered` and creates no new draft (FR-018, SC-007).

### Tests for User Story 2

- [X] T033 [P] [US2] `coverage_status` states (covered/preparing/pending/unavailable/flag-off/reattempt) + identifier-safe tool name — `backend/tests/attachments/test_autoparse_coverage.py` (**green locally**).
- [X] T034 [P] [US2] Dedup verified at registry + `coverage_status` (pending row → `pending_admin_approval`, no new draft) — covered by `test_message_attachment_repo.py` + `test_autoparse_coverage.py` (**green**).
- [X] T035 [P] [US2] Admin gating: non-admin approve refused (approve_agent never called); admin passes the gate; normal drafts still owner-gated — `backend/tests/chrome/test_autoparse_admin_approval.py` (**green locally**).
- [X] T036 [P] [US2] Fail-closed: security gate blocks subprocess/`os.system` (CRITICAL) and stdlib-only parser passes — `backend/tests/attachments/test_autoparse_security_gate.py` (**green**). (Flag-off → `unavailable` in T033.)
- [X] T037 [P] [US2] Global reuse: a `live` registry row makes `coverage_status` return `covered` for any user — `test_autoparse_coverage.py::test_live_registry_row_reports_covered` (**green**).
- [X] T038 [P] [US2] Codegen constraint present in `agent_generator` + the gate is the enforcement — `backend/tests/attachments/test_autoparse_security_gate.py` (**green**).

**Checkpoint**: US1 + US2 both work. Auto-creation is eager, safe, admin-gated, global-by-registry, deduped. (T031 re-parse simplified to notify — tracked follow-up.)

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
