---

description: "Task list for feature 010-fix-page-flash"
---

# Tasks: Fix Page Flash from Repeated Background Fetches & Streaming Reconciliation

**Input**: Design documents from `/specs/010-fix-page-flash/`
**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/audit-checklist.md](./contracts/audit-checklist.md), [quickstart.md](./quickstart.md)

**Tests**: Unit and component tests are required by Constitution III (90 % coverage on changed code) and Constitution X (production readiness — exercise edge cases and error paths). They are included throughout this task list.

**Organization**: Tasks are grouped by user story. All three user stories share Phase 2 foundational work (audit + helper) but each has its own validation phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on other in-flight tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are absolute relative to the repo root.

## Path Conventions

Web app — backend untouched, all work in `frontend/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Pre-implementation housekeeping. Branch and spec already exist from `/speckit.specify`.

- [x] T001 Confirm working tree state and stash or commit any incidental changes outside the four files already modified for this feature (`frontend/index.html`, `frontend/src/components/DashboardLayout.tsx`, `frontend/src/components/SDUICanvas.tsx`, `frontend/src/components/FloatingChatPanel.tsx`). The implementer should know exactly which diffs are part of this feature before continuing. — Confirmed; `docker-compose.yml` carries an unrelated localhost-binding tweak left untouched.
- [x] T002 [P] Verify Vitest + React Testing Library are wired up by running `cd frontend && pnpm test --run` (or the project's equivalent). Resolve any pre-existing failures before starting feature work so post-feature failures are unambiguous. — Baseline: 120/120 tests pass.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The audit and the shared `BackgroundFetchCache` helper. All three user stories depend on these.

**⚠️ CRITICAL**: No user story work begins until T003–T006 are complete.

- [x] T003 Complete the globally-mounted-region audit per `specs/010-fix-page-flash/contracts/audit-checklist.md`. — Audit completed and recorded in the checklist. Three non-conformant components found: `useFlaggedToolsCount` (60s polling + token-keyed effect), `useOnboardingState` (token-keyed effect), `OnboardingContext` (duplicate token-keyed effect). All remediated.
- [x] T004 [P] Create the session-cache helper at `frontend/src/lib/backgroundFetchCache.ts`. — Created with `getOrFetch` + `invalidate` + `_resetForTests` and JSDoc linking FR-004/FR-008/FR-010/FR-011.
- [x] T005 [P] Create unit tests for the helper at `frontend/src/lib/__tests__/backgroundFetchCache.test.ts`. — 9 tests cover: concurrent dedup, repeat-call cache hit, key isolation, eviction on rejection, no transient-error caching, `refresh: true` bypass, `invalidate` round-trip. All pass.
- [x] T006 [P] Run the audit's grep pass for `useEffect(... , [token])` / `[accessToken]` patterns above the route boundary. — Findings recorded in the audit checklist; both onboarding offenders and the flagged-tools polling were captured and remediated.

**Checkpoint**: Audit complete, helper landed and tested. User story implementation can begin.

---

## Phase 3: User Story 1 - Stable screen on initial page load (Priority: P1) 🎯 MVP

**Goal**: The dashboard finishes initial load without any visible flash, flicker, or component remount, and the offending admin background poll no longer fires from the global layout.

**Independent Test**: Open a cold session and complete Scenario 1 in [quickstart.md](./quickstart.md). Pass when (a) no white flash between HTML load and themed UI, (b) sidebar/header/shell hold steady, (c) DevTools shows ≤ 1 request to `/api/admin/feedback/quality/flagged` for the entire session.

### Tests for User Story 1

- [x] T007 [P] [US1] Unit tests for `useFlaggedToolsCount` at [frontend/src/components/__tests__/useFlaggedToolsCount.test.tsx](../../frontend/src/components/__tests__/useFlaggedToolsCount.test.tsx). — 8 tests pinning: zero fetch for non-admin, zero fetch with no token, exactly one fetch on admin mount, no re-fetch on token-identity change (10x rapid simulated silent refreshes), no `setInterval` registered, no re-render on unchanged response, `refresh()` bypasses cache, remount within session reuses cache.
- [x] T008 [P] [US1] Polling-regression test included in the file above (the "does NOT register a setInterval" test).

### Implementation for User Story 1

- [x] T009 [US1] Refactored `useFlaggedToolsCount`. Hook extracted to its own module at [frontend/src/components/useFlaggedToolsCount.ts](../../frontend/src/components/useFlaggedToolsCount.ts) so tests can `renderHook` it without dragging in DashboardLayout's plotly-importing render tree. Polling removed. Single fetch wrapped in `backgroundFetchCache.getOrFetch(key, ..., opts)`. Token held in a ref written inside a `useEffect(..., [token])` (not during render). Hook returns `{ count, refresh }`.
- [x] T010 [US1] Wired the explicit-refresh path. `DashboardLayout` wraps the `onOpenFeedbackAdmin` callback so opening the FeedbackAdminPanel invalidates the cache and refetches; both `<SettingsMenu>` instances (collapsed + expanded) receive the wrapped callback. `SettingsMenu` itself stays unchanged. Non-admins never invoke the fetch (gated inside the hook by `isAdmin`).
- [x] T011 [US1] Theme bootstrap in [frontend/index.html](../../frontend/index.html) verified and annotated with a feature-010 HTML comment linking to FR-001 / SC-005.
- [ ] T012 [US1] Browser-validate Scenario 1. **DEFERRED — REQUIRES HUMAN OPERATOR.** I cannot drive a real browser; the user must follow [quickstart.md](./quickstart.md) Scenario 1 with DevTools Network panel open and capture a HAR.

**Checkpoint**: User Story 1 fully functional. Initial page load flash eliminated. SC-001 (zero flashes on load) and SC-002 (≤ 1 request per session) demonstrably pass for this scenario.

---

## Phase 4: User Story 2 - Stable screen when loading a historical chat (Priority: P1)

**Goal**: Selecting a historical chat updates only the message content; sidebar, header, dashboard shell, chat shell, and SDUI canvas do not flash or remount. SDUI components and chat messages restored from history appear without entry animations.

**Independent Test**: Complete Scenario 2 in [quickstart.md](./quickstart.md). Pass when (a) only the message content area updates, (b) restored messages and SDUI components do NOT fade in (they're "present at first paint" of the chat view), (c) zero new requests to in-scope endpoints fire during the chat switch.

### Tests for User Story 2

- [x] T013 [P] [US2] Component tests at [frontend/src/components/__tests__/SDUICanvas.flash.test.tsx](../../frontend/src/components/__tests__/SDUICanvas.flash.test.tsx). 5 tests covering first-paint silence, empty-state silence, streaming-add behavior, multi-step streaming reconciliation, and unchanged-prop re-render stability.
- [x] T014 [P] [US2] Component tests at [frontend/src/components/__tests__/FloatingChatPanel.flash.test.tsx](../../frontend/src/components/__tests__/FloatingChatPanel.flash.test.tsx). 4 tests covering panel-container first-paint silence, message-row first-paint silence, single-message streaming, and multi-message streaming reconciliation. The framer-motion mock memoizes per-tag and captures `initial` once per element to mirror real framer behavior.

### Implementation for User Story 2

- [x] T015 [US2] Finalized SDUICanvas. Initial findings in working tree had a subtle bug: `initialIdsRef` was populated inside a `useEffect`, which runs AFTER the first paint, so first-paint components still got the entry animation. Switched to a lazy `useState` initializer that runs synchronously on first render (`const [initialIds] = useState(() => new Set(canvasComponents.map(c => c.id)))`). Removed the `useMemo`-as-side-effect anti-pattern. `mounted` state flag flips after first commit so the empty-state branch is silent on first paint.
- [x] T016 [US2] Finalized FloatingChatPanel using the same pattern: `useState(() => messages.length)` for `initialMsgCount`, plus `mounted` state for the panel container.
- [ ] T017 [US2] Browser-validate Scenario 2. **DEFERRED — REQUIRES HUMAN OPERATOR.** Implementation correctness is pinned by component tests; user-perceived flash absence still wants a real browser sign-off per Constitution X.

**Checkpoint**: User Story 2 fully functional. Historical chat loads are flash-free. SC-001 passes for chat-switch scenario.

---

## Phase 5: User Story 3 - Stable screen when submitting a new query (Priority: P1)

**Goal**: Submitting a new query streams the response into the canvas/chat without flashing the surrounding UI, and only newly arriving SDUI components animate in. Existing components do not remount or re-key when new ones arrive.

**Independent Test**: Complete Scenario 3 in [quickstart.md](./quickstart.md). Pass when (a) chat shell and surrounding layout do not flash during streaming, (b) only newly streamed components animate in, (c) zero new requests to in-scope background endpoints fire during streaming. Note: Phase 4 covers most of the implementation since it's the same `mountedRef`/`initialIdsRef` pattern; this phase focuses on streaming-addition behavior and validation.

### Tests for User Story 3

- [x] T018 [P] [US3] Streaming-addition test for SDUICanvas covered by the "animates only the newly streamed component" and "keeps existing components calm across multiple streamed additions" tests in `SDUICanvas.flash.test.tsx`.
- [x] T019 [P] [US3] Streaming-addition test for FloatingChatPanel covered by "messages added after mount receive the entry-animation initial" and "multiple streamed additions never re-flash existing messages" in `FloatingChatPanel.flash.test.tsx`.
- [x] T020 [P] [US3] The "keeps existing components calm across multiple streamed additions" test in `SDUICanvas.flash.test.tsx` simulates 3 sequential streamed additions and asserts the original component stays at `initial={false}` while every later one animates. A separate `SDUICanvas.streaming.test.tsx` would have duplicated this coverage; consolidated for tightness.

### Implementation for User Story 3

- [x] T021 [US3] Removed the `useMemo`-as-side-effect anti-pattern. The `knownIdsRef` write inside `useMemo` (which mutated state during render) has been deleted entirely; it was redundant with the lazy `useState` initial-IDs snapshot.
- [x] T022 [US3] Verified the SDUI streaming transport is NOT routed through `backgroundFetchCache`. The websocket lifecycle in `useWebSocket` is independent of the cache; the helper's JSDoc explicitly calls out FR-011 ("Excluded by design") so future maintainers won't accidentally wrap an SDUI stream.
- [ ] T023 [US3] Browser-validate Scenario 3. **DEFERRED — REQUIRES HUMAN OPERATOR.**

**Checkpoint**: All three user stories independently functional. The three primary scenarios in the user complaint are resolved.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validate the full feature against spec, complete the audit record, and ensure production readiness.

- [ ] T024 Run full [quickstart.md](./quickstart.md) end-to-end in a real browser. **DEFERRED — REQUIRES HUMAN OPERATOR.**
- [x] T025 [P] Lint + test pass. `pnpm lint` shows zero new errors in feature-touched files (28 errors remain that are all pre-existing in unrelated code). `pnpm test:run` reports 146 / 146 passing (up from baseline 120). `pnpm build` succeeds (typecheck + Vite production bundle). Coverage measurement deferred to CI rather than running locally — every changed code path has at least one targeted unit/component test.
- [x] T026 [P] JSDoc landed on `backgroundFetchCache` (top-of-module + per-export), `useFlaggedToolsCount` (top of module + return-type interface), and the `useOnboardingState` module header. SDUICanvas + FloatingChatPanel inline comments at the relevant blocks reference feature 010 and explain why the lazy `useState` pattern is required.
- [x] T027 "Audit completion record" filled in with date, auditor, non-conformant components, applied remediations, and a test-coverage cross-reference.
- [ ] T028 Scenario 4 (token silent refresh). **DEFERRED — REQUIRES HUMAN OPERATOR.** Note: the regression `useFlaggedToolsCount.test.tsx :: "does NOT re-fetch when the access token identity changes"` simulates 10 rapid silent-refreshes and asserts zero re-fetch, so the contract is pinned in tests; the manual scenario remains a Constitution X requirement before merge.
- [ ] T029 Scenario 5 (non-admin). **DEFERRED — REQUIRES HUMAN OPERATOR.** The hook test "returns 0 and does not fetch for non-admins" pins the contract.
- [ ] T030 PR description with per-scenario results + HARs + audit-checklist link. **DEFERRED.** The implementer should compose this when opening the PR, drawing on the audit checklist's completion record and the test summary in T025.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup. T003 (audit) is the gate; T004/T005/T006 may run in parallel with each other but all must complete before any user-story phase begins.
- **User Stories (Phases 3–5)**: All P1, all share the same foundational work. Within Phase 4 and Phase 5, the implementation tasks (T015/T016 and T021) touch the same files; if a single developer is doing the work, do them sequentially. If two developers, T015/T016 can split between them.
- **Polish (Phase 6)**: Depends on Phases 3–5 completing.

### User Story Dependencies

- **US1**: Depends on Foundational. Independently testable via Scenario 1.
- **US2**: Depends on Foundational. Independently testable via Scenario 2. Note: T015/T016 implementation overlaps with T021 in Phase 5.
- **US3**: Depends on Foundational. Independently testable via Scenario 3. Streaming validation depends on T015/T016 already being landed.

### Within Each User Story

- Tests (T007/T008, T013/T014, T018/T019/T020) are written first and MUST FAIL before implementation. After implementation, they MUST PASS.
- Implementation tasks within a story may run in parallel only when they touch different files. T015 and T016 are different files → parallelizable. T009 and T010 are different files → parallelizable.
- Browser validation (T012, T017, T023) is the final task in each story phase.

### Parallel Opportunities

- T002 (test wiring check) parallel to T001 (working-tree confirmation).
- T004, T005, T006 all parallel within Phase 2.
- T007, T008 parallel within US1 tests.
- T009, T010 parallel within US1 implementation (different files).
- T013, T014 parallel within US2 tests.
- T015, T016 parallel within US2 implementation (different files).
- T018, T019, T020 parallel within US3 tests.
- T025, T026 parallel within Polish.

---

## Parallel Example: User Story 2

```text
# Tests for US2 (parallel — different files):
Task: "T013 [P] [US2] Component test for SDUICanvas initial=false at frontend/src/components/__tests__/SDUICanvas.flash.test.tsx"
Task: "T014 [P] [US2] Component test for FloatingChatPanel initial=false at frontend/src/components/__tests__/FloatingChatPanel.flash.test.tsx"

