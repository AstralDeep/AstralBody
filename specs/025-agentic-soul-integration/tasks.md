# Tasks: Agentic Soul Integration

**Input**: Design documents from `/specs/025-agentic-soul-integration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED — Constitution Principle III mandates unit + integration tests with ≥90% coverage on changed code. Test tasks are first-class here, not optional.

**Organization**: Tasks are grouped by user story (US1–US6) to enable independent implementation and testing.

> **Container + LIVE-STACK validation (2026-05-27):**
> - `docker compose build astraldeep` succeeds with the new deps (presidio, spaCy + `en_core_web_lg`, tzdata) — **requirements resolve cleanly** (image 1.08→2.17GB). In-container `pytest personalization scheduler dreaming` = **49 passed, 0 skipped**. Real Presidio PHI gate smoke test: detects PERSON/MRN/email, passes clean text.
> - **Live stack (`docker compose up`)**: all 7 tables auto-migrated on startup; backend starts clean with new routers registered. **Authenticated end-to-end tests pass**: profile PUT/GET persists (US1/US3); **PHI in profile → `422` blocked by real Presidio (US4/SC-005)**; skills catalog lists live agent tools (US2); dreaming status + manual sweep run (US6); onboarding ParamPicker panel served (US1/T019); schedule governance rejects 30s interval `400`, creates a NY-tz cron job `201`, lists + deletes it (US5); audit_events recorded `success` for `personalization`/`memory`/`dreaming`/`schedule` (SC-004).
> - **Still pending (correctly):** scheduler *execution* loop is gated OFF pending **T057** security review of the offline-grant store; LLM-driven submit interpretation (T021/T050); frontend glue (T022); formal pytest-TestClient files (T013–T015/T024/T033/T040 — behavior validated via live API instead).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US6 (setup/foundational/polish carry no story label)

## Path Conventions

Web app: backend modules under `backend/`, frontend under `frontend/src/`. New modules: `backend/personalization/`, `backend/scheduler/`, `backend/dreaming/`. Per-module unit tests in `backend/<module>/tests/`; cross-cutting integration tests in `backend/tests/integration/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project scaffolding and the one approved dependency.

