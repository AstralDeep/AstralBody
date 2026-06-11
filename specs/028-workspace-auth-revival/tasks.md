# Tasks: Persistent SDUI Workspace & Revived Keycloak Authentication

**Input**: Design documents from `specs/028-workspace-auth-revival/` (plan.md, research.md D1–D18, data-model.md, contracts/)
**Branch**: `028-workspace-auth-revival`

Format: `[ID] [P?] [Story] Description` — `[P]` = parallelizable with neighbors; file paths are repo-relative.

## Phase 1: Setup

- [x] T001 Add `ASTRAL_ENV` to `backend/agentic_settings.py` (or the existing env module) with `production` default when unset; update `.env.example` (`ASTRAL_ENV=development` beside `USE_MOCK_AUTH=true`, new `WEB_SESSION_ENC_KEY` documented) (research D7)
- [x] T002 Idempotent migrations in `backend/shared/database.py::_init_db()`: `web_session`, `auth_revocation_queue`, `workspace_snapshot` tables; `saved_components` columns `component_id`/`position`/`updated_at`; indexes per data-model.md

## Phase 2: Foundational (blocking prerequisites)

- [x] T003 Additive WS dataclasses `UIUpsert`, `AuthRequired` in `backend/shared/protocol.py` (contracts/ws-workspace-protocol.md, auth-session.md)
- [x] T004 New `backend/orchestrator/session_store.py`: Fernet-encrypted `web_session` CRUD, hard-cap checks, revocation-queue enqueue/worker (research D3/D5)
- [x] T005 New `backend/orchestrator/workspace.py` `WorkspaceManager`: component-identity resolution (`Primitive.id` → fingerprint, D11), upsert/remove with stable rows + position, snapshot writes, live/timeline reads
- [x] T006 `backend/webrender/renderer.py`: wrap top-level components in `<div class="astral-component" data-component-id="…">`; fragment-render helper for single components (D12)
- [x] T007 [P] `backend/audit/hooks.py`: action types `auth.logout`, `auth.token_refresh_failed` (class `auth`); `workspace.component_added/updated/removed`, `workspace.action_denied`, `workspace.timeline_viewed` (class `conversation`)

**Checkpoint**: migrations apply cleanly on existing data; new modules import; nothing user-visible changed yet.

## Phase 3: User Story 1 — Sign-in required to enter the app (P1)

- [x] T008 [US1] `backend/orchestrator/web_auth.py`: `next` param (validated relative path) through `/auth/login`→`_PENDING`→`/auth/callback`; bounded ungated error page for IdP/callback failures; user-switch revocation at callback (D1/D6)
- [x] T009 [US1] `backend/orchestrator/orchestrator.py::serve_shell`: 302 unauthenticated → `/auth/login?next=…`; no shell markup pre-auth
- [x] T010 [P] [US1] New `backend/tests/test_auth_gate.py`: gate redirect, next preservation + open-redirect guard, no-role refusal, error-page loop bound, mock-mode passthrough

**Checkpoint**: US1 independently testable (real-auth mode requires login; dev mode unchanged).

## Phase 4: User Story 2 — Stay signed in without interruption (P1)

- [x] T011 [US2] `web_auth.py`: `_ensure_fresh()` silent refresh (60 s window, ±5 min skew, rotate refresh token, never move anchor, hard-cap refusal); wire into `session_token()`, `/auth/session`, shell gate (D2)
- [x] T012 [US2] `web_auth.py` + `session_store.py`: `_SESSIONS` becomes read-through cache over `web_session` (restart/multi-worker survival, D3)
- [x] T013 [US2] `orchestrator.py` + `backend/webrender/static/client.js`: replace register_ui failure alert with `auth_required`; client refetches `/auth/session` before reconnect/retry then redirects with `next` if dead; remove `'dev-token'` literal fallback (D4)
- [x] T014 [P] [US2] Shared JWKS cache (TTL + kid-miss refetch) for `orchestrator.validate_token` and `orchestrator/auth.py::get_current_user_payload` (D8)
- [x] T015 [P] [US2] New `backend/tests/test_session_store_refresh.py`: refresh rotation, anchor immutability, hard-cap, restart survival (new store instance), refresh-failure → session dead + audit

