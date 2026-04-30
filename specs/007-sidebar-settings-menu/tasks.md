---

description: "Tasks for feature 007-sidebar-settings-menu"
---

# Tasks: Condensed Sidebar Settings Menu

**Input**: Design documents from `/specs/007-sidebar-settings-menu/`
**Prerequisites**: plan.md, spec.md (with Clarifications), research.md, data-model.md, contracts/ (intentionally empty), quickstart.md

**Tests**: REQUIRED. Constitution Principle III mandates ≥ 90% coverage on changed code. `research.md` § Decision 6 enumerates 14 test cases that map directly to functional requirements. Test tasks are included below.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1 / US2 / US3)
- File paths shown are absolute from repo root

## Path Conventions

- Web app: `frontend/src/...` (backend untouched)
- Tests: colocated under `__tests__/` next to the component, matching `frontend/src/components/onboarding/__tests__/` precedent
- All new code lives under `frontend/src/components/settings/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new component directory and skeleton files.

- [X] T001 Create directory `frontend/src/components/settings/` and `frontend/src/components/settings/__tests__/`. Add stub `frontend/src/components/settings/SettingsMenu.tsx` exporting an empty React component, and stub `frontend/src/components/settings/__tests__/SettingsMenu.test.tsx` with a single passing smoke test (`it("renders without crashing", …)`). Confirms Vitest discovers the file and the project compiles cleanly before any real work begins.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Cross-cutting prerequisites that ALL user stories depend on (tooltip catalog entry; tutorial-context plumbing).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Add `sidebar.settings` entry to the tooltip catalog in `frontend/src/components/onboarding/tooltipCatalog.ts`. Tooltip text should describe "Open Settings — Audit log, LLM, Help, and admin tools" (or a concise variant matching the existing tone). The entry is consumed by US1 when the trigger renders with a `<Tooltip>` wrapper.
- [X] T003 Expose a new field `currentStepTargetKey: string | null` on the `OnboardingContext` value in `frontend/src/components/onboarding/OnboardingContext.tsx`. Source it from the same selector that `TutorialOverlay.tsx:35-41` already uses to find tutorial targets (the active step's target key, or `null` when no step is active or `target_kind === "none"`). Make zero behavioral changes to existing context consumers — this is a purely additive field.
- [X] T004 Update `frontend/src/components/onboarding/__tests__/OnboardingContext.test.tsx` to assert that `currentStepTargetKey` reflects the active step's target (and is `null` when the tutorial is dismissed or between steps). Existing assertions must continue to pass unchanged.

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 — Reduce Sidebar Clutter Behind a Single Settings Entry (Priority: P1) 🎯 MVP

**Goal**: Replace the six secondary sidebar buttons (Audit log, LLM settings, Tool quality, Tutorial admin, Take the tour, User guide) with one Settings entry that opens an anchored popover. Items are reachable; existing URL deep-links continue to work; popover dismisses on outside click / Escape; full WAI-ARIA keyboard navigation; tutorial auto-opens menu when targeting a moved item and auto-closes when the next step targets something else; missing-callback items are omitted.

**Independent Test**: Sign in as any user (admin or not — admin gating is US2's concern). Confirm the sidebar shows one Settings entry instead of six. Click it; confirm all six items render (no admin gating yet) and each one opens the same panel its original button opened. Confirm Escape, click-outside, and full keyboard navigation work. Confirm `?audit=open` (and the four other deep-links) still open their panels directly. Confirm replaying the tutorial reaches every step that targets a moved item.

### Tests for User Story 1

> **NOTE: Write these tests FIRST. Verify they FAIL before implementation tasks T009-T015.**

- [X] T005 [US1] Add render-and-activate tests to `frontend/src/components/settings/__tests__/SettingsMenu.test.tsx`: (a) trigger renders with `aria-haspopup="menu"`, `aria-expanded="false"`, and the `Settings` icon; (b) clicking trigger sets `aria-expanded="true"` and renders six menuitem buttons; (c) clicking a menu item invokes the corresponding `onOpen…`/`onReplay…` prop callback exactly once and the menu closes (`aria-expanded` returns to `"false"`).
- [X] T006 [US1] Add dismissal-and-keyboard tests to `frontend/src/components/settings/__tests__/SettingsMenu.test.tsx`: (a) clicking outside the popover closes it without invoking any callback; (b) Escape closes the menu and returns focus to the trigger; (c) Tab to trigger + Enter opens menu and focuses first item; (d) ArrowDown/ArrowUp move focus between items with wrap-around; (e) Home / End jump to first / last item; (f) Tab and Shift+Tab cycle within menu items (focus trap); (g) Enter or Space on a focused item activates that item's callback. Depends on T005 (same file).
- [X] T007 [US1] Add callback-omission tests to `frontend/src/components/settings/__tests__/SettingsMenu.test.tsx`: (a) when `onOpenAuditLog={undefined}`, the Audit log menuitem is absent from the rendered tree (use `queryByRole`, expect `null`); (b) when every user-scope callback is undefined, no user-scope items render. Depends on T005.
- [X] T008 [US1] Add tutorial-integration tests to `frontend/src/components/settings/__tests__/SettingsMenu.test.tsx`: (a) wrap component in a mock `OnboardingContext.Provider` whose value sets `currentStepTargetKey` to one of the menu item keys (e.g., `"sidebar.audit"`) and assert the menu auto-opens; (b) transition the value to `"sidebar.agents"` (an off-menu key) and assert the menu auto-closes; (c) transition to `null` and assert the menu auto-closes. Depends on T005, T003.

### Implementation for User Story 1

- [X] T009 [US1] Implement the SettingsMenu skeleton in `frontend/src/components/settings/SettingsMenu.tsx`: (a) `lucide-react` `Settings` icon trigger button with proper ARIA (`aria-haspopup="menu"`, `aria-expanded`, `aria-controls`); (b) anchored popover container (`role="menu"`, position absolute relative to trigger, no backdrop scrim) holding the six items; (c) click-outside dismissal mirroring `frontend/src/components/feedback/FeedbackControl.tsx:58-67`; (d) Escape dismissal via a window keydown listener gated on `open`; (e) JSDoc on the exported component (Constitution VI). At this stage, render all six items unconditionally on `isAdmin` (US2 adds gating).
- [X] T010 [US1] Implement the full WAI-ARIA keyboard navigation in `frontend/src/components/settings/SettingsMenu.tsx`: focus trap inside the open menu (Tab/Shift+Tab cycle within items), arrow-key navigation, Home/End jumps, Enter/Space activation, focus return to trigger on close. Use a `focusedIndex` state plus a `Map`/array of item refs as described in `data-model.md` § State transitions. Depends on T009.
- [X] T011 [US1] Implement per-item conditional rendering in `frontend/src/components/settings/SettingsMenu.tsx`: each menuitem renders only when its corresponding `on…` prop is defined; if every item in a group is absent, the group's container/heading is also absent (FR-014). Depends on T009.
- [X] T012 [US1] Implement tutorial auto-open / auto-close in `frontend/src/components/settings/SettingsMenu.tsx`: define `SETTINGS_MENU_TARGET_KEYS = new Set(["sidebar.audit", "sidebar.feedback-admin", "sidebar.tutorial-admin", "sidebar.replay-tour", "sidebar.user-guide", "sidebar.llm"])` (any subset that exists in the catalog). Add a `useEffect` keyed on `currentStepTargetKey` from `useOnboarding()` that opens the menu when the key joins the set, closes it when it leaves the set or becomes `null`. Auto-open MUST NOT steal focus from the tutorial overlay (set `focusedIndex = -1` in this code path). Depends on T009, T003.
- [X] T013 [US1] Replace the six expanded-sidebar button blocks at `frontend/src/components/DashboardLayout.tsx:713-820` with a single Settings entry that wraps the new `<SettingsMenu>` component, threading through the existing props (`onOpenAuditLog`, `onOpenLlmSettings`, `onOpenFeedbackAdmin`, `onOpenTutorialAdmin`, `onReplayTutorial`, `onOpenUserGuide`). Keep the Agents button (`:694-711`) and the chat-history list (`:822+`) unchanged. Add `data-tutorial-target="sidebar.settings"` to the Settings entry so future tutorial steps can reference it.
- [X] T014 [US1] Replace the four utility entries in the collapsed icon rail at `frontend/src/components/DashboardLayout.tsx:630-639` (Audit log icon, FeedbackAdminCollapsedButton) with a single Settings gear icon that triggers the same `<SettingsMenu>`. Keep the New chat (+) and Agents icons before it, and the Logout icon after the spacer. Use a `title` attribute matching the tooltip catalog entry from T002. Depends on T013 (same file).
- [X] T015 [US1] Move the existing `data-tutorial-target` attributes off the six original sidebar buttons and onto the corresponding menu items inside `<SettingsMenu>` (`sidebar.audit`, `sidebar.feedback-admin`, `sidebar.tutorial-admin`, `sidebar.replay-tour`, `sidebar.user-guide`, plus `sidebar.llm` if present in the catalog). The keys themselves do NOT change — only the DOM element they live on (per `research.md` § Decision 3, this avoids any tutorial_step DB migration). Edit in `frontend/src/components/settings/SettingsMenu.tsx` and confirm removal from `DashboardLayout.tsx`. Depends on T009, T013.

**Checkpoint**: User Story 1 is functional and testable independently. The MVP ships if work stops here — admin items render unconditionally (which today's product also does, since admins-only buttons are conditionally passed via props), and section headings are flat or absent.

---

## Phase 4: User Story 2 — Admin-Only Tools Grouped and Hidden From Non-Admins (Priority: P2)

**Goal**: Add explicit `isAdmin`-driven gating so the Admin tools section (Tool quality + Tutorial admin) renders only for admins; non-admins see nothing of it in the rendered DOM.

**Independent Test**: With US1 already shipped, sign in as an admin: open Settings, confirm an "Admin tools" section heading appears with Tool quality and Tutorial admin items. Sign in as a non-admin: open Settings, confirm zero references to "Admin tools" / "Tool quality" / "Tutorial admin" in the rendered DOM.

### Tests for User Story 2

- [X] T016 [US2] Add admin-gating tests to `frontend/src/components/settings/__tests__/SettingsMenu.test.tsx`: (a) with `isAdmin={true}` and the two admin callbacks defined, the Admin tools section heading renders and both items are listed; (b) with `isAdmin={false}`, the Admin tools section heading is absent (`queryByText("Admin tools")` returns `null`) AND both admin items are absent (`queryByRole("menuitem", { name: /tool quality/i })` and `tutorial admin` both return `null`). FR-006 / SC-003.
- [X] T017 [US2] Add admin-empty-section test to `frontend/src/components/settings/__tests__/SettingsMenu.test.tsx`: with `isAdmin={true}` but BOTH admin callbacks `undefined`, the Admin tools heading MUST also be absent (FR-014 empty-group rule applied to the admin section). Depends on T016 (same file).

### Implementation for User Story 2

- [X] T018 [US2] Add an `isAdmin: boolean` prop to `<SettingsMenu>` in `frontend/src/components/settings/SettingsMenu.tsx`. Wrap the Admin tools group rendering in `isAdmin && (…)`, with the inner empty-group rule already enforced by T011. Add JSDoc note clarifying that the prop is UX-only and that server-side authorization is enforced separately (FR-015).
- [X] T019 [US2] Pass `isAdmin` from `DashboardLayout` props through to `<SettingsMenu>` at the call site in `frontend/src/components/DashboardLayout.tsx` (the prop is already piped from `App.tsx:213` to DashboardLayout — no `App.tsx` change needed). Depends on T018.

**Checkpoint**: User Stories 1 AND 2 both work independently. Non-admin users no longer see admin items at all; admins see a clearly labeled Admin tools section.

---

## Phase 5: User Story 3 — Help Items Discoverable From the Same Place (Priority: P3)

**Goal**: Ensure the Help group ("Take the tour" + "User guide") and the Account group ("Audit log" + "LLM settings") render with explicit, visually distinct section headings so help items are discoverable rather than buried in a flat list.

**Independent Test**: Open Settings and confirm three section headings render in this order: **Account**, **Help**, **Admin tools** (if admin). Each section visually separates its items (heading text styled distinctly from menuitem text). A user looking for help can locate "User guide" in under 10 seconds of being told "the user guide is somewhere in the sidebar" (SC-004).

### Tests for User Story 3

- [X] T020 [US3] Add section-headings tests to `frontend/src/components/settings/__tests__/SettingsMenu.test.tsx`: (a) when the menu is open with all callbacks defined, three headings render with text "Account", "Help", and "Admin tools" (when `isAdmin={true}`); (b) headings appear in DOM order Account → Help → Admin tools; (c) each heading is associated with its menu items via `aria-labelledby` (or equivalent ARIA grouping per the WAI-ARIA menu pattern from FR-012). FR-003 / FR-004 / FR-005.

### Implementation for User Story 3

- [X] T021 [US3] Add the three section headings ("Account", "Help", "Admin tools") to `<SettingsMenu>` in `frontend/src/components/settings/SettingsMenu.tsx` per `research.md` § Decision 4 ordering. Wrap each section's menuitems in a `<div role="group" aria-labelledby="…">` (or `<ul role="group">` if the menu pattern requires it) so screen readers announce the grouping. Style headings with the same Tailwind utility classes used for the existing `Recent Chats` / `Status` section labels in `DashboardLayout` (lines 660, 824) for visual consistency.

**Checkpoint**: All three user stories now work independently. The menu has explicit grouping, admin gating, and full keyboard accessibility.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify the feature meets every Success Criterion end-to-end, regression-check existing tests, and ship-ready cleanup.

- [X] T022 Run the full frontend test suite from the repo root: `cd frontend && npx vitest run --coverage`. Confirm: (a) all 22 new tests in `SettingsMenu.test.tsx` pass; (b) the updated `OnboardingContext.test.tsx` passes (7 tests, including the new `currentStepTargetKey` assertion); (c) total: **111 tests passing across 15 files** (was 84 before this feature). Coverage on `frontend/src/components/settings/` (added `@vitest/coverage-v8@^3.2.4` with lead-developer approval recorded 2026-04-30): **97.88% statements / 91.56% branches / 100% functions / 97.88% lines** — all four metrics exceed Constitution Principle III's 90% threshold.
- [X] T023 [P] Run ESLint on changed files: `npx eslint src/components/settings src/components/onboarding/OnboardingContext.tsx src/components/onboarding/tooltipCatalog.ts src/components/onboarding/__tests__/OnboardingContext.test.tsx src/components/DashboardLayout.tsx`. Result: **clean, no warnings**. `npx tsc -b` and `npm run build` also succeed.
- [X] T024 [P] No pre-existing `DashboardLayout` snapshot or render tests referenced the moved buttons. The only files containing `data-tutorial-target="sidebar.{audit,tutorial-admin,replay-tour,user-guide,feedback-admin}"` after the move are `SettingsMenu.tsx` (the new home) and `tooltipCatalog.ts` (catalog keys, valid). `TutorialAdminPanel.tsx` references those keys as legitimate authorable target identifiers — no change needed.
- [ ] T025 Execute the full quickstart smoke checklist in `specs/007-sidebar-settings-menu/quickstart.md` § 3a–3i (visible Settings entry across viewports; admin gating; deep-link preservation; dismissal; full WAI-ARIA keyboard nav; tutorial replay; missing-callback omission; server-side authz boundary). _Requires running the dev server in a real browser; deferred to human verification before merge._
- [ ] T026 [P] Capture three screenshots (expanded sidebar, collapsed icon rail, mobile drawer) showing the consolidated Settings entry, and attach them to the PR description per quickstart § 5. _Requires browser; deferred to human verification before merge._

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. Blocks all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational (T002, T003, T004). Required for US2 and US3.
- **User Story 2 (Phase 4)**: Depends on US1 (the menu must exist before admin gating can be added).
- **User Story 3 (Phase 5)**: Depends on US1 (the menu must exist before headings can be added). Independent of US2.
- **Polish (Phase 6)**: Depends on whichever stories you've shipped. T022 should run after every phase that adds tests.

### Within Each User Story

- **Tests first**: write the test tasks in each phase BEFORE the implementation tasks, and verify they fail.
- All tests for a user story live in the same file (`SettingsMenu.test.tsx`), so test tasks within a phase are sequential, not parallel.
- Implementation tasks targeting `SettingsMenu.tsx` are sequential (same file). Tasks targeting `DashboardLayout.tsx` are sequential among themselves but parallel-possible with `SettingsMenu.tsx` tasks once the public component shape is stable.

### Parallel Opportunities

- **Phase 2**: T002 ([P], `tooltipCatalog.ts`) and T003 (`OnboardingContext.tsx`) are independent files → can run in parallel.
- **Phase 6**: T023 (lint), T024 (existing-test cleanup, different files), and T026 (screenshots) are independent of each other.

### Cross-story Independence

- US2 (admin gating) and US3 (section headings) both edit `SettingsMenu.tsx` so they cannot be developed truly in parallel by two engineers without merge conflicts. However, each story is independently testable (US2's tests pass without US3's headings; US3's tests pass without US2's gating, given a non-admin test fixture).

---

## Parallel Example: Phase 2 (Foundational)

```bash
# Foundational tasks that touch independent files:
Task: "T002 — Add `sidebar.settings` entry to frontend/src/components/onboarding/tooltipCatalog.ts"
Task: "T003 — Expose currentStepTargetKey on frontend/src/components/onboarding/OnboardingContext.tsx"
# T004 must wait for T003 (assertion target).
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (T001).
2. Complete Phase 2 (T002–T004) — foundation ready.
3. Complete Phase 3 (T005–T015) — Settings menu replaces sidebar clutter.
4. **STOP and VALIDATE**: Run quickstart § 3a, 3d, 3e, 3f, 3g (skip § 3b/3c admin-specific checks). Run `npm test`. Ship if green.