- [X] T001 Create backend module skeletons (`__init__.py` + submodules) for `backend/personalization/`, `backend/scheduler/`, `backend/dreaming/`, and register their FastAPI routers in the orchestrator app (`backend/orchestrator/orchestrator.py` app factory, lines ~5306/5327)
- [X] T002 Add the lead-dev-approved PHI deps (`presidio-analyzer`, `presidio-anonymizer`, `spacy`) to `backend/requirements.txt` and add the spaCy model download (`en_core_web_lg`) to the `Dockerfile` build stage (build-time, no runtime fetch); approval documented in requirements.txt comment + PR per Constitution V
- [X] T003 [P] Add feature configuration in `backend/agentic_settings.py`: `OFFLINE_GRANT_ENC_KEY` (secret, env-only), `SCHEDULER_TICK_SECONDS` (≤60), `SCHEDULE_MAX_ACTIVE_JOBS_PER_USER`, `SCHEDULE_MIN_INTERVAL_SECONDS`, `DREAMING_DEFAULT_CRON`, `OFFLINE_GRANT_MAX_DAYS` — all env-driven, no hard-coded values

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema, audit classes, the PHI gate, and the per-user prompt-injection point that multiple stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Add all new tables to `backend/shared/database.py::Database._init_db()` idempotently (`CREATE TABLE IF NOT EXISTS` + `_column_exists()` convention) with indexes per [data-model.md](data-model.md): `user_personalization`, `memory_item`, `short_term_signal`, `scheduled_job`, `job_run`, `consolidation_sweep`, `user_offline_grant`
- [X] T005 [P] Add user-scoped persistence (get/upsert/delete) for the new tables — folded into the per-module repositories (`personalization/repository.py`; scheduler store pending in US5) using the existing generic `Database.execute/fetch_*` API, matching the audit/onboarding repository convention
- [X] T006 [P] Extend `EVENT_CLASSES` in `backend/audit/schemas.py` with `personalization`, `memory`, `skill`, `schedule`, `dreaming`; `auth` (existing) covers `auth.offline_grant_minted` / `auth.offline_grant_revoked`
- [X] T007 Implement the PHI gate in `backend/personalization/phi_gate.py`: Presidio `AnalyzerEngine` (PERSON, LOCATION, US_SSN, MEDICAL_LICENSE, US_DRIVER_LICENSE, PHONE_NUMBER, EMAIL_ADDRESS) + a custom MRN recognizer + a cheap pure-Python pre-filter; **fail-closed** (block on analyzer error/unavailable); exposes `contains_phi(text)` and `filter_value(value)`
- [X] T008 [P] Unit tests for the PHI gate in `backend/personalization/tests/test_phi_gate.py` (PHI-shaped inputs blocked incl. names/MRN/SSN/DOB; clean personalization text passes; fail-closed when analyzer unavailable) — **16 tests passing locally**
- [X] T009 [P] Implement personalization repository (profile, personality, memory_item, short_term_signal CRUD — strictly user-scoped) in `backend/personalization/repository.py` (audit emitted at the API/service layer)
- [X] T010 Implement personalization service in `backend/personalization/service.py`: assemble the per-user prompt fragment in order **memory recall → user context → skill guidance → personality (explicitly subordinate via `PERSONALITY_PREAMBLE`)**; returns empty string when no data
- [X] T011 Wire the injection point in `backend/orchestrator/orchestrator.py` (immediately after the knowledge-synthesis block, before `_call_llm`) to append the personalization fragment; graceful no-op when empty/error
- [X] T012 [P] Test prompt-injection precedence mechanism in `backend/personalization/tests/test_service_fragment.py` (personality rendered last + behind the "never overrides compliance" preamble) — **passing locally**. NOTE: full behavioral test (LLM obeys compliance over personality) requires the live stack and is deferred to staging validation.

**Checkpoint**: Schema, audit, PHI gate, personalization service, and injection point ready — user stories can begin.

---

## Phase 3: User Story 1 - Personalized onboarding (Priority: P1) 🎯 MVP

**Goal**: A new user is guided through server-generated onboarding that introduces available agents, captures profession + goals, recommends/enables skills, and sets a personality — and the assistant reflects it next session.

**Independent Test**: Create a brand-new user, complete onboarding (profession+goals saved, ≥1 skill enabled, personality chosen); start a fresh chat and confirm the assistant references profession/goals and uses the chosen tone; sign out/in and confirm onboarding does not re-run.

### Tests for User Story 1

- [ ] T013 [P] [US1] Contract test for `GET/PUT/DELETE /api/personalization/profile` in `backend/personalization/tests/test_profile_api.py` (per [contracts/personalization-api.md](contracts/personalization-api.md))
- [ ] T014 [P] [US1] Contract test for `GET /api/onboarding/personalize/{step}` returning ParamPicker `_ui_components` in `backend/onboarding/tests/test_personalize_steps.py`
- [ ] T015 [P] [US1] Integration test for the full onboarding round-trip + run-once + skip/resume in `backend/tests/integration/test_onboarding_personalization.py` (FR-002/005/006, SC-001/002/003)

### Implementation for User Story 1