**Checkpoint**: 016 resume matrix passes under real auth; restart logs nobody out.

## Phase 5: User Story 3 — Persistent workspace with in-place updates (P1)

- [x] T016 [US3] `orchestrator.py` provenance tagger (~2714): stamp `component_id` (D11) alongside `_source_*`; same in poll-stream tagger (~4821)
- [x] T017 [US3] `orchestrator.py`: route rich sends through `WorkspaceManager.upsert` → emit `ui_upsert` ops (replacing `_send_or_replace_components` `(tool,agent)` matcher); full `ui_render` now renders entire live workspace
- [x] T018 [US3] `client.js`: `ui_upsert` morph handler (querySelector by `data-component-id`, replace-else-append, scoped `processSideEffects`) per ws-workspace-protocol.md
- [x] T019 [US3] `orchestrator.py` LLM canvas prompt block (~2499): list live `component_id`s + updated COMPONENT UPDATE RULES (same id ⇒ in-place update)
- [x] T020 [P] [US3] New `backend/tests/test_workspace_manager.py` + `backend/tests/test_ui_upsert_render.py`: identity fingerprint vs explicit id, same-tool/different-params coexistence, stable row ids, wrapper/fragment golden tests

**Checkpoint**: multi-turn chats accumulate components; updates morph in place; pagination-era canvas wipes gone for new sends.

## Phase 6: User Story 4 — Re-open a chat and pick up where you left off (P2)

- [x] T021 [US4] `orchestrator.py::load_chat`: after `chat_loaded`, push full per-socket workspace `ui_render`; add server-rendered `html` to component-bearing transcript messages (D13)
- [x] T022 [US4] `client.js::chat_loaded`: render message `html` when content is structured (kill empty bubbles); stop wiping canvas before re-hydration render
- [x] T023 [P] [US4] New `backend/tests/test_rehydration.py`: workspace restored without tool re-runs; transcript html present; LLM canvas context == user-visible state (FR-029)

**Checkpoint**: close/reopen restores everything; old chats' transcripts render meaningfully.

## Phase 7: User Story 5 — Component interaction loop (P2)

- [x] T024 [US5] `orchestrator.py::handle_ui_message`: `component_action` pipeline per contracts/component-action.md (resolve → provenance+patch → CURRENT permission stack → execute → upsert target → snapshot → broadcast → audit; per-chat serialization; timeline guard)
- [x] T025 [US5] Re-express `table_paginate` as `component_action kind:'refresh'` alias (no canvas replacement); keep legacy action name mapped (FR-038)
- [x] T026 [US5] `client.js` + `renderer.py` buttons: deterministic actions carry `component_id` (`data-component-id` on `.astral-action` within component scope); param_picker documented intent path unchanged
- [x] T027 [P] [US5] New `backend/tests/test_component_action.py`: happy path in-place update, permission denial + audit, missing target graceful, cross-component target, params_patch merge, concurrency serialization

**Checkpoint**: refresh-style actions work permission-gated and in place.

## Phase 8: User Story 6 — Read-only workspace timeline (P2)

- [x] T028 [US6] Snapshot writes: per assistant turn (at message-persist points ~2767/2989/3014 — one snapshot per turn close), per component-action/combine/condense/remove (`WorkspaceManager.snapshot`, D14)
- [x] T029 [US6] New `backend/webrender/chrome/surfaces/workspace_timeline.py` (TITLE/render/HANDLERS: list 50/page, view snapshot → historical `ui_render` + banner, back-to-live) + topbar entry in `backend/webrender/chrome/topbar.py`; handlers dispatched via `chrome_events.py`
- [x] T030 [US6] `client.js` `timelineMode`: defer live canvas applications + "live has moved on" indicator; inert canvas actions; banner interactions
- [x] T031 [P] [US6] New `backend/tests/test_workspace_snapshots.py`: snapshot per cause, exact reproduction at turn N, CASCADE delete with chat, `workspace.timeline_viewed` audit, server-side timeline action refusal

