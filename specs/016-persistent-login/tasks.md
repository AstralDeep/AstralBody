---

description: "Tasks for 016-persistent-login — credential storage so users do not have to log in every time they open the website or app (365 days)"
---

# Tasks: Persistent Login Across App Restarts (Web + Flutter Wrapper)

**Input**: Design documents from `/specs/016-persistent-login/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: REQUIRED by Constitution III (≥90% coverage) and Constitution X (production-ready merges). Every implementation task is paired with tests in the same phase.

**Organization**: Tasks are grouped by user story (US1–US4) to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Setup / Foundational / Polish phases carry no Story label.

## Path Conventions

This is a web application with a Flutter WebView wrapper:

- `backend/` — Python (FastAPI)
- `frontend/src/` — TypeScript on Vite + React 18
- `flutter-passthrough/` — Dart (untouched this feature)
- `docs/` — operator-facing notes (Keycloak realm settings)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton for the new auth helper.

- [X] T001 Create directory `frontend/src/auth/` with an empty `index.ts` re-export stub so subsequent files have a stable import path
- [X] T002 [P] Create directory `frontend/src/auth/__tests__/` (Vitest will pick it up automatically; no config change needed)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared building blocks every user story depends on. Backend protocol/audit changes + the three frontend helper modules + their unit tests. Implementing the helpers and their unit tests in lock-step keeps Constitution III coverage continuously green.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Backend protocol + audit foundations

- [X] T003 Extend `RegisterUI` dataclass with optional `resumed: bool = False` field in [backend/shared/protocol.py](../../backend/shared/protocol.py) (backward-compatible — older clients omit the field and are treated as `false`)
- [X] T004 [P] Update the orchestrator WS register handler in [backend/orchestrator/orchestrator.py](../../backend/orchestrator/orchestrator.py) to read `RegisterUI.resumed` and select the `action_type` per [contracts/audit-actions.md](contracts/audit-actions.md) §2 — `auth.login_interactive` (resumed=false, success), `auth.session_resumed` (resumed=true, success), or `auth.session_resume_failed` (resumed=true, failure)
- [X] T005 [P] Add `POST /api/audit/session-resume-failed` REST endpoint in [backend/audit/api.py](../../backend/audit/api.py) per [contracts/audit-actions.md](contracts/audit-actions.md) §3 (accepts unauthenticated; records anonymous when no bearer)
- [X] T006 [P] Add `backend/audit/tests/test_session_resume_actions.py` with the five test cases listed in [contracts/audit-actions.md](contracts/audit-actions.md) §6 — must fail before T003–T005 land, must pass after

### Frontend foundational helpers (each with paired unit tests)

- [X] T007 [P] Create `SafeWebStorageStateStore` in `frontend/src/auth/safeStorageStore.ts` — subclasses `WebStorageStateStore` from `oidc-client-ts`; wraps `set()` in try/catch that swallows `QuotaExceededError` / `SecurityError`, emits a `console.warn`, and dispatches a `window.dispatchEvent(new CustomEvent('astralbody:persistence-disabled'))` for the UI toast (R-10)
- [X] T008 [P] Unit tests for `SafeWebStorageStateStore` in `frontend/src/auth/__tests__/safeStorageStore.test.tsx` — assert: write success path; write throws → no exception escapes; write throws → `astralbody:persistence-disabled` event fires exactly once per session
- [X] T009 [P] Create `frontend/src/auth/persistentLogin.ts` with the public API from [data-model.md](data-model.md) §"Read/Write operations" — `recordInteractiveLogin(sub)`, `getAnchor()`, `clear()`, `checkOnLaunch()`, `wasSilentResume(auth)`, plus internal helpers for the 365-day hard-cap and the `deployment_origin` check
- [X] T010 [P] Unit tests for `persistentLogin.ts` in `frontend/src/auth/__tests__/persistentLogin.test.tsx` — assert: anchor write/read round-trip; `checkOnLaunch` clears OIDC + anchor when `now - initial_login_at > 365 days` (FR-013); `checkOnLaunch` clears both records on `deployment_origin` mismatch (FR-007); `wasSilentResume` returns false right after `onSigninCallback`, true on subsequent reads (FR-015); invariants I-1 through I-6 from data-model.md. **Additional cases** (closes /speckit-analyze CG1 + I12): (i) **clock-skew leeway (FR-010)** — construct a `User` with `expires_at = now + 60s` and a faked system clock 200 s ahead; assert `oidc-client-ts` still treats the access token as valid (the default `clockSkewInSeconds: 300` is honored end-to-end); (ii) **unknown schema_version** — write `astralbody.persistentLogin.v1` with `schema_version: 99`; assert `checkOnLaunch()` discards the record and routes to login (no corrupt/stuck state — matches the "Flutter app upgrade changes storage keys" edge case in spec.md)
- [X] T011 [P] Create `frontend/src/auth/revocationQueue.ts` per [research.md](research.md) §R-5 and [data-model.md](data-model.md) §"Record 3" — sessionStorage-backed, FIFO, 16-entry cap, 5-attempt-per-entry cap, drains on `online` event and on app launch
- [X] T012 [P] Unit tests for `revocationQueue.ts` in `frontend/src/auth/__tests__/revocationQueue.test.tsx` — assert: enqueue under cap; enqueue past cap evicts oldest; drain calls Keycloak revoke endpoint per entry; 4xx removes entry; 5xx/network increments attempts; 5 failed attempts drops entry; queue cleared after browser close (sessionStorage semantics)

**Checkpoint**: Foundation ready — backend records the three new `action_type` values correctly; frontend has three tested helper modules; user-story phases can now proceed in parallel.

---

## Phase 3: User Story 1 — Returning Web User Stays Signed In (Priority: P1) 🎯 MVP

**Goal**: Web users land directly on the dashboard after closing/reopening the browser, up to 365 days from their most recent interactive login.

**Independent Test**: Per [quickstart.md](quickstart.md) §"Smoke test — Web" — sign in, close browser, reopen, dashboard renders without login screen; localStorage holds both `oidc.user:*` and `astralbody.persistentLogin.v1` records.

### Tests for User Story 1

- [ ] T013 [P] [US1] Integration test in `frontend/src/__tests__/persistent_login_web.test.tsx` — render `<AuthProvider>` by importing the **exact production `oidcConfig`** from `frontend/src/auth/oidcConfig.ts` (extracted by T015 below — this closes /speckit-analyze I9 so a regression in T015 fails this test). Sign in via a mocked `oidc-client-ts` `UserManager`, unmount, remount; assert (a) the user is still authenticated, (b) `astralbody.persistentLogin.v1` is present with a recent `initial_login_at`, (c) **no `<LoginScreen />` element is ever rendered on the second mount** (closes CG8 — `screen.queryByTestId('login-screen')` MUST return `null` throughout the remount), and (d) **time from remount to first `data-testid="dashboard-ready"` paint ≤ 2 000 ms** measured via `performance.now()` (closes CG5 / SC-001).
- [ ] T014 [P] [US1] Test that `useWebSocket` includes `resumed: <bool>` in the `register_ui` payload in `frontend/src/hooks/__tests__/useWebSocket.test.tsx` — mock auth state with and without the `justInteractive` sessionStorage flag; assert the emitted message shape matches [contracts/ws-register-flag.md](contracts/ws-register-flag.md) §1

### Implementation for User Story 1

- [X] T015 [US1] Extract the OIDC configuration object from [frontend/src/main.tsx](../../frontend/src/main.tsx) into a new module `frontend/src/auth/oidcConfig.ts` (default export `oidcConfig`). Wire `userStore` and `stateStore` to `SafeWebStorageStateStore({store: window.localStorage})` inside that new module — the headline change. Import `SafeWebStorageStateStore` from `./safeStorageStore`. Update `main.tsx` to import `oidcConfig` from `./auth/oidcConfig` and pass it to `<AuthProvider {...oidcConfig}>`. This extraction also enables T013 to import the exact production config (closes /speckit-analyze I9).
- [X] T016 [US1] Update the existing `onSigninCallback` in `frontend/src/main.tsx` to call `persistentLogin.recordInteractiveLogin(user.profile.sub)` and set `sessionStorage.setItem("astralbody.justInteractive", "1")` immediately before the existing URL-cleanup logic. Note: `onSigninCallback` receives the `User` object as an argument in newer `react-oidc-context` versions; if the project's installed version doesn't, derive `sub` by parsing the just-created `oidc.user:*` localStorage record
- [X] T017 [US1] Call `persistentLogin.checkOnLaunch()` at module top in `frontend/src/main.tsx` (synchronously, before `createRoot(...).render(...)`) — this clears OIDC + anchor records on hard-max-exceeded or deployment-mismatch BEFORE the `<AuthProvider>` reads them
- [X] T018 [US1] Wire `wasSilentResume(auth)` into the `register_ui` payload sent by [frontend/src/hooks/useWebSocket.ts](../../frontend/src/hooks/useWebSocket.ts) — add a `resumed` field to the message object alongside the existing `device` field
- [X] T019 [US1] Add a one-time toast subscriber for the `astralbody:persistence-disabled` event in [frontend/src/App.tsx](../../frontend/src/App.tsx) using the existing `sonner` toaster — message: "We could not save your sign-in on this device; you'll be asked to sign in again next time."
- [ ] T020 [US1] Run the quickstart §"Smoke test — Web" end-to-end against a real running backend in Chrome and Firefox; document pass/fail in PR description

**Checkpoint**: Web users have full persistent login. Audit log shows correct `auth.login_interactive` / `auth.session_resumed` rows. MVP shippable here.

---

## Phase 4: User Story 2 — Returning Mobile App User Stays Signed In (Priority: P1)

**Goal**: Mobile users (iOS + Android via Flutter WebView) land directly on the dashboard after force-quit or reboot, up to 365 days.

**Independent Test**: Per [quickstart.md](quickstart.md) §"Smoke test — Flutter wrapper" — sign in inside the WebView, force-quit, reopen, dashboard renders without login screen; same after device reboot.

**Note**: This story has NO Flutter code changes (per [plan.md](plan.md) §"Structure Decision" and [research.md](research.md) §R-2). The work is validation that the web-side persistence already works inside `webview_flutter`'s default WebView. Since this is a validation-only phase, the tasks are smoke tests on real devices.

### Implementation for User Story 2

- [ ] T021 [US2] Manual smoke test per quickstart §"Smoke test — Flutter wrapper" on the iOS Simulator (latest stable). Document pass/fail in PR description; capture a screen recording showing force-quit + relaunch
- [ ] T022 [US2] [P] Manual smoke test per quickstart on the Android Emulator (API 33+). Document pass/fail; capture screen recording
- [ ] T023 [US2] [P] Repeat T021 with a full device reboot between force-quit and relaunch on a physical iOS device if available
- [ ] T024 [US2] [P] Repeat T022 with a full device reboot on a physical Android device if available
- [X] T025 [US2] Confirm by reading [flutter-passthrough/lib/webview_screen.dart](../../flutter-passthrough/lib/webview_screen.dart) and the `webview_flutter` plugin's default options that no `WebStorage.deleteAllData()` or equivalent call exists. Record the confirmation as a one-line comment in the PR — no code change

**Checkpoint**: Mobile parity confirmed. Both P1 stories complete.

---

## Phase 5: User Story 3 — User Can Sign Out and Be Forgotten (Priority: P2)

**Goal**: Sign-out clears local credentials unconditionally, queues server-side revocation, and survives the offline-at-signout case. User-switch on the same surface revokes the prior user's leftover credential.

**Independent Test**: Per [quickstart.md](quickstart.md) §"Smoke test — Sign-out flow" — sign out, verify localStorage records are gone within 1 s, reload the page returns to login, refresh-token replay against Keycloak returns `invalid_grant`.

### Tests for User Story 3

- [ ] T026 [P] [US3] Unit tests for the `signOut()` helper in `frontend/src/auth/__tests__/persistentLogin.test.tsx` (extend the file from T010) — assert: synchronous clear of `astralbody.persistentLogin.v1`; synchronous clear of `oidc.user:*`; revocation enqueued; `signoutRedirect` called even when revocation enqueue is the only successful step (offline path)
- [ ] T027 [P] [US3] Unit tests for user-switch detection in `frontend/src/auth/__tests__/persistentLogin.test.tsx` — assert: new login with a different `sub` than `last_user_sub` causes the prior refresh token to be enqueued before the anchor is overwritten; new login with the same `sub` does NOT enqueue revocation
- [ ] T028 [P] [US3] Integration test in `frontend/src/__tests__/persistent_login_signout.test.tsx` — full signout flow under simulated offline conditions; assert queue persists in sessionStorage and drains on the next `online` event

### Implementation for User Story 3

- [X] T029 [US3] Add `signOut()` helper to `frontend/src/auth/persistentLogin.ts` per [data-model.md](data-model.md) §"Record 2 Lifecycle / Explicit sign-out": synchronously remove anchor, snapshot the prior refresh token, enqueue revocation, then delegate to `userManager.signoutRedirect()` which clears the OIDC record and hits the end-session endpoint
- [X] T030 [US3] Update the `onSigninCallback` in `frontend/src/main.tsx` to compare `new sub vs last_user_sub` and enqueue revocation of the prior refresh token when they differ (FR-008). Must read the old OIDC record one tick before `oidc-client-ts` overwrites it
- [X] T031 [US3] Replace the raw `auth.signoutRedirect()` call in [frontend/src/App.tsx](../../frontend/src/App.tsx) (currently passed via the `Shell` `signOut` prop) with a call to `persistentLogin.signOut(auth)`
- [X] T032 [US3] Add a small "signed out locally, server confirmation pending" toast notice that subscribes to the revocationQueue's `enqueued-while-offline` event in `App.tsx`
- [ ] T033 [US3] Run the quickstart §"Smoke test — Sign-out flow" end-to-end **including the refresh-token replay step (required, not optional — this is the only way to verify SC-003's 100 % replay-rejection promise)**. Capture the refresh token from `oidc.user:*` localStorage immediately before clicking sign-out; after the sign-out flow completes (and the revocation queue drains), POST the captured token to `${authority}/protocol/openid-connect/token` with `grant_type=refresh_token`; assert the response is HTTP 400 `{"error":"invalid_grant"}`. Document the round-trip in the PR.

**Checkpoint**: Sign-out is trustworthy; user-switch closes the leftover-credential replay window.

---

## Phase 6: User Story 4 — Refresh Failure Recovers Gracefully (Priority: P2)

**Goal**: When silent resume fails (network, server, revoked, expired) the app shows a clear next step — never a blank screen, never an infinite spinner. 3-retry exponential backoff (1 s, 3 s, 9 s) before falling back to login.

**Independent Test**: Per [quickstart.md](quickstart.md) §"Smoke test — Offline silent-resume" + §"Smoke test — 365-day hard cap".

### Tests for User Story 4

- [ ] T034 [P] [US4] Unit tests for the 3-retry backoff in `frontend/src/auth/__tests__/persistentLogin.test.tsx` — assert: 5xx → retry at 1s, 3s, 9s then fall back; 4xx → fall back immediately, no retries; ≤13s wall-clock budget
- [ ] T035 [P] [US4] Integration test in `frontend/src/__tests__/persistent_login_failure.test.tsx` — simulate `navigator.onLine = false` at app launch with a valid stored credential; assert the existing offline retry UI renders, not the login screen, not an infinite spinner; reconnect and verify recovery
- [ ] T036 [P] [US4] Backend test in `backend/audit/tests/test_session_resume_actions.py` (extend the file from T006) — assert `POST /api/audit/session-resume-failed` records exactly one row with the expected fields and accepts both authenticated and anonymous requests

### Implementation for User Story 4

- [X] T037 [US4] Implement the retry policy inside `persistentLogin.ts` — wrap `userManager.signinSilent()` in a `retryWithBackoff()` helper that distinguishes transient (5xx, network) from definitive (4xx) failures per FR-011
- [X] T038 [US4] Implement offline-state detection in [frontend/src/App.tsx](../../frontend/src/App.tsx) — when `navigator.onLine === false` AND an anchor record exists AND `auth.user` is null, render the existing WS-disconnected banner from [frontend/src/hooks/useWebSocket.ts](../../frontend/src/hooks/useWebSocket.ts) (the same `connectionState !== 'connected'` indicator + retry button shown today when the orchestrator WS drops). Do NOT introduce a new offline component (closes /speckit-analyze A1). The banner MUST surface a retry control that calls `auth.signinSilent()` on click; do NOT render `<LoginScreen />` while offline state is active.
- [X] T039 [US4] After retry budget exhausted, POST to `/api/audit/session-resume-failed` from the frontend with `{reason: "retry-budget-exhausted", attempts: 3, last_error: …}` per [contracts/audit-actions.md](contracts/audit-actions.md) §3
- [X] T040 [US4] Make sure the 365-day hard-cap clear path (T009 / `checkOnLaunch`) ALSO POSTs `auth.session_resume_failed` with `reason: "token-expired"` so the audit log captures these silent expirations
- [ ] T041 [US4] Run quickstart §"Smoke test — Offline silent-resume" + §"Smoke test — 365-day hard cap" + §"Smoke test — Storage-write rejection" end-to-end

**Checkpoint**: All four user stories complete. All seven quickstart smoke tests pass.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Operator config docs, coverage verification, cross-browser/cross-OS validation.

- [X] T042 [P] Document required Keycloak realm settings in `docs/keycloak-realm-settings.md` per [research.md](research.md) §R-3 — Offline Session Idle ≥ 365 days, Offline Session Max ≥ 365 days (or 0=unlimited; client enforces 365), Access Token Lifespan 5–15 min, `offline_access` scope already requested by frontend
- [ ] T043 [P] Verify ≥90 % line coverage on changed files (`frontend/src/auth/*`, the modified hunks of `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/hooks/useWebSocket.ts`, `backend/shared/protocol.py`, `backend/orchestrator/orchestrator.py` WS register handler, `backend/audit/api.py`) — Constitution III gate. Use `vitest --coverage` + `pytest --cov` and attach the report to the PR. **Additionally** (closes /speckit-analyze C3 — Constitution VI gate): verify that every exported symbol under `frontend/src/auth/` carries a JSDoc block (at minimum a `@param`/`@returns`/short description on functions, and a short description on classes); ESLint rule `jsdoc/require-jsdoc` MUST pass on this directory with no exemptions. Attach the lint report to the PR.
- [ ] T044 [P] Verify Constitution X (production readiness): no `TODO`/`FIXME` without tracked-issue references; no debug-only code; no hardcoded URLs; structured logs for the three new audit action_types; observability sufficient to diagnose a "stuck on login screen" incident from logs alone
- [ ] T045 Run the full [quickstart.md](quickstart.md) on Chrome stable + Firefox stable + Safari (macOS) + iOS Simulator + Android Emulator. Document each pass/fail in the PR description with screenshots/recordings
- [ ] T046 Manual verification in staging that the Keycloak realm settings from T042 are applied and that an `offline_access` refresh token issued by staging still works after a simulated 366-day wait (achieved by adjusting the device clock OR by manually editing the local `initial_login_at` per quickstart §"Smoke test — 365-day hard cap")
- [X] T047 [P] Add a one-line entry under "Recent Changes" in [CLAUDE.md](../../CLAUDE.md) summarizing the feature for future context: "016-persistent-login: Added 365-day persistent login on web + Flutter wrapper. Frontend `oidc-client-ts` `userStore` swapped to localStorage; new `frontend/src/auth/` module enforces 365-day hard cap, user-switch revocation, offline-tolerant signout queue. Three new audit `action_type` values under existing `event_class="auth"`. No new dependencies, no DB schema change, no Flutter code change."
- [ ] T048 [P] **Flutter multi-deployment validation** (closes /speckit-analyze CG7 — FR-007 mandates the Flutter wrapper hold multiple deployments simultaneously). Procedure: (a) build the Flutter app pointed at deployment A by setting `assets/config.json.backendUrl = "https://sandbox.ai.uky.edu"`; sign in; force-quit. (b) Rebuild with `backendUrl = "https://<second-deployment>"`; sign in to the second deployment; force-quit. (c) Use ADB / Xcode device inspector to dump the WebView localStorage and assert both `oidc.user:<authority-A>:*` AND `oidc.user:<authority-B>:*` records are present and non-empty. (d) Restore `backendUrl` to A; launch the app; assert silent resume into deployment A without re-typing credentials. (e) Switch back to B; assert silent resume into B without re-typing credentials. Document the dump and the swap-and-resume cycle in the PR.
- [ ] T049 **SC-004 cold-launch benchmark** (closes /speckit-analyze CG6). Measure median time-to-dashboard across 10 cold-launch trials on a representative desktop browser (Chrome stable, machine specs documented in the PR) for two scenarios: (i) **returning-user silent resume** — pre-seeded `oidc.user:*` + valid anchor; (ii) **fresh interactive login** — empty localStorage, scripted Keycloak sign-in via a headless test account. Assert: `median(silent_resume) ≤ median(fresh_login) + 500 ms` (SC-004). If the assertion fails, file a perf regression issue and DO NOT mark the feature complete. Repeat informally on iOS Simulator + Android Emulator to spot-check mobile.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion. BLOCKS all user stories.
- **US1 (Phase 3)**: Depends on Foundational. P1 MVP — finish this first.
- **US2 (Phase 4)**: Depends on US1 (mobile validates the same code path web exercises). Can run in parallel with US3/US4 implementation once US1 lands in main.
- **US3 (Phase 5)**: Depends on Foundational only. Can run in parallel with US1 implementation IF different developers; otherwise sequential after US1.
- **US4 (Phase 6)**: Depends on Foundational only. Can run in parallel with US3.
- **Polish (Phase 7)**: Depends on all four user stories.

### Task-Level Dependencies (within phases)

- **T003 (backend protocol)** must complete before T004 (orchestrator handler reads `RegisterUI.resumed`).
- **T004, T005** depend on T003 but are otherwise [P] with respect to each other.
- **T006** (backend tests) is [P] with T004/T005 — write tests first, watch them fail, implement, watch them pass.
- **T007 → T008**, **T009 → T010**, **T011 → T012** pair each frontend helper with its test file. Within each pair the test task is [P] with the implementation task only if written first.
- **T015** (main.tsx wiring) requires T007 (SafeWebStorageStateStore) and T009 (persistentLogin module) to exist.
- **T016, T017, T018** all touch `frontend/src/main.tsx` and `App.tsx` — sequence them after T015 to avoid merge conflicts.
- **T029 (signOut helper)** requires T011 (revocationQueue) to exist.
- **T037 (retry policy)** requires T009 (persistentLogin module) to exist.
- **T039** depends on T005 (the REST endpoint).
- **T042–T049 (polish)** are mostly [P] except where they reference each other; T049 (benchmark) is sequential because it depends on a fully-wired build.

### Parallel Opportunities (highlights)

- **Phase 2**: T004, T005, T006 (backend) run in parallel with T007–T012 (frontend) since they touch disjoint files. Inside frontend, the three helper modules + their tests can be six parallel tasks.
- **Phase 3 (US1)**: T013 and T014 are different test files → parallel.
- **Phase 4 (US2)**: T021–T024 are independent device/emulator validations → all parallel.
- **Phase 5 (US3)**: T026, T027, T028 are different test files → parallel.
- **Phase 6 (US4)**: T034, T035, T036 are different files → parallel.

---

## Parallel Example: Phase 2 (Foundational)

The frontend test/implementation pairs (T007/T008, T009/T010, T011/T012) ARE NOT independent in the strict sense — each test imports its sibling implementation module. Use a TDD discipline so they can be developed concurrently: write the test against the *expected* exported symbol first (it will fail with a "module not found" or "undefined export"), then land the implementation. Each pair is fully parallel **across pairs**: SafeWebStorageStateStore vs persistentLogin vs revocationQueue touch different files.

```bash
# Backend (one developer):
Task: "T003 Add resumed:bool=False to backend/shared/protocol.py RegisterUI"
Task: "T004 [P] Wire resumed flag to action_type in backend/orchestrator/orchestrator.py"
Task: "T005 [P] Add POST /api/audit/session-resume-failed in backend/audit/api.py"
Task: "T006 [P] backend/audit/tests/test_session_resume_actions.py — five test cases"

# Frontend pair 1 (developer A, TDD: write T008 first, fail, then T007):
Task: "T008 [P] tests/safeStorageStore.test.tsx"
Task: "T007 [P] SafeWebStorageStateStore in frontend/src/auth/safeStorageStore.ts"

# Frontend pair 2 (developer B, TDD: T010 first):
Task: "T010 [P] tests/persistentLogin.test.tsx (invariants I-1..I-6 + clock-skew + unknown schema_version)"
Task: "T009 [P] persistentLogin.ts (anchor + 365-day cap + wasSilentResume)"

# Frontend pair 3 (developer C, TDD: T012 first):
Task: "T012 [P] tests/revocationQueue.test.tsx"
Task: "T011 [P] revocationQueue.ts (sessionStorage, FIFO, 16-cap, 5-attempt-cap)"
```

## Parallel Example: Phase 4 (US2 device validation)

```bash
# All four can run on different devices/emulators simultaneously:
Task: "T021 iOS Simulator smoke test"
Task: "T022 Android Emulator smoke test"
Task: "T023 Physical iOS device with reboot"
Task: "T024 Physical Android device with reboot"
```

---

## Implementation Strategy

### MVP First (US1 only — the headline)

1. Complete Phase 1: Setup (T001–T002 — trivial).
2. Complete Phase 2: Foundational (T003–T012).
3. Complete Phase 3: User Story 1 (T013–T020).
4. **STOP and VALIDATE**: Run the web smoke test in quickstart. If it passes, you have a deployable MVP that satisfies the user's headline ask for browser users.
5. Deploy to staging. Confirm the audit log shows correct `auth.login_interactive` / `auth.session_resumed` rows.

### Incremental Delivery

1. Setup + Foundational + US1 → MVP shipped (web persistence works).
2. Add US2 → mobile validation done (no code change; sign off).
3. Add US3 → sign-out hardened, user-switch revocation closed.
4. Add US4 → failure recovery solid; offline resume covered.
5. Polish → operator docs + coverage + cross-browser sign-off.

### Risk Notes

- **Highest risk task**: T015 (extracting `oidcConfig` and switching `userStore` to localStorage). Mechanically small but blast-radius covers every login. Mitigation: T013/T014 integration tests (T013 now imports the extracted production config so a regression fails the test) + the manual T020 smoke test.
- **Second-highest risk**: T030 (user-switch revocation in `onSigninCallback`). Timing-sensitive — must read old OIDC record before the lib overwrites it. Mitigation: tests T027 and T028 cover both interleavings.
- **Performance budget risk**: T049's SC-004 ≤ 500 ms median delta is achievable today (silent resume re-uses an unexpired access token) but could regress if a future change introduces a synchronous storage read on the hot path. Block the PR on T049 passing.
- **Operator coordination required**: T042 + T046 require a Keycloak admin to verify realm settings in staging before merge. T048 (Flutter multi-deployment) requires producing two distinct asset bundles; coordinate with the deployment owner. Block the PR on these confirmations.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks.
- [US#] label maps task to its user story for traceability.
- Each user story is independently completable and testable per the spec's "Independent Test" criteria.
- Constitution III: tests are NOT optional here; every implementation task in this list has matching test tasks.
- Constitution V: no new third-party packages are introduced. `oidc-client-ts` is already installed; `WebStorageStateStore` is an export from it.
- Constitution IX: no database schema changes; no migration task needed.
- Commit after each task or logical group; reference task IDs in commit messages.
- Stop at any checkpoint to validate story independently.
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that break independence.
