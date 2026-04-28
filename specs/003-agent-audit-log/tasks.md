---

description: "Task list for feature 003-agent-audit-log"
---

# Tasks: Agent & User Action Audit Log

**Input**: Design documents from [specs/003-agent-audit-log/](.)
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: INCLUDED — required by Constitution Principle III (≥90% coverage; unit + integration). Specific test obligations are also enumerated in the contracts and in plan.md's Project Structure.

**Organization**: Tasks are grouped by user story so each story can be implemented, tested, and demoed independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story tag (US1 / US2 / US3) — only on user-story-phase tasks
- File paths are absolute-from-repo-root and exact

## Path Conventions (Web app — `backend/` + `frontend/`)

- Backend module: [backend/audit/](backend/audit/)
- Backend tests: [backend/tests/unit/audit/](backend/tests/unit/audit/), [backend/tests/integration/audit/](backend/tests/integration/audit/), [backend/tests/contract/audit/](backend/tests/contract/audit/)
- Frontend route: [frontend/src/pages/AuditLogPage.tsx](frontend/src/pages/AuditLogPage.tsx)
- Frontend components: [frontend/src/components/audit/](frontend/src/components/audit/)
- Frontend tests: [frontend/tests/audit/](frontend/tests/audit/)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new module directories and tooling configuration so subsequent tasks have somewhere to land.

- [x] T001 Create backend module skeleton: empty `__init__.py` files at [backend/audit/__init__.py](backend/audit/__init__.py), [backend/tests/unit/audit/__init__.py](backend/tests/unit/audit/__init__.py), [backend/tests/integration/audit/__init__.py](backend/tests/integration/audit/__init__.py), [backend/tests/contract/audit/__init__.py](backend/tests/contract/audit/__init__.py)
- [x] T002 [P] Create frontend folder skeleton: empty index files at [frontend/src/components/audit/index.ts](frontend/src/components/audit/index.ts) and [frontend/tests/audit/.gitkeep](frontend/tests/audit/.gitkeep)
- [x] T003 [P] Add a ruff custom rule (or a unit test under [backend/tests/unit/audit/test_no_raw_sha.py](backend/tests/unit/audit/test_no_raw_sha.py)) that fails CI if `hashlib.sha256` is called on payload-shaped values inside `backend/audit/` (FR-016 enforcement aid)
- [x] T004 [P] Register `AUDIT_HMAC_SECRET` and `AUDIT_HMAC_KEY_ID` in the backend's existing settings/env loader (no new dependency); document the dev default in [backend/audit/__init__.py](backend/audit/__init__.py) module docstring

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Substrate that every user story relies on — the table, the recorder, the schemas, and the WS protocol extension. **No user-story work begins until this phase is complete.**

