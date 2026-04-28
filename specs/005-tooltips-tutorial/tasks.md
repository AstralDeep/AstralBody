---

description: "Task breakdown for 005-tooltips-tutorial"
---

# Tasks: Tool Tips and Getting Started Tutorial

**Input**: Design documents from `Y:/WORK/MCP/AstralBody/specs/005-tooltips-tutorial/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Test tasks ARE included — Constitution Principle III mandates 90% coverage with both unit and integration tests, so tests are a non-optional deliverable for every change in this feature.

**Organization**: Tasks are grouped by user story (US1, US2, US3) plus a fourth phase (US4) for the admin tutorial-step editing surface that supports FR-015–FR-018. Each phase is independently testable.

## Format

`- [X] [TaskID] [P?] [Story?] Description with file path`

- **[P]**: Parallelizable — different file, no dependency on incomplete tasks.
- **[Story]**: Maps the task to a user story (or omitted for shared phases).

## Path Conventions

Web app split (matches the existing AstralBody repo): `backend/` and `frontend/src/`. All paths in this file are absolute from the repo root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Folder skeletons and seed-data file. The repo, backend venv, frontend toolchain, lint, and CI are already in place from prior features.

- [X] T001 Create `backend/onboarding/` package with empty `__init__.py` so the new module is importable from `backend/orchestrator/api.py`.
- [X] T002 [P] Create `backend/onboarding/tests/` with empty `__init__.py` and a stub `conftest.py` that reuses the existing test database fixtures from `backend/audit/tests/conftest.py` (import path: `from audit.tests.conftest import *`).
- [X] T003 [P] Create `frontend/src/components/onboarding/` with an empty `index.ts` barrel so the directory is real before any component lands.
- [X] T004 Create `backend/seeds/tutorial_steps_seed.sql` with idempotent `INSERT … ON CONFLICT (slug) DO NOTHING` rows for the initial step set listed in `quickstart.md` §0 (welcome, chat-with-agent, open-agents-panel, open-audit-log, give-feedback for `audience='user'`; review-feedback-flagged, review-feedback-proposals, review-feedback-quarantine for `audience='admin'`).

**Checkpoint**: Empty packages exist; nothing imports them yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database schema, primitive extension, audit event-class registrations, and the admin-role dependency wiring. Every user story depends on this phase.

**⚠️ CRITICAL**: No user-story work begins until Phase 2 is complete.

- [X] T005 Add three new tables to `backend/shared/database.py` inside `Database._init_db()`: `onboarding_state`, `tutorial_step`, and `tutorial_step_revision` per [data-model.md](data-model.md) §1–§3. Include the listed PK / FK / `CHECK` constraints and the indices `(slug)` on `tutorial_step`, `(archived_at, audience, display_order)` on `tutorial_step`, `(step_id, edited_at DESC)` and `(editor_user_id, edited_at DESC)` on `tutorial_step_revision`. Statements MUST be `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` so re-runs are idempotent.
- [X] T006 [P] Add `tooltip: Optional[str] = None` to the base `Component` dataclass in `backend/shared/primitives.py`. Confirm by serializing one of every existing subclass (`Container`, `Text`, `Button`, `Card`, `Table`, `Alert`, `MetricCard`, `Input`) and checking the new field appears as `null` when unset and as the string when set.
- [X] T007 [P] Register five new audit event classes in the existing audit recorder (likely `backend/audit/schemas.py` — `event_class` enum or constant list): `onboarding_started`, `onboarding_completed`, `onboarding_skipped`, `onboarding_replayed`, `tutorial_step_edited`. No schema migration needed for `audit_events` itself.
- [X] T008 [P] In `backend/onboarding/recorder.py`, write thin wrappers around the existing audit recorder: `record_onboarding_started(user_id, step_slug)`, `record_onboarding_completed(user_id, last_step_slug, duration_seconds)`, `record_onboarding_skipped(user_id, last_step_slug)`, `record_onboarding_replayed(user_id, prior_status)`, `record_tutorial_step_edited(actor_user_id, step_id, step_slug, change_kind, changed_fields)`. Each returns the audit row id for caller use.
- [X] T009 In `backend/onboarding/schemas.py`, define Pydantic models matching the [contracts/](contracts/) shapes: `OnboardingStateResponse`, `OnboardingStateUpdateRequest`, `TutorialStepDTO`, `TutorialStepListResponse`, `AdminTutorialStepCreateRequest`, `AdminTutorialStepUpdateRequest`, `AdminTutorialStepListResponse`, `RevisionDTO`, `RevisionListResponse`. Include the validators called out in the contracts (status enum, audience enum, target-kind/target-key consistency, title/body trimmed-non-empty length bounds 1–120 / 1–1000).
- [X] T010 In `backend/onboarding/repository.py`, implement raw psycopg2 CRUD: `get_state(conn, user_id) -> OnboardingStateResponse`, `upsert_state(conn, user_id, status, last_step_id) -> OnboardingStateResponse`, `list_steps_for_user(conn, *, include_admin: bool) -> list[TutorialStepDTO]`, `get_step(conn, step_id) -> TutorialStepDTO | None`, `create_step(conn, dto) -> TutorialStepDTO`, `update_step(conn, step_id, partial) -> tuple[TutorialStepDTO, list[str]]` returning `(row, changed_fields)`, `archive_step(conn, step_id) -> TutorialStepDTO`, `restore_step(conn, step_id) -> TutorialStepDTO`, `list_revisions(conn, step_id) -> list[RevisionDTO]`, `append_revision(conn, step_id, editor_user_id, change_kind, previous, current)`. Every write happens in a single transaction with the corresponding revision/audit insertion.
- [X] T011 [P] Reuse the existing admin dependency. In `backend/onboarding/api.py`, import `require_admin` (or whichever FastAPI dependency `backend/feedback/api.py` already uses) — do **not** add a new admin check. Confirm it pulls `is_admin` from the verified token (`backend/orchestrator/auth.py:269`). If no shared dependency exists, lift the inline check from `backend/feedback/api.py` into a new `backend/orchestrator/auth.py` helper named `require_admin` and refactor feedback to use it.
- [X] T012 In `backend/orchestrator/api.py`, register the new onboarding router at module-level alongside the existing audit and feedback routers. Run the seed loader at startup (idempotent) so new deployments come up with the canonical step set.
- [X] T013 [P] [P] Backend test: `backend/onboarding/tests/test_schema_init.py` — start a fresh test DB, call `_init_db()`, and assert the three tables and all four indices exist with the expected columns and constraints. Re-run `_init_db()` and assert no error (idempotent).

**Checkpoint**: Tables exist, primitive supports tooltips, audit event classes are registered, admin dependency is shared. User-story work can begin.

---

## Phase 3: User Story 1 — First-Run Guided Tutorial (Priority: P1) 🎯 MVP

**Goal**: A fresh user signs in, sees the tutorial overlay within 2 s, can advance through every step, can skip with one click, has their state persisted to the backend, can resume on browser reload, and is not auto-launched on subsequent sign-ins.

**Independent Test**: Per [quickstart.md](quickstart.md) §1 and §2 — clear `onboarding_state` for a test user, sign in, complete or skip the tour, sign out and back in, and confirm no auto-launch. Each step's Next/Back/Skip controls are individually exercisable.

### Tests for User Story 1

- [X] T014 [P] [US1] Contract test for `GET /api/onboarding/state` and `PUT /api/onboarding/state` in `backend/onboarding/tests/test_api_user.py` — covers: not-started default, in_progress upsert + `onboarding_started` audit event, completed transition + `onboarding_completed` audit event with `completed_at` populated, `skipped` transition similarly, `409` on completed → in_progress, `400` on `user_id` query param, `400` on `last_step_id` referencing an admin-audience step from a non-admin caller.
- [X] T015 [P] [US1] Contract test for `GET /api/tutorial/steps` in `backend/onboarding/tests/test_api_user.py` — covers: non-admin sees only `audience='user'` non-archived steps; admin sees both audiences; archived steps excluded from both; ordering is `display_order ASC, id ASC`.
- [X] T016 [P] [US1] Repository test in `backend/onboarding/tests/test_repository.py` — covers: `get_state` returns implicit `not_started` when no row; `upsert_state` is idempotent; `list_steps_for_user(include_admin=False)` filters correctly; `list_steps_for_user(include_admin=True)` returns combined list in correct order; archived steps excluded from both lists.
- [X] T017 [P] [US1] Recorder test in `backend/onboarding/tests/test_recorder.py` — covers: each onboarding event-class wrapper writes a row in `audit_events` with the expected `event_class`, `user_id`, and payload fields, and the row participates in feature 003's hash chain.
- [X] T018 [P] [US1] Frontend test `frontend/src/components/onboarding/__tests__/OnboardingContext.test.tsx` — covers: state machine transitions (not_started → in_progress → completed; in_progress → skipped); resume-on-mount picks the next non-archived step ≥ `last_step_id`; replay leaves persisted state untouched.
- [X] T019 [P] [US1] Frontend integration test `frontend/src/components/onboarding/__tests__/TutorialOverlay.test.tsx` — covers: overlay appears when context status is `in_progress`; Next advances; Skip dispatches the `skipped` transition and closes; Escape behaves like Skip; focus is trapped while open and restored on close.

### Implementation for User Story 1

- [X] T020 [US1] Implement `GET /api/onboarding/state` in `backend/onboarding/api.py` per [contracts/onboarding-state.md](contracts/onboarding-state.md). Reject any request that includes `user_id`/`actor_user_id`/`as_user` query params with `400`.
- [X] T021 [US1] Implement `PUT /api/onboarding/state` in `backend/onboarding/api.py` — calls `repository.upsert_state` and the appropriate `recorder.record_*` wrapper inside a single transaction. Returns `409` on the disallowed `completed/skipped → in_progress` transition.
- [X] T022 [US1] Implement `GET /api/tutorial/steps` in `backend/onboarding/api.py` — delegates to `repository.list_steps_for_user`, deriving `include_admin` from the caller's `is_admin` flag.
- [X] T023 [P] [US1] Implement `frontend/src/components/onboarding/useOnboardingState.ts` — wraps `fetch('/api/onboarding/state')` (GET) and `fetch('/api/onboarding/state', { method: 'PUT' })` with the existing auth-header injector used by other feature panels (see how `frontend/src/components/audit/AuditLogPanel.tsx` calls `/api/audit`).
- [X] T024 [P] [US1] Implement `frontend/src/components/onboarding/useTutorialSteps.ts` — fetches `/api/tutorial/steps` once per tutorial activation; returns `{ steps, loading, error }`. No persistent cache (see research.md Decision 9).
- [X] T025 [US1] Implement `frontend/src/components/onboarding/OnboardingContext.tsx` — provider exposing `{ state, steps, currentStep, next(), back(), skip(), complete() }`. On mount: if `state.status === 'in_progress'` and not currently visible, auto-show. On `next()` from the final step: call `complete()`. Persists every transition via `useOnboardingState`.
- [X] T026 [US1] Implement `frontend/src/components/onboarding/TutorialStep.tsx` — renders the title and body of the active step, plus Next/Back/Skip buttons; receives `step` and the navigation callbacks via props. Uses the existing typographic primitives from `frontend/src/components/` so the styling matches.
- [X] T027 [US1] Implement `frontend/src/components/onboarding/TutorialOverlay.tsx` — dialog-role overlay with a hand-rolled focus trap, ARIA wiring (`aria-labelledby` to the step title, `aria-describedby` to the body), Escape handler, scroll-into-view of the target element when applicable, and a transparent cutout/highlight aligned to the target's bounding rect (use `getBoundingClientRect` and a `ResizeObserver` so reflows reposition correctly per the spec edge case). Renders `TutorialStep` inside.
- [X] T028 [US1] Mount `<TutorialOverlay />` once near the top of `frontend/src/components/DashboardLayout.tsx`, inside an `<OnboardingProvider>` that wraps the rest of the dashboard. Auto-fetch initial state on first render so the overlay can self-decide whether to show.
- [X] T029 [P] [US1] Add `data-tutorial-target="<key>"` attributes to the static elements referenced by the seeded user-flow steps (chat input, agents sidebar entry, audit log sidebar entry, feedback control trigger). Steps with `target_kind='static'` resolve targets by querying `[data-tutorial-target="<target_key>"]`.

**Checkpoint**: Fresh user → tutorial → completed/skipped → no re-launch on next sign-in. Quickstart §1 and §2 pass end-to-end.

---

## Phase 4: User Story 2 — Contextual Tooltips (Priority: P2)

**Goal**: Hovering or keyboard-focusing any interactive control with associated help text shows a tooltip within 500 ms; tooltips dismiss on pointer-leave, blur, or Escape; controls without help text show no frame; SDUI components carry tooltip text from the backend payload.

**Independent Test**: Per [quickstart.md](quickstart.md) §4 and §5 — with the tutorial dismissed, hover or Tab to every interactive control listed in `tooltipCatalog.ts`, and trigger an SDUI dispatch that returns a `Component(tooltip="…")` payload.

### Tests for User Story 2

- [X] T030 [P] [US2] Frontend unit test `frontend/src/components/onboarding/__tests__/Tooltip.test.tsx` — covers: appears within 500 ms of hover; appears immediately on keyboard focus; dismisses on pointer-leave within 200 ms; dismisses on Escape immediately; renders nothing when `text` prop is null/empty (FR-008); on touch, appears on long-press, not on tap.
- [X] T031 [P] [US2] Backend test `backend/onboarding/tests/test_primitive_tooltip.py` — covers: every primitive subclass round-trips through `to_json()` / `from_json()` with and without `tooltip`; an existing payload without the field deserializes cleanly with `tooltip = None`.

### Implementation for User Story 2

- [X] T032 [P] [US2] Implement `frontend/src/components/onboarding/Tooltip.tsx` — props `{ text: string | null | undefined; children: ReactNode; placement?: 'top'|'bottom'|'left'|'right' }`. Returns `children` unmodified when `text` is empty/null (FR-008). Otherwise wraps children with hover, focus, and long-press handlers; renders the tooltip in a portal at the placement; sets `aria-describedby` on the wrapped child.
- [X] T033 [P] [US2] Implement `frontend/src/components/onboarding/TooltipProvider.tsx` — single keyboard listener (Escape) and a single "active tooltip" registry so only one tooltip is visible at a time. Mounted once near the root of `DashboardLayout` alongside `OnboardingProvider`.
- [X] T034 [P] [US2] Create `frontend/src/components/onboarding/tooltipCatalog.ts` — typed export `tooltipCatalog: Record<string, string>` keyed by stable element ids (`sidebar.audit`, `sidebar.agents`, `sidebar.feedback-admin`, `chat.input`, `chat.send`, etc.). Add ESLint rule comment so unused keys are flagged.
- [X] T035 [US2] In `frontend/src/components/DashboardLayout.tsx`, wrap each sidebar button and other static interactive controls with `<Tooltip text={tooltipCatalog['sidebar.audit']}>`-style usage. Do **not** auto-tooltip every element — only ones with a catalog entry, so FR-008 holds without a special-case for empty strings.
- [X] T036 [US2] In `frontend/src/components/DynamicRenderer.tsx`, when rendering any SDUI component whose JSON has a non-empty `tooltip` field, wrap the rendered React element in `<Tooltip text={component.tooltip}>`. This is the single chokepoint for SDUI tooltip wiring (research.md Decision 10).
- [X] T037 [US2] Detect touch devices using the existing ROTE device-capabilities pipeline already attached in `frontend/src/hooks/useWebSocket.ts` — expose a `useDeviceCapabilities()` hook (or read from existing context if one exists) so `Tooltip` can switch its trigger from hover to long-press on touch (FR-011).

**Checkpoint**: Hover/focus tooltips on the static dashboard plus SDUI components. Quickstart §4 and §5 pass.

---

## Phase 5: User Story 3 — Replay Tutorial On Demand (Priority: P3)

**Goal**: A user who has completed or skipped the tutorial can relaunch it from a sidebar affordance; replay does not re-trigger auto-launch on subsequent sign-ins.

**Independent Test**: Per [quickstart.md](quickstart.md) §3 — from `completed` or `skipped` state, click the sidebar "Take the tour" entry, run the tour (or skip), then sign out / in and confirm no auto-launch.

### Tests for User Story 3

- [X] T038 [P] [US3] Contract test for `POST /api/onboarding/replay` in `backend/onboarding/tests/test_api_user.py` — covers: `204` response; `onboarding_replayed` audit event recorded with `prior_status` reflecting the row's status (or `not_started` if no row exists); the row's `status`, `completed_at`, `skipped_at` are unchanged afterwards (per research.md Decision 8).
- [X] T039 [P] [US3] Frontend test in `frontend/src/components/onboarding/__tests__/OnboardingContext.test.tsx` — extend with: `replay()` activates the overlay at step 1 without mutating persisted state; subsequent unmount/mount does not auto-show the overlay.

### Implementation for User Story 3

- [X] T040 [US3] Implement `POST /api/onboarding/replay` in `backend/onboarding/api.py` per [contracts/onboarding-state.md](contracts/onboarding-state.md). Single repository read for `prior_status`, single recorder call, no row mutation.
- [X] T041 [US3] Extend `frontend/src/components/onboarding/OnboardingContext.tsx` with a `replay()` method — POSTs `/api/onboarding/replay`, then sets the in-memory active step to the first user-applicable step and shows the overlay. Does NOT call the state-update endpoint.
- [X] T042 [US3] Add a "Take the tour" entry to the sidebar in `frontend/src/components/DashboardLayout.tsx` that calls `replay()` from `OnboardingContext`. Place it under the existing "Audit log" / "Agents" entries; reuse the same icon/spacing pattern.
- [X] T043 [US3] Add a `tooltipCatalog` entry for the new sidebar button (e.g., `sidebar.replay-tour`) so it follows the FR-008 rule from US2.

**Checkpoint**: Replay works from any post-tour state; auto-launch suppression remains intact. Quickstart §3 passes.

---

## Phase 6: User Story 4 — Admin Tutorial Step Editing (supports FR-015–FR-018)

**Goal**: Admins can create, edit, archive, and restore tutorial steps via an admin-only UI; edits take effect on next user replay without redeploy; non-admins are blocked at the API layer; every edit produces a revision row and an audit event.

**Independent Test**: Per [quickstart.md](quickstart.md) §6 and §7 — sign in as admin, edit a step's body, replay the tour as a regular user, see the new copy. Sign in as non-admin, attempt the admin endpoints directly, get `403`.

### Tests for User Story 4

- [X] T044 [P] [US4] Contract test in `backend/onboarding/tests/test_api_admin.py` for `GET /api/admin/tutorial/steps`, `POST /api/admin/tutorial/steps`, `PUT /api/admin/tutorial/steps/{id}`, `POST /api/admin/tutorial/steps/{id}/archive`, `POST /api/admin/tutorial/steps/{id}/restore`, `GET /api/admin/tutorial/steps/{id}/revisions` — covers all status codes from [contracts/admin-tutorial-steps.md](contracts/admin-tutorial-steps.md), including the `403` for non-admin callers and the `409` for duplicate slug.
- [X] T045 [P] [US4] Repository test in `backend/onboarding/tests/test_repository.py` — covers: `update_step` returns the correctly minimized `changed_fields` list (no false positives when the same value is assigned), revision row's `previous` matches the prior `current`, archive/restore round-trip writes both revision rows.
- [X] T046 [P] [US4] Recorder test in `backend/onboarding/tests/test_recorder.py` — covers: `record_tutorial_step_edited` writes an audit row with `event_class='tutorial_step_edited'`, `actor_user_id` from JWT (admin), `step_id`, `change_kind`, and the structured `changed_fields` list.
- [X] T047 [P] [US4] Frontend test `frontend/src/components/onboarding/__tests__/TutorialAdminPanel.test.tsx` — covers: panel renders the full step list with archived steps visible; edit form roundtrips title and body; archive button toggles `archived_at`; the panel is unreachable for non-admin users (component-level rendering guard).

### Implementation for User Story 4

- [X] T048 [US4] Implement `GET /api/admin/tutorial/steps` (with `include_archived` query param) in `backend/onboarding/api.py`, gated by the shared `require_admin` dependency.
- [X] T049 [US4] Implement `POST /api/admin/tutorial/steps` — single transaction that inserts the step, appends a `tutorial_step_revision` row with `change_kind='create'`, and records the `tutorial_step_edited` audit event. Returns `201`.
- [X] T050 [US4] Implement `PUT /api/admin/tutorial/steps/{step_id}` — partial update; computes `changed_fields` by comparing the prior row to the patched row (skip equal-value writes); writes a single revision and audit event per request; returns the patched row.
- [X] T051 [US4] Implement `POST /api/admin/tutorial/steps/{step_id}/archive` and `/restore` — idempotent toggles of `archived_at`; each writes a revision row (`change_kind='archive'` or `'restore'`) and an audit event.
- [X] T052 [US4] Implement `GET /api/admin/tutorial/steps/{step_id}/revisions` — reverse-chronological list from `tutorial_step_revision` for the given step.
- [X] T053 [P] [US4] Implement `frontend/src/components/onboarding/TutorialAdminPanel.tsx` — modal-style panel mirroring `FeedbackAdminPanel.tsx`. List view with edit / archive / restore buttons per row, plus a "New step" button. Edit form fields: `audience` (select), `display_order` (number), `target_kind` (select), `target_key` (text), `title` (text, ≤120), `body` (textarea, ≤1000). On save, calls the appropriate admin endpoint. Show inline 403 message if the panel is somehow opened without admin role (defense in depth — server already blocks).
- [X] T054 [P] [US4] Add a "Tutorial admin" sidebar entry in `frontend/src/components/DashboardLayout.tsx`, conditional on `is_admin` from the same source `FeedbackAdminPanel` already uses. Wire it to mount `TutorialAdminPanel` as an overlay modal (parallel to the feedback admin pattern).
- [X] T055 [P] [US4] Add `tooltipCatalog` entries for the admin panel's primary controls (`admin.tutorial.new-step`, `admin.tutorial.archive`, `admin.tutorial.restore`).

**Checkpoint**: Admins can edit step copy live; non-admins are blocked at the API and the UI; revision history and audit events are written for every edit. Quickstart §6 and §7 pass.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Accessibility validation, full-suite test runs, documentation updates, and the end-to-end quickstart sweep.

- [X] T056 [P] Accessibility pass per [quickstart.md](quickstart.md) §11 — keyboard-only walkthrough of the tutorial overlay, screen-reader (NVDA or VoiceOver) announcement check on at least one user-flow step and one admin-flow step, focus-trap and focus-restore verification. File any axe-core findings as follow-up tasks.
- [X] T057 [P] Run the full backend test suite for the new module: `docker exec astralbody bash -c "cd /app/backend && python -m pytest onboarding/tests/ -q"`. Confirm coverage on `backend/onboarding/` ≥ 90% (Constitution Principle III). If not, add the missing unit tests in `backend/onboarding/tests/`.
- [X] T058 [P] Run the frontend test suite: `cd frontend && npm run test -- onboarding`. Confirm coverage on `frontend/src/components/onboarding/` ≥ 90%.
- [X] T059 [P] Update `CLAUDE.md` "Active Technologies" / "Recent Changes" sections to reflect the shipped state of feature 005. (The `update-agent-context.ps1` script ran during planning; this task is for the implementer to confirm the entries are still correct after coding.)
- [X] T060 Run the end-to-end quickstart sweep ([quickstart.md](quickstart.md) §1 through §11) on a freshly-reset database. Capture any deviation as a follow-up task before merge.
- [X] T061 Manual security check: as a non-admin user, hit every `/api/admin/tutorial/*` endpoint with curl and confirm `403`; hit `/api/onboarding/state` with `?user_id=other_user` and confirm `400`; confirm no audit row leaks across users when querying `/api/audit` for the new event classes.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies; can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 — blocks all user stories.
- **Phase 3 (US1 — MVP)**: Depends on Phase 2 only; can ship as the MVP.
- **Phase 4 (US2 — Tooltips)**: Depends on Phase 2 only; independent of US1 functionally (and they share `TooltipProvider`/`OnboardingProvider` wiring in `DashboardLayout`, which T028/T035 must coordinate to avoid stomping on each other if shipped in parallel).
- **Phase 5 (US3 — Replay)**: Depends on Phase 3 (extends `OnboardingContext`).
- **Phase 6 (US4 — Admin editing)**: Depends on Phase 2; otherwise independent of US1/US2/US3 — can be developed in parallel with them.
- **Phase 7 (Polish)**: Depends on every phase the team has chosen to ship.

### Within Each User Story

- Tests for a story SHOULD be written first (TDD), but Constitution Principle III enforces coverage at merge time, not order.
- Schemas → repository → recorder → API endpoints → frontend hooks → frontend components → integration mounts.
- A story is "complete" only when its checkpoint clause holds (quickstart subsection passes).

### Parallel Opportunities

- All Phase 1 tasks marked [P] (T002, T003) can run in parallel.
- All Phase 2 tasks marked [P] (T006, T007, T008, T011, T013) can run in parallel after T005 lands the schema.
- US1 tests T014–T019 can all run in parallel.
- US1 implementation T023, T024, T029 can run in parallel; T025 depends on T023+T024; T027 depends on T026.
- US2 tasks T030–T034 can run in parallel; T035, T036, T037 depend on T032+T033.
- US4 backend tests T044–T046 can run in parallel; T047 is independent frontend.
- US4 implementation T048–T052 are mostly sequential (same file `backend/onboarding/api.py`) but T053–T055 are [P] across different frontend files.

---

## Parallel Example: User Story 1

```bash
# Phase 3 — kick off all US1 tests in parallel:
Task: "T014 contract test for /api/onboarding/state in backend/onboarding/tests/test_api_user.py"
Task: "T015 contract test for /api/tutorial/steps in backend/onboarding/tests/test_api_user.py"
Task: "T016 repository unit test in backend/onboarding/tests/test_repository.py"
Task: "T017 recorder unit test in backend/onboarding/tests/test_recorder.py"
Task: "T018 OnboardingContext.test.tsx in frontend/src/components/onboarding/__tests__/"
Task: "T019 TutorialOverlay.test.tsx in frontend/src/components/onboarding/__tests__/"

# After backend tests turn red, kick off backend implementation:
Task: "T020 GET /api/onboarding/state"
Task: "T021 PUT /api/onboarding/state"
Task: "T022 GET /api/tutorial/steps"

# Frontend hooks and overlay:
Task: "T023 useOnboardingState.ts"
Task: "T024 useTutorialSteps.ts"
Task: "T029 data-tutorial-target attributes on static targets"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 — Setup (T001–T004)
2. Phase 2 — Foundational (T005–T013)
3. Phase 3 — US1 (T014–T029)
4. **STOP and validate** with [quickstart.md](quickstart.md) §1 and §2.
5. Ship the MVP. Tooltips, replay, and admin editing are still ahead but the core onboarding experience is live.

### Incremental Delivery

1. Foundation → MVP (US1) → ship.
2. Add US2 (Tooltips) → ship.
3. Add US3 (Replay) → ship.
4. Add US4 (Admin editing) → ship.
5. Each phase adds value without breaking previous phases; the audit-log integration and per-user isolation guarantees hold across all four.

### Parallel Team Strategy

After Phase 2 lands, three streams can run concurrently:

- Developer A: US1 (Phase 3) — overlay + state endpoints. (MVP gate.)
- Developer B: US2 (Phase 4) — tooltip layer + DynamicRenderer integration.
- Developer C: US4 (Phase 6) — admin endpoints + admin panel.

US3 (Phase 5) is small and can be picked up by whoever finishes their stream first.

---

## Notes

- `[P]` = different file, no dependency on incomplete tasks.
- `[US#]` traceability ties each task back to the user story it serves; setup/foundational/polish tasks have no story label.
- Constitution Principle V is satisfied by reuse — no new third-party libraries are introduced anywhere in this task list.
- The audit-log integration (T007, T008, T046) reuses feature 003 wholesale; do not introduce a parallel audit pipeline.
- Per-user isolation is enforced exclusively at the API layer — never trust a `user_id` query parameter (T020, T021, T040, T061).
- Admin RBAC is enforced via the shared `require_admin` dependency (T011) — do not duplicate the role check in each endpoint.
- Each task should be a single commit (or, where multiple tasks edit the same file in sequence, a single squashed commit at the end of the phase).