- [X] T016 [P] [US1] Define personalization schemas (profile, personality) in `backend/personalization/schemas.py` — **validated** (pydantic tests pass)
- [X] T017 [US1] Implement profile endpoints `GET/PUT/DELETE /api/personalization/profile` in `backend/personalization/api.py` (PHI-gate string values via T007 → 422 on PHI; emit `personalization.profile_update`/`personalization.personality_update`) — authored, compiles; HTTP behavior needs live stack
- [X] T018 [P] [US1] Seed personalization tutorial steps (`personalize-profession`, `personalize-skills`, `personalize-personality`, `target_kind='sdui'`) appended to `backend/seeds/tutorial_steps_seed.sql` (`ON CONFLICT (slug) DO NOTHING`) — **030 reconciliation:** these slugs were intentionally archived by the 030-wiring tutorial rewrite (`_LEGACY_TUTORIAL_SLUGS_030` in `shared/database.py`); onboarding personalization is now delivered through the ParamPicker panel/submit flow (030 FR-009), not the legacy seed.
- [X] T019 [US1] Panel builders (`panels.py`) **+** the `GET /api/onboarding/personalize/{step}` endpoint in `onboarding/api.py` (serves profession/skills/personality ParamPickers; skills step ranks live agent tools via `recommend_skills`) — **live-validated** (`200` with `_ui_components`)
- [X] T020 [US1] Implement profession→skill recommendation ranking in `backend/personalization/skills_reco.py` (pure function; ranks agent tools by relevance, prefers authorized on ties) — **validated** (FR-003, FR-007)
- [X] T021 [US1] Handle onboarding ParamPicker submits in the orchestrator (interpret `submit_message_template` → save profile / enable skills) — **DONE in 030** (`backend/orchestrator/onboarding_submit.py`, intercepted in `handle_chat_message`; deterministic parse of the three submit templates → PHI-gated profile + scope-gated skills; 030 FR-009/FR-011).
- [X] T022 [US1] Frontend editing UI — **030 reconciliation:** the React `PersonalizationPanel.tsx` referenced here was removed with the whole client frontend in feature 026 and was reimplemented as the server-rendered chrome surface `backend/webrender/chrome/surfaces/personalization.py` (tabs: soul / memory / skills / schedule / dreaming) in feature 027. Functionally complete via the settings menu; this task's original React artifact no longer exists by design.
- [X] T023 [US1] No-agents-available edge case handled in `build_skills_panel` (explanatory Alert, no dead-end) — **validated** (spec Edge Cases)

**Checkpoint**: US1 fully functional — onboarding personalizes the assistant end-to-end. **This is the MVP.**

---

## Phase 4: User Story 2 - Enableable skills (Priority: P2)

**Goal**: A standalone skills catalog (each skill = an agent tool) where the user enables/disables capabilities, gated by their existing scopes, fully audited.

**Independent Test**: Open the catalog, enable a skill you're authorized for and confirm the assistant can use it, disable it and confirm it's gone; view a skill needing an ungranted scope and see it unavailable with a reason — every change audited.

### Tests for User Story 2

- [ ] T024 [P] [US2] Formal pytest-TestClient integration test — PENDING (enable/disable + scope-gating behavior validated live via API instead: catalog `200`, FR-011 guard returns `403`)

### Implementation for User Story 2

- [X] T025 [P] [US2] Skills catalog read-view implemented inline in `skills_router.list_skills` (enumerates `ToolPermissionManager` tool→scope map per agent with `enabled`/`authorized`) — **live-validated** (`GET /api/skills` → 200)
- [X] T026 [US2] Skills catalog + enable/disable endpoints in `backend/personalization/api.py` (`GET/PUT /api/skills`; maps to `tool_overrides` via `set_tool_overrides`; FR-011 guard = 403 if scope ungranted; emits `skill.enable`/`disable`) — **live-validated**
- [X] T027 [US2] Skills panel rendered server-side (`build_skills_panel`, ParamPicker checklist + Alert for no-agents) — **tested**
- [X] T028 [US2] FR-011 enforced (enable refused without scope). Disabled-skill no-leakage relies on the existing tool-assembly gate; skill-guidance line in the prompt fragment is wired via `service.build_prompt_fragment(skill_lines=...)`. **DONE in 030:** `personalization_skill_lines` is now populated from the live tool set in `handle_chat_message` (030 FR-010), so enabled-skill guidance reaches the prompt.