- [x] T005 Write Alembic migration creating `audit_events` per [data-model.md](./data-model.md): partitioned table, monthly partitions for the next 24 months, indices, `audit_events_no_update` trigger, role grants — file [backend/alembic/versions/](backend/alembic/versions/) (new file `XXXX_create_audit_events.py`)
- [x] T006 Implement SQLAlchemy `AuditEvent` model in [backend/audit/models.py](backend/audit/models.py) matching the data-model.md columns; mark `__table_args__` as read-only-friendly; expose typed enums for `event_class` and `outcome`
- [x] T007 [P] Implement PII helpers in [backend/audit/pii.py](backend/audit/pii.py): `normalize_extension(name) -> str | None`, `hmac_digest(value: bytes, key_id: str) -> tuple[bytes, str]` (returns digest + key_id), `strip_filename(metadata: dict) -> dict`. No raw `sha256` of payloads anywhere
- [x] T008 [P] Implement Pydantic schemas in [backend/audit/schemas.py](backend/audit/schemas.py): `AuditEventCreate` (write-side, with `inputs_meta` / `outputs_meta` validators that reject payload-shaped fields and enforce ≤4 KiB serialized size), `AuditEventDTO` (read-side, matching [contracts/audit-event-schema.json](./contracts/audit-event-schema.json)), `ArtifactPointer`
- [x] T009 Implement `AuditRepository` in [backend/audit/repository.py](backend/audit/repository.py): `insert(event)` runs in serializable txn, selects the user's most recent `entry_hash` `FOR UPDATE`, computes new `prev_hash` + HMAC `entry_hash` (per research.md §R3/§R4), inserts under `app_audit_role`; `list_for_user(user_id, filters, cursor, limit)` and `get_for_user(user_id, event_id)` queries; `verify_chain(user_id)` walker for the operator CLI (no API surface)
- [x] T010 Implement `Recorder` in [backend/audit/recorder.py](backend/audit/recorder.py): public `record(...)` API that handlers call; transactional-outbox path when a session is provided, otherwise synchronous-best-effort with a disk-backed retry queue at `backend/audit/retry_queue/` (per research.md §R9). Recording must never raise into the caller on success of the underlying action
- [x] T011 [P] Add the `audit_append` server→client message type to [backend/shared/protocol.py](backend/shared/protocol.py); include the `AuditEventDTO` shape; mirror the change in any TypeScript protocol type at [frontend/src/types/protocol.ts](frontend/src/types/protocol.ts) if such a file exists, else create [frontend/src/types/audit.ts](frontend/src/types/audit.ts) with the DTO type
- [x] T012 [P] Extend [frontend/src/hooks/useWebSocket.ts](frontend/src/hooks/useWebSocket.ts) to recognize incoming `audit_append` messages and dispatch them to subscribers via a typed event emitter — no business logic here, just routing
- [x] T013 [P] Unit tests for PII helpers in [backend/tests/unit/audit/test_pii.py](backend/tests/unit/audit/test_pii.py): extension normalization, filename stripping, HMAC determinism with the same key_id, HMAC inequality across key_ids
- [x] T014 [P] Unit tests for hash-chain insert in [backend/tests/unit/audit/test_repository_hash_chain.py](backend/tests/unit/audit/test_repository_hash_chain.py): genesis row, second row links to genesis, concurrent inserts under FOR UPDATE never produce sibling chain heads, `verify_chain` returns OK on a clean log
- [x] T015 [P] Unit tests for `Recorder` in [backend/tests/unit/audit/test_recorder.py](backend/tests/unit/audit/test_recorder.py): transactional path commits with the outer txn; non-txn path retries from the disk queue after a simulated DB hiccup; recording never raises on the caller's happy path

**Checkpoint**: Foundation ready — table, integrity, recorder, and protocol extension all wired. User-story phases can begin.

---

## Phase 3: User Story 1 — View Audit Log (Priority: P1) 🎯 MVP

**Goal**: A user opens `/audit` and sees a chronological list of every user-attributable action the system has recorded for them, including agent actions performed on their behalf, with live updates while the route is open.

**Independent Test**: Start the backend, log in as `dev-user-id`, trigger an agent tool call from a chat, navigate to `/audit`, confirm the entry appears within 5 s without manual refresh; confirm a second user logged in concurrently never sees the first user's entries.

### Tests for User Story 1 ⚠️ (write FIRST, ensure they FAIL before implementation)

- [x] T016 [P] [US1] Contract test for `GET /api/audit` in [backend/tests/contract/audit/test_rest_contract.py](backend/tests/contract/audit/test_rest_contract.py) covering all six obligations in [contracts/rest-audit-api.md](./contracts/rest-audit-api.md) §"Test obligations"
- [x] T017 [P] [US1] Integration test for admin-blindness in [backend/tests/integration/audit/test_admin_blindness.py](backend/tests/integration/audit/test_admin_blindness.py): seed alice + bob events, hit `GET /api/audit` and `GET /api/audit/{bob's id}` with the highest privileged token in the role catalog, assert FR-019 holds at REST and at WS
- [x] T018 [P] [US1] Integration test for recording coverage in [backend/tests/integration/audit/test_recording_coverage.py](backend/tests/integration/audit/test_recording_coverage.py): exercise every authority boundary in research.md §R10, assert each emits an audit row
- [x] T019 [P] [US1] Integration test for WS live push in [backend/tests/integration/audit/test_ws_live_push.py](backend/tests/integration/audit/test_ws_live_push.py): two users connected to the same process; insert event for user A; assert A's connection receives `audit_append`; assert B's connection does not
- [x] T020 [P] [US1] Integration test for tamper detection in [backend/tests/integration/audit/test_tamper_detection.py](backend/tests/integration/audit/test_tamper_detection.py): clean log verifies OK; manually mutate a row's `description` (bypass via direct DB) and assert `verify_chain` flags the offending `event_id`
- [x] T021 [P] [US1] Frontend integration test in [frontend/tests/audit/AuditLogPage.test.tsx](frontend/tests/audit/AuditLogPage.test.tsx): renders entries from a mocked REST response, applies a mocked `audit_append` event and shows it without remounting, shows the empty state when the response is empty