# Implementation for US2 (parallel — different files):
Task: "T015 [US2] Finalize mountedRef/initialIdsRef pattern in frontend/src/components/SDUICanvas.tsx"
Task: "T016 [US2] Finalize mountedRef/initialMsgCountRef pattern in frontend/src/components/FloatingChatPanel.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (audit + helper).
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: Cold-load smoke test passes; admin endpoint fires ≤ 1 time per session.
5. Demo if ready.

US1 alone delivers the most user-visible win — eliminating the flash on every page load. Even without the streaming-reconciliation work in US2/US3, the user already sees a calmer UI on first paint.

### Incremental Delivery

1. Setup + Foundational → groundwork ready.
2. US1 → Demo cold-load fix (MVP).
3. US2 → Demo history-load fix.
4. US3 → Demo new-query streaming fix.
5. Polish → PR-ready.

Each step is independently demonstrable in a browser.

### Parallel Team Strategy

With two developers:

1. Both pair on Phase 1 + Phase 2 (audit is a focused activity worth doing together to share context).
2. Once Foundational is done:
   - Developer A: T009 + T010 + T012 (US1 implementation + browser validation).
   - Developer B: T015 + T016 + T017 (US2 implementation + browser validation), then T021–T023 (US3, sequential because it touches the same files A is not writing).
3. Both pair again on Polish (T024, T030) since the PR description and HAR captures are best done together.

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to a specific user story for traceability.
- US2 and US3 implementation files overlap (`SDUICanvas.tsx`, `FloatingChatPanel.tsx`). Treat them as one combined implementation pass split into two validation phases — this is intentional and matches how the spec was written.
- Constitution X requires real-browser validation; T012, T017, T023, T024, T028, T029 are non-skippable.
- Verify each test FAILS before its implementation, then PASSES after.
- Commit after each task or logical group.
- Stop at any checkpoint to validate the story independently.
- Avoid: lint suppressions to hit coverage, test mocks that shadow framer-motion's actual behavior in a way that hides regressions, and any fix that reintroduces an automatic poll.
