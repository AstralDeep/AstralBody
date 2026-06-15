---
description: "Task list for 030-finish-soul-integration"
---

# Tasks: Finish Soul Integration

**Input**: Design documents from `/specs/030-finish-soul-integration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED. The deferred pytest-TestClient contract/integration tests are in-scope for this feature (FR-015) and are first-class tasks.

**Organization**: Tasks are grouped by user story (priority order). Each `*(closes 025 Txx)*` / `*(closes 029 Txx)*` annotation traces the task back to the audited gap in the prior spec.

**Conventions**: All backend paths are under `backend/`. Run tests via the root `.venv` against docker postgres with `ASTRAL_ENV=development` (see quickstart.md). No new third-party libraries (FR-022). Server-driven UI only (FR-023).

> **Implementation status (2026-06-15):** 30 of 40 tasks complete and locally test-passing (full suite green except a pre-existing `AstralBody`/`AstralDeep` rebrand assertion in `tests/test_webui_serving.py`, unrelated to this feature). The remaining tasks are **partial or human-gated**, left unchecked on purpose:
> - **T002** baseline coverage capture — not formally recorded.
> - **T007** full grant-backed scheduler e2e — only the dreaming-routing + fail-closed-gate paths are tested (`test_runner_dreaming.py`, `test_execution_gate.py`); the grant-backed run e2e is part of the T009/T010 gated path.
> - **T009** offline-grant **security sign-off** — analysis written (`security-review.md`); the sign-off is a lead-dev decision. `FF_SCHEDULER_EXECUTION` stays OFF until then.
> - **T010** WS offline-grant **consent capture** — deferred to the T057-gated path (secure session→refresh-token retrieval); the `set_offline_grant` receiver (T011) is in place.
> - **T016 / T023** LLM round-trip + full onboarding integration tests — covered at unit level (`test_memory_chat.py`, `test_onboarding_submit.py`); the full orchestrator round-trip is not yet written.
> - **T035** changed-code coverage ≥90% — run `diff-cover` on the PR.
> - **T038/T039/T040** quickstart/staging/CI — run on the PR / live stack.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US6 per spec.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Reproducible local verification environment matching the production image.

- [X] T001 Sync the root `.venv` to `backend/requirements.txt` (`pip install -r backend/requirements.txt --upgrade`) and start docker postgres (`docker compose up -d postgres`); confirm `from a2a.types import SecurityRequirement` and `from astralprims import Hero` both import.
- [ ] T002 [P] Capture baseline: run both CI pytest invocations + `diff-cover coverage.xml --compare-branch origin/main` and record the starting changed-code coverage in `specs/030-finish-soul-integration/research.md`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The execution gate + orchestrator seams that US1 (and dreaming execution in US4) depend on.

**⚠️ CRITICAL**: US1 and US4 execution cannot be completed until this phase is done.

- [X] T003 Add `FF_SCHEDULER_EXECUTION` flag (default **False**) to `backend/shared/feature_flags.py`, documented as the fail-closed gate for unattended execution (distinct from the existing `scheduling_chat` proposal flag). *(FR-005)*
- [X] T004 Implement `Orchestrator.run_scheduled_turn(*, user_id, chat_id, instruction, agent_id, access_token, allowed_scopes, correlation_id) -> str` in `backend/orchestrator/orchestrator.py` per `contracts/orchestrator-seams.md` (background chat turn via BackgroundTaskManager + VirtualWebSocket under the delegated token, output persisted to chat history). *(FR-001; closes 025 T040/T046)*
- [X] T005 Implement `Orchestrator.notify_user(user_id, payload)` in `backend/orchestrator/orchestrator.py` (fan-out to all of the user's sockets via `_safe_send`/`ui_clients` + persist for offline delivery + audit) per `contracts/orchestrator-seams.md`. *(FR-002; closes 025 T049)*
- [X] T006 Gate the scheduler execution loop start on `FF_SCHEDULER_EXECUTION` AND a recorded sign-off in `backend/orchestrator/orchestrator.py` (loop-start site ~line 6500) and `backend/scheduler/loop.py`; when ungated the loop MUST NOT start (fail-closed). *(FR-005)*

**Checkpoint**: Seams exist and the loop is fail-closed by default. User stories can begin.

---

## Phase 3: User Story 1 - Scheduled work runs safely or not at all (Priority: P1) 🎯 MVP

**Goal**: Consented jobs execute unattended with in-app notifications when the security gate is satisfied; otherwise the loop is provably off and reported unavailable — never live-but-broken.

**Independent Test**: Create a one-shot job due now; with the gate enabled it runs, persists output, and notifies; with the gate disabled the loop does not start and no execution path is reachable; a revoked grant yields `skipped_auth` + pause + notify.

### Tests for User Story 1 ⚠️

- [ ] T007 [P] [US1] Scheduler end-to-end test in `backend/tests/test_scheduler_e2e.py`: run timing (SC-001), scope intersection + `skipped_auth` (SC-008/FR-006), restart recovery, and notification delivery. *(closes 025 T040)*
- [X] T008 [P] [US1] Fail-closed gate test in `backend/tests/test_scheduler_e2e.py` (or `backend/scheduler/tests/`): with `FF_SCHEDULER_EXECUTION` false the loop does not start and no job-execution path is reachable. *(SC-002/FR-005)*

### Implementation for User Story 1

- [ ] T009 [US1] Conduct + record the lead-dev security review of `backend/orchestrator/offline_grant.py` (encryption at rest, revocation, lifetime cap, scope intersection, no token egress) as `specs/030-finish-soul-integration/security-review.md`, referenced in the PR; only after this may `FF_SCHEDULER_EXECUTION` be enabled. *(FR-004; closes 025 T057)*
- [ ] T010 [US1] Add WS `offline_grant_request`/`offline_grant_ack` consent handlers in `backend/orchestrator/chrome_events.py` per `contracts/websocket-events.md`; on ack call `OfflineGrantStore.capture(...)` and obtain the `grant_id` (idempotent on `request_id`, audited). *(FR-003; closes 025 T042)*
- [X] T011 [US1] Write the captured `offline_grant_id` onto the job at creation in `backend/scheduler/store.py` / `backend/scheduler/api.py` / `backend/orchestrator/scheduling_chat.py` (replace the hard-coded `None`). *(FR-003)*
- [X] T012 [US1] Emit structured logs/metrics on run success in `backend/scheduler/runner.py` (step 5) with `extra={job_id, outcome, ...}`. *(FR-017)*
- [X] T013 [US1] Make the scheduling chrome surface report "unattended execution unavailable" when `FF_SCHEDULER_EXECUTION` is off, in `backend/webrender/chrome/surfaces/` (scheduling/personalization surface). *(FR-005)*

**Checkpoint**: Scheduled jobs are safe — they run correctly when gated on, and are inert + honest when gated off.

---

## Phase 4: User Story 2 - The assistant can remember and recall on request (Priority: P1)

**Goal**: The LLM can call memory tools (remember / search / get) during chat, gated by enablement and the PHI gate; passive recall is unchanged.

**Independent Test**: Ask the assistant to remember a non-PHI fact, then recall it in a later turn; confirm PHI content is refused.

### Tests for User Story 2 ⚠️

- [X] T014 [P] [US2] Unit tests for `backend/orchestrator/memory_chat.py` in `backend/orchestrator/tests/test_memory_chat.py`: `meta_tool_definitions()` shape, `should_inject()` gating, `handle_meta_tool()` dispatch + PHI refusal.
- [X] T015 [P] [US2] Contract test for `GET /api/memory`, `PUT/DELETE /api/memory/{id}` in `backend/personalization/tests/test_memory_api.py` (FastAPI TestClient). *(closes 025 T033)*
- [ ] T016 [P] [US2] Integration test in `backend/tests/integration/test_memory_round_trip.py`: LLM `remember` → `memory_get`/`memory_search` via the orchestrator dispatch path.

### Implementation for User Story 2

- [X] T017 [US2] Create `backend/orchestrator/memory_chat.py` mirroring `scheduling_chat.py` (`META_AGENT_ID="__memory__"`, `meta_tool_definitions()`, `should_inject()`, `handle_meta_tool()` dispatching to `backend/personalization/memory_tools.py` through the PHI gate + audit) per `contracts/memory-meta-tool.md`. *(FR-007; closes 025 T036)*
- [X] T018 [US2] Inject the memory meta-tool into the chat tool list and add the `agent_id == "__memory__"` dispatch branch in `backend/orchestrator/orchestrator.py` (alongside `__scheduler__`/`__orchestrator__`, ~lines 2814-2820 and ~4199-4210). *(FR-007/FR-008)*
- [X] T019 [US2] Emit a structured log/metric on memory write in `backend/personalization/memory_tools.py` (`remember`/`capture_signal`). *(FR-017)*

**Checkpoint**: The assistant actively stores and recalls memory on request; PHI is blocked.

---

## Phase 5: User Story 3 - Onboarding actually personalizes the assistant (Priority: P2)

**Goal**: Onboarding submits persist the profile + enabled skills, and enabled-skill guidance reaches the prompt; returning users are not re-onboarded.

**Independent Test**: Complete onboarding enabling a skill + personality; confirm persistence and behavior change; return and confirm no re-prompt.

### Tests for User Story 3 ⚠️

- [X] T020 [P] [US3] Contract test for `GET/PUT/DELETE /api/personalization/profile` in `backend/personalization/tests/test_profile_api.py`. *(closes 025 T013)*
- [X] T021 [P] [US3] Contract test for `GET /api/onboarding/personalize/{step}` returning ParamPicker `_ui_components` in `backend/onboarding/tests/test_personalize_steps.py`. *(closes 025 T014)*
- [X] T022 [P] [US3] Contract test for `GET/PUT /api/skills` incl. FR-011 scope-gating `403` in `backend/personalization/tests/test_skills_api.py`. *(closes 025 T024)*
- [ ] T023 [P] [US3] Integration test for the full onboarding round-trip + run-once + skip/resume in `backend/tests/integration/test_onboarding_personalization.py`. *(closes 025 T015)*

### Implementation for User Story 3

- [X] T024 [US3] Interpret onboarding ParamPicker `submit_message_template` submissions in `backend/orchestrator/orchestrator.py` (mirror the scheduling submit path) and persist profile + enabled skills via the existing personalization endpoints/repository. *(FR-009; closes 025 T021)*
- [X] T025 [US3] Populate the dead `personalization_skill_lines` call site (`backend/orchestrator/orchestrator.py` ~line 2925) from the user's enabled skills so guidance reaches the prompt. *(FR-010; closes 025 T028)*
- [X] T026 [US3] Enforce skill scope-gating on enable during onboarding (reuse `personalization/api.py` guard) in the submit-interpretation path. *(FR-011)*

**Checkpoint**: Onboarding selections persist and change assistant behavior; returning users keep their preferences.

---

## Phase 6: User Story 4 - Background consolidation runs automatically (Priority: P2)

**Goal**: Dreaming runs on a per-user recurring schedule by default and honors the enable flag.

**Independent Test**: For a dreaming-enabled user a recurring job exists and fires; disabling stops it; re-enabling resumes it.

### Tests for User Story 4 ⚠️

- [X] T027 [P] [US4] Test per-user dreaming job registration + enable/disable honoring in `backend/dreaming/tests/test_dreaming_schedule.py`.

### Implementation for User Story 4

- [X] T028 [US4] Register a per-user recurring dreaming `scheduled_job` using `DREAMING_DEFAULT_CRON` (`backend/agentic_settings.py:44`) on personalization init/enable in `backend/personalization/service.py`. *(FR-013; closes 025 T053)*
- [X] T029 [US4] Honor `dreaming_enabled`: pause/remove the job on disable, resume on enable (no restart) in `backend/personalization/service.py` / `backend/dreaming/api.py`. *(FR-014)*
- [X] T030 [US4] Route dreaming jobs to the consolidation sweep and emit structured logs/metrics on sweep in `backend/dreaming/consolidation.py`. *(FR-013/FR-017)*

**Checkpoint**: Dreaming runs automatically for enabled users and stops for disabled users.

---

## Phase 7: User Story 5 - The completed work is trustworthy and production-ready (Priority: P3)

**Goal**: Coverage ≥90% on changed code, structured observability for all background ops, accurate operator docs, recorded SC verification, and reconciled prior-spec bookkeeping.

**Independent Test**: Coverage gate passes; each background op emits a structured log; docs resolve; checkboxes match code.

- [X] T031 [P] [US5] Emit structured log/metric on grant-mint success in `backend/orchestrator/offline_grant.py` (`mint_access_token`). *(FR-017; closes 025 T055)*
- [X] T032 [P] [US5] Update `docs/keycloak-realm-settings.md` (offline_access + Offline Session Max ≥365d) and fix the stale `keycloak-persistent-login-realm-settings.md` reference in `specs/025-agentic-soul-integration/quickstart.md`. *(FR-018; closes 025 T056)*
- [X] T033 [P] [US5] Record SC-009/SC-010 verification (no new third-party runtime libs; no new UI primitive types) in the PR description and a `specs/030-finish-soul-integration/` note. *(FR-019; closes 025 T058)*
- [X] T034 [US5] Reconcile `specs/025-agentic-soul-integration/tasks.md`: mark T022 done (chrome surface `webrender/chrome/surfaces/personalization.py`, not the deleted React frontend) and T050 done (`scheduling_chat.py`); annotate T018 as archived by the 030 rewrite. *(FR-020)*
- [ ] T035 [US5] Bring changed-code coverage to ≥90% (`diff-cover` vs `origin/main`); add tests for any uncovered changed lines. *(FR-016; closes 025 T059)*

**Checkpoint**: The feature meets the merge gate and is observable, documented, and honestly tracked.

---

## Phase 8: User Story 6 - Retired agents leave no trace in the knowledge base (Priority: P3)

**Goal**: The regenerated knowledge index contains zero references to retired/merged agents, durably.

**Independent Test**: The five agents' knowledge files are absent and `_index.md` has no entries for them after regeneration.

- [X] T036 [P] [US6] Durably remove `grants`, `nefarious`, `classify`, `forecaster`, `llm_factory` knowledge files (both `backend/knowledge/capabilities/` and `backend/knowledge/techniques/`) from disk and the image build context. *(FR-021; closes 029 T018/T023)*
- [X] T037 [US6] Ensure `KnowledgeSynthesizer._update_index()` (`backend/orchestrator/knowledge_synthesis.py`) regenerates `_index.md` with 0 refs to the five agents; add a guard/test so re-discovery cannot resurrect retired-agent entries. *(FR-021/SC-008)*

**Checkpoint**: Retired agents are gone from the knowledge index and stay gone.

---

## Phase 9: Polish & Cross-Cutting

- [ ] T038 [P] Run `quickstart.md` §1–§8 locally (root `.venv` + docker postgres, `ASTRAL_ENV=development`); capture results.
- [ ] T039 Staging end-to-end validation (Constitution X): scheduler + offline-grant consent + onboarding + dreaming against the live backend in a real browser; record evidence in the PR.
- [ ] T040 Confirm the CI pipeline (lint / tests / coverage ≥90% / build / boot-smoke / secret-scan) runs green end-to-end on the PR.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — start immediately.
- **Foundational (Phase 2)**: after Setup. Blocks US1 (and US4 execution).
- **US1 (Phase 3)**: after Foundational. MVP.
- **US2 (Phase 4)**: after Setup; independent of US1 (no shared files except the orchestrator injection site — coordinate T018 with T004/T005 edits).
- **US3 (Phase 5)**: after Setup; independent (touches onboarding submit path; coordinate orchestrator edits with US2 T018).
- **US4 (Phase 6)**: after Foundational (uses `run_scheduled_turn` for sweep execution).
- **US5 (Phase 7)**: after the stories whose code it covers/documents (coverage T035 last; observability tasks can land with their story).
- **US6 (Phase 8)**: independent — can run any time after Setup.
- **Polish (Phase 9)**: after all targeted stories.

### Critical path (MVP)

T001 → T003/T004/T005/T006 (Foundational) → T009 (security review) → T010/T011 (consent + grant id) → T007/T008 (tests) → T012/T013 → US1 done.

### Parallel Opportunities

- T002 in Setup.
- US6 (T036/T037) is fully parallel to everything else.
- Within a story, the `[P]` test tasks run together.
- US2, US3, US5-docs, US6 can proceed in parallel once Setup is done; serialize only the shared `orchestrator.py` injection edits (T004/T005/T018/T024/T025).

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup → Phase 2 Foundational → Phase 3 US1.
2. **STOP & VALIDATE**: scheduled jobs run safely or are provably off. This resolves the highest-risk audit finding (live-but-broken scheduler under unreviewed authority).

### Incremental Delivery

US1 (scheduler safe) → US2 (memory) → US3 (onboarding) → US4 (dreaming) → US5 (quality/coverage/bookkeeping) → US6 (knowledge cleanup). Each is independently testable and adds value without breaking the previous.

---

## Notes

- `[P]` = different files, no incomplete dependencies.
- The biggest serialization risk is concurrent edits to `backend/orchestrator/orchestrator.py` (T004, T005, T006, T018, T024, T025) — sequence those even though they belong to different stories.
- Do NOT enable `FF_SCHEDULER_EXECUTION` until T009 (security review) is recorded.
- Commit after each task or logical group; reference the original 025/029 task IDs in commit messages.