### Implementation for User Story 1

- [x] T022 [US1] Implement REST list endpoint in [backend/audit/api.py](backend/audit/api.py): `GET /api/audit` per [contracts/rest-audit-api.md](./contracts/rest-audit-api.md); `actor_user_id` derived solely from the JWT; rejects `actor_user_id` / `user_id` query params with 400; cursor pagination over `(recorded_at DESC, event_id DESC)` (depends on T009)
- [x] T023 [US1] Mount the audit router on the existing FastAPI app in [backend/orchestrator/api.py](backend/orchestrator/api.py); confirm it appears under `/docs` (Constitution VI)
- [x] T024 [P] [US1] Implement HTTP recording middleware in [backend/audit/middleware.py](backend/audit/middleware.py): records every authenticated request (method, route template, status, request id, latency); skip the `/api/audit` GETs themselves to avoid feedback (those produce a dedicated `audit_view` event in T029)
- [x] T025 [US1] Wire the middleware in [backend/orchestrator/api.py](backend/orchestrator/api.py) after authentication
- [x] T026 [P] [US1] Implement WS message-handler hooks in [backend/audit/ws_recorder.py](backend/audit/ws_recorder.py): wraps each handler in the orchestrator's WS dispatcher to record the action just performed (action type only — no raw payloads)
- [x] T027 [US1] Wire the WS hooks in [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py); ensure the orchestrator's existing per-connection `user_id` is the `actor_user_id` written
- [x] T028 [P] [US1] Implement orchestrator hooks in [backend/audit/orchestrator_hooks.py](backend/audit/orchestrator_hooks.py): `record_tool_dispatch_start`, `record_tool_dispatch_end`, `record_ui_render` (filtered to state-changing renders by component-class allowlist), `record_external_call` — all keyed by `correlation_id`, RFC 8693 actor mapping per research.md §R7
- [x] T029 [US1] Wire the orchestrator hooks at the actual call sites inside [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py) (tool dispatch path, `send_ui_render`, external integration points); start `in_progress` row, end with paired `success`/`failure`
- [x] T030 [P] [US1] Implement WS publisher in [backend/audit/ws_publisher.py](backend/audit/ws_publisher.py): given an `AuditEventDTO`, find connections whose `user_id == event.actor_user_id` and send `{"type":"audit_append","event":...}`. Server-side filter is the only filter; no broadcast
- [x] T031 [US1] Hook the publisher into `Recorder.record(...)` in [backend/audit/recorder.py](backend/audit/recorder.py) so every successful insert fans out to the user's WS connections (depends on T010, T030)
- [x] T032 [P] [US1] Add auth-lifecycle recording: emit `auth.login` / `auth.logout` / `auth.token_refresh` events from the existing Keycloak callback handlers (mock-auth path included). Locate via grep for the existing auth callback module and add the recorder call there
- [x] T033 [P] [US1] Implement orphan-sweeper job in [backend/audit/sweeper.py](backend/audit/sweeper.py): converts `in_progress` rows older than 5 minutes (configurable) into a paired `interrupted` follow-up row; runs on a background timer in `start.py`'s lifecycle
- [x] T034 [P] [US1] Implement REST client in [frontend/src/api/audit.ts](frontend/src/api/audit.ts): `listAudit(filters, cursor)` returning `{ items, next_cursor }` against `GET /api/audit`
- [x] T035 [P] [US1] Implement `useAuditStream` hook in [frontend/src/hooks/useAuditStream.ts](frontend/src/hooks/useAuditStream.ts): subscribes to `audit_append` via the existing `useWebSocket` event emitter (T012); exposes `(entries, refresh)` to components
- [x] T036 [US1] Implement `AuditLogPage` in [frontend/src/pages/AuditLogPage.tsx](frontend/src/pages/AuditLogPage.tsx): combines `listAudit()` for the initial page + `useAuditStream` for live appends; renders rows ordered by `recorded_at DESC`; manual refresh button calls `listAudit()` again to recover gaps; empty state when zero entries; uses only existing primitives from [frontend/src/catalog.ts](frontend/src/catalog.ts) (Constitution VIII)
- [x] T037 [P] [US1] Implement `AuditEntryRow` component in [frontend/src/components/audit/AuditEntryRow.tsx](frontend/src/components/audit/AuditEntryRow.tsx): timestamp + agent (if any) + description + outcome badge — composed from existing primitives only
- [x] T038 [US1] Add `/audit` route in [frontend/src/routes.tsx](frontend/src/routes.tsx) mapped to `AuditLogPage`; reflect filter + pagination state in the URL query string (FR-005)
- [x] T039 [US1] Add the "Audit log" button to [frontend/src/components/AppChrome.tsx](frontend/src/components/AppChrome.tsx) that navigates to `/audit` (or to the equivalent main-chrome component if AppChrome.tsx does not yet exist — locate via routes.tsx)
- [x] T040 [US1] Make `/api/audit` reads themselves emit an `audit_view` event in the caller's own log (closing the AU-2/AU-12 loop): in [backend/audit/api.py](backend/audit/api.py), after a successful list response, call `Recorder.record(...)` with `event_class="audit_view"` (depends on T010, T022)