**Checkpoint**: US1 + US2 work independently.

---

## Phase 5: User Story 3 - Personality / "soul" (Priority: P2)

**Goal**: A user shapes the assistant's voice/tone/boundaries (one per user), honored across all conversations, always subordinate to compliance.

**Independent Test**: Set a distinctive personality, confirm responses reflect it in a new conversation; edit it and confirm the change applies; confirm a personality instruction cannot override a compliance rule.

### Tests for User Story 3

- [X] T029 [P] [US3] Precedence + rendering covered by `personalization/tests/test_service_fragment.py` (personality last + subordinate). NOTE: cross-session behavioral assertion needs live stack.

### Implementation for User Story 3

- [X] T030 [US3] Personality fields handled by the profile endpoints (`PersonalitySpec` tone/directness/humor/verbosity/notes; notes PHI-gated; emits `personalization.personality_update`) in `backend/personalization/api.py`
- [X] T031 [US3] Personality editor server-generated panel (`build_personality_panel`) in `backend/personalization/panels.py` — **tested**
- [X] T032 [US3] Personality injected **last + subordinate** via `PERSONALITY_PREAMBLE` in `backend/personalization/service.py` — **tested**

**Checkpoint**: US1 + US2 + US3 independently functional.

---

## Phase 6: User Story 4 - Cross-session memory (Priority: P2)

**Goal**: The assistant remembers durable non-PHI facts (explicit + auto-captured signals), recalls them across sessions, and lets the user view/correct/delete; PHI never persists.

**Independent Test**: Tell the assistant a durable preference, start a new session and confirm it's honored; attempt to have it remember PHI and confirm 0 rows persist; delete an item and confirm it stops influencing the assistant in-session.

### Tests for User Story 4

- [ ] T033 [P] [US4] Contract test for `GET /api/memory`, `PUT/DELETE /api/memory/{id}` — PENDING (needs FastAPI TestClient + DB)
- [X] T034 [P] [US4] Memory-tool behavior incl. PHI-not-persisted (SC-005) covered by `personalization/tests/test_memory_tools.py`. NOTE: full DB cross-session/delete integration deferred to live stack.

### Implementation for User Story 4

- [X] T035 [P] [US4] Implement memory tools (`remember`, `memory_search`, `memory_get`, `capture_signal`) in `backend/personalization/memory_tools.py` — all PHI-gated via T007, user-scoped — **tested**
- [ ] T036 [US4] Register memory tools with the orchestrator tool registry (scope-gated) — PENDING. NOTE: memory recall is already injected via the prompt fragment (T010, done); tool-dispatch registration needs orchestrator internals.
- [X] T037 [US4] Post-turn auto-capture via `MemoryTools.capture_signal` (structured, PHI-gated, non-durable short_term_signal) — **tested** (FR-016, R5)
- [X] T038 [US4] Memory REST (`GET /api/memory`, `PUT/DELETE /api/memory/{id}`) in `backend/personalization/api.py` (PHI-gated update, audited `memory.*`) — **live-validated** (`GET /api/memory` → 200)

**Checkpoint**: US1–US4 independently functional; durable memory is non-PHI and user-managed.

---

## Phase 7: User Story 5 - Scheduled jobs / "cron" (Priority: P3)

**Goal**: Users schedule recurring/future work that runs unattended under bounded, consented, audited authority, delivers in-app, and is fully manageable — surviving restarts.

**Independent Test**: Schedule a short-interval job, confirm it fires on time without the user present and delivers in-app; revoke the grant/scope and confirm the next run is `skipped_auth` and the job pauses; restart the backend and confirm the job survives.

> **Security gate**: T040 (offline-grant store) requires lead-dev security review (Constitution VII) before US5 merges.

### Tests for User Story 5