**Checkpoint**: time-travel works read-only; live never mutated by viewing.

## Phase 9: User Story 7 — Sign out everywhere (P2)

- [x] T032 [US7] `web_auth.py::/auth/logout`: session-row delete (unconditional) → Keycloak revoke (best-effort) → `OfflineGrantStore.revoke_for_user` → `auth.logout` audit → end-session redirect; `auth_revocation_queue` worker on `BackgroundTaskManager` (D5)
- [x] T033 [P] [US7] New `backend/tests/test_logout_revocation.py`: revoke order, offline-tolerant local completion + queue retry, offline-grant revocation, user-switch path (D6)

## Phase 10: User Story 8 — Production fail-closed (P2)

- [x] T034 [US8] Startup gate in orchestrator init (mock auth + non-dev ⇒ fatal refusal); `orchestrator/auth.py::validate_agent_api_key` fail-closed outside dev (D7)
- [x] T035 [P] [US8] New `docs/keycloak-realm-settings.md` (FR-017); fix CLAUDE.md dangling reference; scrub real client secret from `docs/keycloak_agent_delegation_setup.md` (FLAG rotation in PR)
- [x] T036 [P] [US8] New `backend/tests/test_fail_closed_boot.py`: refusal matrix (env × mock × agent key), dev-mode passthrough

## Phase 11: User Story 9 — Multi-device consistency (P3)

- [x] T037 [US9] `orchestrator.py`: fan out `ui_upsert`/workspace renders to all user sockets with `_ws_active_chat == chat_id`, per-socket ROTE adapt + fragment render (D16); `backend/rote/rote.py` device-change re-adapt reads full live workspace from server state instead of `_last_components` (D17)
- [x] T038 [P] [US9] Tests in `backend/tests/test_workspace_manager.py` (extend): two-socket broadcast with differing device profiles; device-change re-adapt renders whole workspace

## Phase 12: Polish & cross-cutting

- [x] T039 Legacy verb reconciliation (D18) in `orchestrator.py`/`backend/orchestrator/history.py`/`backend/orchestrator/api.py`: save_component deprecated alias; get/delete map to workspace (+`ui_upsert op:'remove'` + snapshot); combine/condense write through `WorkspaceManager`; legacy WS messages still emitted
- [x] T040 [P] Fix `backend/webrender/chrome/guide_content.py` removed-page text; deprecation docstring on `POST /auth/token` (D10)
- [x] T041 `ruff check .` clean on all 028-touched files (20 pre-existing violations fixed; 0 introduced); full `python -m pytest` green — 13 reds triaged: 5 were interference from the concurrent evidence run, 8 were pre-existing test defects (stale mocks / `get_event_loop` on py3.13 / stale 013 auth expectation) now fixed; changed-code coverage measured via `backend/tmp/e2e/t041_changed_cov.py`
- [x] T042 Real-browser evidence gate per quickstart.md walkthrough → [evidence/t042/](evidence/t042/EVIDENCE.md) (EVIDENCE.md + 14 screenshots + boot log + 4 machine reports; Constitution X). A2–A4 environment-constrained (no realm credentials), compensated by `test_session_store_refresh.py`/`test_logout_revocation.py`
- [x] T043 [P] CLAUDE.md: add feature-028 section (auth lifecycle + workspace protocol summary)

## Phase 13: Post-T042 audit remediation (2026-06-11 FR-by-FR audit)

A 51-agent adversarial audit of the finished branch confirmed 21 FRs fully implemented/tested and surfaced the gaps below — all closed:

- [x] T044 FR-016 **wiring**: `validate_agent_api_key` had no production call site. `RegisterAgent` gained additive `api_key`; `Orchestrator.register_agent` refuses keyless/invalid registrations (closes WS 1008) outside dev; `BaseA2AAgent` sends `AGENT_API_KEY`; internal A2A discovery path carries the orchestrator's own key (`backend/tests/test_agent_key_enforcement.py`)
- [x] T045 FR-003/004/005 callback hardening: OIDC `error` param handled; `next` recovered before every error exit; IdP-unreachable preflight at `/auth/login` (3 s probe, 60 s cache, bounded 503 page); role gate at callback — token without `user`/`admin` → 403 no-access page, refresh token revoked, `login_interactive outcome=failure` audited (`backend/tests/test_auth_callback_paths.py`)
- [x] T046 CT-auth conformance: `/auth/session` reason `hard_cap` threaded from both cache and store deletions; one-shot `resumed` semantics (server-derived; shell injects `__ASTRAL_RESUMED__`, client echoes it — FR-011 meaning drift fixed); `_secret()` falls back through `WEB_SESSION_ENC_KEY`; contract docs amended where reality was chosen (auth_required reasons, timeline entry verb `chrome_open`, `invoke`-as-alias)
- [x] T047 FR-019: single-source supersede exempted for explicit author identities (a NEW `au_`/echoed id always appends) (`backend/tests/test_workspace_identity_028.py`)
- [x] T048 FR-026/T039 REST reconciliation: `save_component`/`delete_component`/`combine`/`condense` now write through `WorkspaceManager` with `ui_upsert`/snapshot/audit like their WS twins; `_reconcile_legacy_replacement` fans out when REST-initiated (`backend/tests/test_rest_legacy_workspace.py`)
- [x] T049 component_action `kind` validated (`refresh`/`invoke` accepted; unknown → Alert + `workspace.action_denied unsupported_kind:*`); `load_chat` ends a stale timeline view; chat deletion ends historical views on other tabs (`chat_deleted` + timeline-mode clear — spec EC) (`backend/tests/test_component_action_extras.py`, `tests/chrome/test_surface_workspace_timeline.py`)
- [x] T050 DM conformance: `workspace_snapshot.turn_message_id` FK → `messages(id) ON DELETE CASCADE` added idempotently (named constraint, `NOT VALID` for historic rows)
- [x] T051 Test-gap closure: ~13 new test files covering ensure_session/auth_session decision layer, register_ui→`auth_required`, JWKS cache, snapshot turn sites, real offline-grant lifecycle (EC-3), real audit-hook emission (FR-023), client.js/shell source-level contract (Constitution III compensation for the no-JS-harness rule), concurrency serialization (EC-7), non-BROWSER `ui_upsert` adaptation (T038 debt)
- [x] T052 Dev-environment repair: `.env` gained `ASTRAL_ENV=development` (the missing key made the 028 fail-closed posture reject the local stack — the "403 guardrail"); stale `test_agent_flow.py` rewritten against the real `/ws` endpoint (it previously swallowed its own connection failure); libmagic dependency drift fixed (`image/x.nifti`/`image/x.nrrd` accepted for `.nii`/`.nrrd`); `TOOL_REGISTRY` test pollution fixed

## Dependencies & Execution Order

- Phase 1 → Phase 2 → everything else. T005/T006 block all of Part B; T004 blocks T011–T012, T032.
- Stories: US1 (T008–T010) and US2 (T011–T015) are ordered (gate before refresh is testable end-to-end, but T011 can start in parallel after T004). US3 (T016–T020) blocks US4/US5/US6/US9. US7/US8 independent after Phase 2.
- Polish last; T042 is the final gate.

## Parallel Example

After Phase 2: `{T008, T011, T016}` may proceed in parallel (different modules); their test tasks `{T010, T015, T020}` in parallel after each lands.

## Implementation Strategy (MVP first)

MVP = Phases 1–5 (gate + continuity + persistent workspace): delivers both P1 pillars. Then US4 → US5 → US6 → US7/US8 → US9 → Polish. Each checkpoint leaves the branch deployable.