**Checkpoint**: User Story 1 is fully functional. A user can open `/audit`, see all their actions (auth, conversation, file, agent tool calls, UI renders, external calls), watch new ones arrive live, and recover any gap via the refresh button. Admin-blindness, recording coverage, WS filtering, and tamper detection are covered by integration tests.

---

## Phase 4: User Story 2 — Inspect Action Details (Priority: P2)

**Goal**: A user clicks on any audit-log entry and sees full detail: inputs metadata, outputs metadata, outcome (with failure reason if applicable), originating conversation reference, and any artifact pointers (with `available` recomputed at read time per FR-017).

**Independent Test**: Click any entry in `/audit`, confirm the detail drawer renders all fields; force a failure on an agent tool call and confirm the failure reason renders in plain language; delete the underlying artifact and confirm the pointer flips to "source artifact no longer available" without breaking the entry.

### Tests for User Story 2 ⚠️

- [x] T041 [P] [US2] Contract test for `GET /api/audit/{event_id}` in [backend/tests/contract/audit/test_rest_contract.py](backend/tests/contract/audit/test_rest_contract.py) (extend the same file from T016): own-event 200, cross-user 404 indistinguishable from non-existent, schema matches [contracts/audit-event-schema.json](./contracts/audit-event-schema.json)
- [x] T042 [P] [US2] Integration test for pointer integrity in [backend/tests/integration/audit/test_pointer_integrity.py](backend/tests/integration/audit/test_pointer_integrity.py): entry references artifact A, A still present → `available=true`; A purged → `available=false`; entry remains visible in either case (FR-017 / Edge Case)
- [x] T043 [P] [US2] Frontend test in [frontend/tests/audit/AuditDetailDrawer.test.tsx](frontend/tests/audit/AuditDetailDrawer.test.tsx): renders all DTO fields, renders "source artifact no longer available" when `available=false`, surfaces `outcome_detail` for failures

### Implementation for User Story 2

- [x] T044 [US2] Implement REST detail endpoint in [backend/audit/api.py](backend/audit/api.py): `GET /api/audit/{event_id}` per [contracts/rest-audit-api.md](./contracts/rest-audit-api.md); 404 for both not-found and not-yours; computes `artifact_pointers[].available` at read time by probing each artifact's source store (depends on T009, T022)
- [x] T045 [P] [US2] Implement `AuditDetailDrawer` in [frontend/src/components/audit/AuditDetailDrawer.tsx](frontend/src/components/audit/AuditDetailDrawer.tsx): opened by selecting a row; pulls full detail via `getAudit(event_id)` (extend [frontend/src/api/audit.ts](frontend/src/api/audit.ts)); composed from existing primitives only
- [x] T046 [US2] Wire detail drawer into [frontend/src/pages/AuditLogPage.tsx](frontend/src/pages/AuditLogPage.tsx): clicking a row opens the drawer for that entry; reflect `event_id` in the URL so the detail view is deep-linkable (FR-005)
- [x] T047 [P] [US2] Extend [frontend/src/api/audit.ts](frontend/src/api/audit.ts) with `getAudit(event_id)` returning the full DTO

**Checkpoint**: User Stories 1 and 2 both work. The user can list and drill into any entry; pointer-integrity and admin-blindness still hold.

---

## Phase 5: User Story 3 — Filter and Search (Priority: P3)

**Goal**: A user with a large history filters their audit log by event class / agent, by outcome, by date range, and by keyword, and the URL reflects the filter state for shareability.

**Independent Test**: Generate a mix of audit entries across multiple agents, classes, and outcomes; apply each filter individually and in combination; confirm only matching entries appear; copy the URL into a new tab and confirm the filtered view restores.