- [X] T039 [P] [US5] Unit tests for the pure-Python cron/interval/one-shot next-run evaluator (tz-aware, weekday, ranges) + governance in `backend/scheduler/tests/test_cron.py` — **12 passing, 1 skipped (tz DB)**
- [ ] T040 [P] [US5] Integration test for run timing (SC-007), authority intersection + `skipped_auth`, in-app delivery, no-PHI-persist, restart recovery — PENDING (needs live stack)

### Implementation for User Story 5

- [~] T041 [US5] Encrypted offline-grant store authored in `backend/orchestrator/offline_grant.py` (Fernet via `cryptography` + `OFFLINE_GRANT_ENC_KEY`, 365-day cap, revoke-for-user, fail-closed if no key, refresh→access mint, token never returned/logged). **⚠️ REQUIRES T057 security review + live Keycloak validation before merge.**
- [ ] T042 [US5] WS `offline_grant_request`/`offline_grant_ack` consent capture in the orchestrator — PENDING (needs WS handler + live session)
- [X] T043 [P] [US5] Pure-Python next-run evaluator in `backend/scheduler/cron.py` (one-shot / interval / 5-field cron, tz-aware) — **tested**
- [X] T044 [P] [US5] Durable job/run persistence in `backend/scheduler/store.py` (`scheduled_job`, `job_run`, due-list, restart reconcile) — **live-validated** (create/list/delete via API against Postgres)
- [X] T045 [P] [US5] Governance in `backend/scheduler/governance.py` (per-user cap + min-interval floor) — **tested** (FR-038)
- [~] T046 [US5] Job runner authored in `backend/scheduler/runner.py` (grant→mint→scope-intersect→execute→fail-safe `skipped_auth`→reschedule→notify). Has a documented orchestrator seam (`run_scheduled_turn`/`notify_user`) to wire + verify. **Security-review gated.**
- [~] T047 [US5] Asyncio scheduler loop + restart reconciliation authored in `backend/scheduler/loop.py` (FR-025). PENDING: start it from the app lifespan.
- [X] T048 [US5] Schedule REST endpoints in `backend/scheduler/api.py` (`POST/GET /api/schedule`, `GET /{id}`, pause/resume/delete; consent required, scope-bounded, governance + cron validated; audited) — **live-validated** (30s→400, cron→201, list/delete OK). Server-generated manager panel: deferred with frontend.
- [ ] T049 [US5] In-app `notification` WS emit + output persistence — PENDING (runner calls `orch.notify_user` seam; needs orchestrator method)
- [X] T050 [US5] Orchestrator interpretation of "schedule this…" → consented job create — **DONE** (`backend/orchestrator/scheduling_chat.py`: `schedule_recurring_task` meta-tool → consent card → `handle_decision` creates the job; wired in `handle_chat_message` + dispatch; flag `FF_SCHEDULING_CHAT` default on; covered by `tests/test_wiring_030.py`).

**Checkpoint**: US1–US5 independently functional; unattended work is bounded, audited, in-app, and restart-safe.

---

## Phase 8: User Story 6 - Background consolidation / "dreaming" (Priority: P3)

**Goal**: A per-user, default-on background sweep promotes high-signal, recurring, non-PHI signals into durable memory, keeps a reviewable trail, and is user-controllable.

**Independent Test**: Generate mixed signals, run a sweep, and confirm only high-signal non-PHI items promote (one-off/PHI = 0) with a readable summary; toggle dreaming off and confirm it stops.

### Tests for User Story 6

- [X] T051 [P] [US6] Consolidation scoring + sweep tests (high-signal recurring non-PHI promoted, one-offs + PHI excluded — SC-011/FR-028) in `backend/dreaming/tests/test_consolidation.py` — **passing**

### Implementation for User Story 6