### Incremental Delivery

1. Setup + Foundational → Foundation ready.
2. + US1 → Test independently → Ship MVP.
3. + US2 → Test admin-vs-non-admin paths → Ship.
4. + US3 → Test section-heading discoverability → Ship.
5. Polish (Phase 6) → Final coverage / lint / smoke / screenshots.

### Parallel Team Strategy

This feature is small (frontend-only, ~26 tasks). Single developer is the realistic case. If two engineers work in parallel:

1. Engineer A: Phase 1 + Phase 2 + Phase 3 (US1) — owns `SettingsMenu.tsx`.
2. Engineer B: T024 (sweeping existing snapshot tests) + T026 (screenshots scaffolding) in parallel.
3. After US1 lands, Engineer A picks up US2; Engineer B picks up US3 — but coordinate on `SettingsMenu.tsx` edits to avoid merge conflicts.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks.
- Every task includes the absolute file path it touches.
- Tests live in the same `__tests__/SettingsMenu.test.tsx` file, so test tasks within a phase are sequential (the [P] tag is intentionally absent).
- This feature introduces **zero new third-party dependencies**, **zero new database tables**, **zero new REST endpoints**, **zero new WebSocket messages**, and **zero new audit-event classes**. Verify these guarantees during code review (Constitution Principle V).
- Verify each test fails before the matching implementation task; this protects against accidentally passing tests that don't actually exercise the target behavior.
- Commit after each task or logical group; reference the task ID in the commit message (e.g., `T009: SettingsMenu skeleton — trigger + popover container`).