### Tests for User Story 3 ⚠️

- [x] T048 [P] [US3] Contract test extension in [backend/tests/contract/audit/test_rest_contract.py](backend/tests/contract/audit/test_rest_contract.py): each filter parameter narrows results correctly; combined filters AND together; invalid `from`/`to` values produce 400; `q` matches against `description` and `action_type`
- [x] T049 [P] [US3] Frontend test in [frontend/tests/audit/AuditFilters.test.tsx](frontend/tests/audit/AuditFilters.test.tsx): toggling each filter pushes the expected query string; the page re-fetches with the new filters; resetting clears the URL state

### Implementation for User Story 3

- [x] T050 [US3] Extend `AuditRepository.list_for_user(...)` in [backend/audit/repository.py](backend/audit/repository.py) to accept the filter set defined in [contracts/rest-audit-api.md](./contracts/rest-audit-api.md): `event_class[]`, `outcome[]`, `from`, `to`, `q`. Use the existing partial index `idx_audit_user_failures` for the failures-only path
- [x] T051 [US3] Wire those filters through `GET /api/audit` in [backend/audit/api.py](backend/audit/api.py); validate values; echo normalized filters in the response `filters_echo`
- [x] T052 [P] [US3] Implement `AuditFilters` component in [frontend/src/components/audit/AuditFilters.tsx](frontend/src/components/audit/AuditFilters.tsx): event-class chips, outcome chips, date-range inputs, keyword field — composed from existing primitives only
- [x] T053 [US3] Integrate filters into [frontend/src/pages/AuditLogPage.tsx](frontend/src/pages/AuditLogPage.tsx): filter state lives in the URL query string; changes trigger a new `listAudit()` call; live `audit_append` events that don't match the active filters are dropped client-side (server still pushes everything for the user)

**Checkpoint**: All three user stories work. The audit log is browsable, drillable, and filterable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Operator tooling, retention, performance validation, documentation, and the deferred non-MVP recording-coverage hardening.

- [x] T054 [P] Implement operator CLI `verify-chain` in [backend/audit/cli.py](backend/audit/cli.py): walks a user's chain forward from genesis, recomputes `entry_hash` per row, reports any mismatch (uses `AuditRepository.verify_chain` from T009). Quickstart §6 references this
- [x] T055 [P] Implement operator CLI `purge-expired` in [backend/audit/cli.py](backend/audit/cli.py): connects under `audit_retention_role`, drops monthly partitions whose entire range is older than 6 years, emits a system operations log entry per purge (FR-012, AU-11)
- [x] T056 [P] Performance test for SC-006 in [backend/tests/integration/audit/test_load_first_page.py](backend/tests/integration/audit/test_load_first_page.py): seed 10,000 entries for a single user, assert `GET /api/audit?limit=50` returns in <2 s p95
- [x] T057 [P] Retention dry-run test in [backend/tests/integration/audit/test_retention.py](backend/tests/integration/audit/test_retention.py): seed entries dated 7 years ago into an old partition, run `purge-expired`, confirm the partition is dropped and recent partitions are untouched; assert chain verification of remaining users still passes
- [x] T058 [P] Add docstrings to every public function in [backend/audit/](backend/audit/) (Constitution VI); add JSDoc to exported TypeScript symbols in [frontend/src/api/audit.ts](frontend/src/api/audit.ts), [frontend/src/hooks/useAuditStream.ts](frontend/src/hooks/useAuditStream.ts), and the audit components
- [x] T059 [P] End-to-end Playwright (or existing equivalent) test in [frontend/tests/audit/e2e/audit_log.spec.ts](frontend/tests/audit/e2e/audit_log.spec.ts): two browser sessions logged in as different users; user A triggers an agent tool call; user A's `/audit` route shows it within 5 s; user B's `/audit` route never shows it
- [x] T060 Coverage check — confirm `backend/audit/` and frontend audit components meet ≥90% (Constitution III); add unit tests where shortfalls remain, located alongside the relevant module
- [x] T061 Run [quickstart.md](./quickstart.md) end-to-end on a clean dev DB; capture any drift between docs and reality and fix the docs (or the code)
- [x] T062 [P] Update [CLAUDE.md](CLAUDE.md) and project memory to point to [backend/audit/](backend/audit/) and the new `/audit` route, ensuring future agents understand the recording surface

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: no dependencies — start immediately
- **Phase 2 (Foundational)**: depends on Phase 1; **blocks all user stories**
- **Phase 3 (US1, MVP)**: depends on Phase 2 only
- **Phase 4 (US2)**: depends on Phase 2 (works independently of US1, but US1 ships first by priority)
- **Phase 5 (US3)**: depends on Phase 2; logically extends US1's list endpoint but is independently testable
- **Phase 6 (Polish)**: depends on whichever stories are in scope