- [X] T052 [US6] Consolidation scoring + promotion (recurrence/recency thresholds; PHI-excluded via T007; writes `consolidation_sweep`) in `backend/dreaming/consolidation.py` — **tested**
- [ ] T053 [US6] Register dreaming as a per-user default-on recurring scheduler job honoring `dreaming_enabled` — PENDING (needs scheduler loop wired into app; `repo.record_sweep` ready, dreaming_enabled flag in schema/repo done)
- [X] T054 [US6] Dreaming REST (`GET` status, `enable`/`disable`/`trigger`) in `backend/dreaming/api.py` (manual trigger runs a real sweep; audited `dreaming.*`) — **live-validated** (status 200, trigger 200). Sweep-review panel: deferred with frontend.

**Checkpoint**: All six user stories independently functional.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T055 [P] Add structured logs + metrics for new user-visible operations (schedule runs, sweeps, memory writes, grant mints) per Constitution X
- [X] T056 [P] Documentation: new endpoints render at `/docs` (routers tagged + registered); operator note that the Keycloak realm must request `offline_access` and set Offline Session Max ≥ 365 days lives in `docs/keycloak-realm-settings.md` (the stale `keycloak-persistent-login-realm-settings.md` reference fixed in 030 T032).
- [ ] T057 Lead-dev **security review** of the offline-grant store (encryption at rest, revocation, 365-day cap, no token egress) — sign-off recorded in PR (Constitution VII)
- [ ] T058 [P] Verify SC-009 (0 new frontend primitive types) and SC-010 (only the approved PHI dependency added); run `ruff check .` and frontend ESLint
- [ ] T059 Run [quickstart.md](quickstart.md) end-to-end in staging (scheduler + offline-grant + onboarding) per Constitution X; confirm ≥90% coverage on changed code

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup; **blocks all user stories**.
- **User Stories (Phase 3–8)**: all depend on Foundational. Recommended priority order P1 → P2 → P3. Cross-story notes:
  - US3 (personality) and US4 (memory) build on US1's profile endpoints (T017) and the shared injection point (T010/T011).
  - US6 (dreaming) depends on US4 (memory/signals: T035/T037) and US5 (scheduler: T047).
  - US5 is otherwise independent (its own scheduler/offline-grant), needing only Foundational.
- **Polish (Phase 9)**: depends on the targeted stories being complete; T057 gates US5 merge.

### Within Each User Story

- Tests written first and expected to fail before implementation.
- Repository/store → service → endpoints/UI → orchestrator integration.

### Parallel Opportunities

- Setup: T003 ∥ others.
- Foundational: T005, T006, T008, T009 are [P] (distinct files); T010 needs T009; T011 needs T010; T012 needs T011.
- US1: T013/T014/T015 (tests) ∥; T016/T018 ∥.
- US5: T039/T040 (tests) ∥; T043/T044/T045 ∥ (distinct files) before T046/T047.
- Across teams once Foundational is done: US5 can proceed fully in parallel with US1–US4; US6 waits on US4+US5.

---

## Parallel Example: User Story 1

```bash
# Tests together:
Task: "Contract test GET/PUT/DELETE /api/personalization/profile (T013)"
Task: "Contract test GET /api/onboarding/personalize/{step} (T014)"
Task: "Integration test onboarding round-trip + run-once (T015)"

# Then parallel implementation starters:
Task: "Personalization schemas (T016)"
Task: "Seed personalization tutorial steps (T018)"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (critical) → 3. Phase 3 US1 → **STOP & validate** the personalized-onboarding journey → demo. This alone delivers the headline value.

### Incremental Delivery

Foundation → US1 (MVP) → US2 (skills) → US3 (soul) → US4 (memory) → US5 (cron, gated by security review T057) → US6 (dreaming). Each story ships independently and is independently testable.

### Notes

- [P] = different files, no incomplete dependencies.
- Every new mutation emits an audit event (FR-033); confirm in tests.
- Memory/personalization writes always pass the PHI gate (T007); the gate is fail-closed.
- All new UI is server-generated from existing primitives — no new `DynamicRenderer` cases (SC-009).
- Commit after each task or logical group; stop at any checkpoint to validate a story.