### User Story Dependencies

- **US1 (P1)**: depends only on Foundational. Ships first as MVP.
- **US2 (P2)**: depends only on Foundational. Reuses the DB schema and recorder; touches a different REST endpoint and a separate UI component.
- **US3 (P3)**: depends only on Foundational. Extends the list endpoint and adds a filter component; does not alter US1's behavior when filters are absent (default is unfiltered).

### Within Each User Story

- Tests written first → run → confirmed FAILING → implementation → tests pass
- Backend models/repository before backend endpoints
- Backend endpoints before frontend client calls
- Frontend client/hooks before page assembly

### Parallel Opportunities

- All `[P]` tasks within a phase can run concurrently
- Within US1: T024, T026, T028, T030, T032, T033, T034, T035, T037 are all `[P]` — different files, no shared state
- Within Foundational: T007, T008, T011, T012, T013, T014, T015 are `[P]`
- US2 and US3 can be worked in parallel by different developers once Foundational is done

---

## Parallel Example: User Story 1 implementation

```bash
# Tests (write all first, in parallel):
Task: "Contract test for GET /api/audit in backend/tests/contract/audit/test_rest_contract.py"
Task: "Integration test for admin-blindness in backend/tests/integration/audit/test_admin_blindness.py"
Task: "Integration test for recording coverage in backend/tests/integration/audit/test_recording_coverage.py"
Task: "Integration test for WS live push in backend/tests/integration/audit/test_ws_live_push.py"
Task: "Integration test for tamper detection in backend/tests/integration/audit/test_tamper_detection.py"
Task: "Frontend test for AuditLogPage in frontend/tests/audit/AuditLogPage.test.tsx"

# Independent implementation tasks (different files):
Task: "Implement HTTP recording middleware in backend/audit/middleware.py"
Task: "Implement WS recorder in backend/audit/ws_recorder.py"
Task: "Implement orchestrator hooks in backend/audit/orchestrator_hooks.py"
Task: "Implement WS publisher in backend/audit/ws_publisher.py"
Task: "Implement REST client in frontend/src/api/audit.ts"
Task: "Implement useAuditStream hook in frontend/src/hooks/useAuditStream.ts"
Task: "Implement AuditEntryRow in frontend/src/components/audit/AuditEntryRow.tsx"
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Complete Phase 1 (Setup).
2. Complete Phase 2 (Foundational) — substrate, recorder, protocol, integrity. **Blocks everything else.**
3. Complete Phase 3 (US1) — recording sites, REST list, WS push, frontend route.
4. **STOP and VALIDATE**: run admin-blindness, tamper-detection, recording-coverage, and WS-filtering integration tests. Walk through the quickstart in dev.
5. Demo / merge MVP.

### Incremental Delivery

- After MVP: add US2 (detail drawer + pointer integrity).
- Then: add US3 (filters + URL state).
- Then: Polish — operator CLIs, retention, performance test, docs.

### Parallel Team Strategy

After Foundational completes:
- Developer A: US1 backend (T022–T033, T040)
- Developer B: US1 frontend (T034–T039)
- Developer C: US2 (T041–T047) — can start in parallel with US1's frontend work
- Developer D: US3 (T048–T053) — can start in parallel
- Reserve one engineer for Phase 6 polish + the cross-cutting Playwright test

---

## Notes

- Every task has a checkbox, ID, optional `[P]`, story tag where applicable, and an exact file path.
- `[P]` tasks touch different files and have no incomplete-task dependencies; safe to parallelize.
- Tests are required (Constitution III) and must FAIL before their corresponding implementation tasks run.
- Admin-blindness (FR-019), no-raw-payload (FR-004), HMAC-not-raw-hash (FR-016), and append-only (FR-014/AU-9) are constraints that show up in multiple tasks — do not relax them locally to "make a test pass."
- Avoid ad-hoc recording outside the recorder layer — adding a new `INSERT INTO audit_events` anywhere except `backend/audit/repository.py` is a review-blocking signal.
- Commit after each task or logical group; stop at any checkpoint to validate independently.
