# Implementation Plan: Condensed Sidebar Settings Menu

**Branch**: `007-sidebar-settings-menu` | **Date**: 2026-04-30 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/007-sidebar-settings-menu/spec.md`

## Summary

Six secondary sidebar buttons added by features 003–006 (Audit log, LLM settings, Tool quality, Tutorial admin, Take the tour, User guide) are folded into a single "Settings" entry in `DashboardLayout`. Clicking it opens an anchored popover dropdown (no backdrop scrim) grouped into three sections: **Account** (Audit log, LLM settings), **Help** (Take the tour, User guide), and **Admin tools** (Tool quality, Tutorial admin — only when `isAdmin === true`). Each menu item invokes the *same* open-callback the original sidebar button used today, preserving every existing URL deep-link (`?audit=open`, `?llm=open`, `?feedback=open`, `?tutorial_admin=open`, `?user_guide=open`) without changes outside the sidebar component. Agents, New chat (+), Sign out, and the Status section stay top-level.

The change is **strictly frontend**. No backend, database, audit, WebSocket, or REST changes. Constitution Principle V (lead-developer approval for new third-party libraries) is satisfied because we adapt the existing inline-popover pattern from `FeedbackControl.tsx` instead of importing a menu library — only the existing `lucide-react` `Settings` icon is added to the imports.

The popover conforms to the full WAI-ARIA menu pattern (FR-012): arrow-key navigation, Home/End, focus trap, focus return, `role="menu"` / `role="menuitem"`, `aria-haspopup`, `aria-expanded`. It auto-opens when the onboarding tutorial highlights an in-menu target, and auto-closes when the tutorial advances past that step (FR-010). When an open-callback is unavailable for a given item, the item is omitted entirely (FR-014); when every item in a group is omitted, the group heading is also hidden.

## Technical Context

**Language/Version**: TypeScript 5+ on Vite + React (frontend, per Constitution Principle II). **No backend changes** — Python is not touched in this feature.

**Primary Dependencies**: React + Vite + Vitest + `@testing-library/react` (existing); `lucide-react` (already a dependency, used in `DashboardLayout.tsx:7-33` for every existing sidebar icon). **Zero new third-party libraries** — Constitution Principle V is satisfied by reuse. The popover is hand-rolled using the same inline-popover pattern already in `frontend/src/components/feedback/FeedbackControl.tsx:39-197` (click-outside via `document.addEventListener` in `useEffect`, ref-based dismissal).

**Storage**: None. The Settings menu is pure React state (`open: boolean`, `focusedIndex: number`). No localStorage, no cookies, no backend persistence. Existing per-feature URL state (audit/llm/feedback/tutorial_admin/user_guide query params, owned by `App.tsx`) is unchanged.

**Testing**: Vitest + Testing Library, alongside existing `frontend/src/__tests__/`. Coverage target 90% on changed code per Constitution Principle III. Tests cover: rendering with/without admin, item omission when callback unavailable, click activation, click-outside dismissal, Escape dismissal, full keyboard navigation (Tab/Enter/Arrow/Home/End/Escape), focus trap, focus return, tutorial auto-open/auto-close.

**Target Platform**: Existing AstralBody frontend running in modern evergreen browsers (Chrome, Firefox, Safari, Edge). Three viewport modes already supported by `DashboardLayout`: expanded sidebar (desktop), collapsed icon rail (desktop), mobile drawer.

**Project Type**: Web application (existing `backend/` + `frontend/` split). This feature touches only `frontend/`.

**Performance Goals**: Popover open/close transitions MUST not introduce visible jank. Open latency MUST be ≤ 16 ms (one frame at 60 fps) since this is a pure local state toggle. No new render path is added to the chat-message hot loop.

**Constraints**:
- Constitution Principle V: no new third-party UI library (FR-013).
- Constitution Principle VIII: must use existing primitive components / styling conventions (Tailwind utility classes already used in `DashboardLayout`).
- FR-015: hiding admin items is UX-only; backend authorization for every admin-scoped action is enforced by existing server-side role checks (REST endpoints in `backend/feedback/api.py` for Tool quality, `backend/onboarding/api.py` for Tutorial admin) and is *not* affected by this feature. The plan must preserve those server-side checks unchanged.
- Tutorial step targets (`data-tutorial-target` attributes) must survive the move — the tutorial overlay locates targets via `document.querySelector('[data-tutorial-target=…]')` (`TutorialOverlay.tsx:35-41`), which means moved targets must exist in the DOM when their step activates.

**Scale/Scope**:
- 1 modified component: `DashboardLayout.tsx` (replace 6 expanded button blocks `:713-820` and 6 collapsed-rail blocks `:630-639` with one Settings trigger + popover).
- 1 new component: `SettingsMenu.tsx` (anchored popover with grouped items).
- 1 modified hook: `useOnboarding` / `OnboardingContext.tsx` exposes the *current step's target key* so SettingsMenu can react to it (or alternatively, SettingsMenu subscribes via a small new effect on the existing context). Decision in `research.md`.
- 1 added entry in `tooltipCatalog.ts` for `sidebar.settings`.
- 6 existing `data-tutorial-target` attributes (`sidebar.audit`, `sidebar.tutorial-admin`, `sidebar.replay-tour`, `sidebar.user-guide`, plus `sidebar.feedback-admin` and one for LLM if present) move from sidebar buttons to menu items.
- 0 backend changes. 0 contract changes. 0 audit-event additions. 0 DB schema changes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Primary Language (Python) | ✅ Pass (N/A) | No backend changes — Python is not touched. |
| II. Frontend Framework (Vite + React + TS) | ✅ Pass | All changes are TSX in the existing Vite + React project. |
| III. Testing Standards (90% coverage) | ✅ Pass | New `SettingsMenu.test.tsx` plus updates to `DashboardLayout.test.tsx` (if present) cover all FRs. CI coverage gate enforced as today. |
| IV. Code Quality (ESLint) | ✅ Pass | No new style exceptions; existing ESLint config applies. |
| V. Dependency Management (lead approval) | ✅ Pass | **Zero new third-party libraries** (FR-013). `lucide-react` already a dependency; `Settings` icon is a one-line additional import from the same package. |
| VI. Documentation | ✅ Pass | New TSX exports get JSDoc comments (component description, props). No public API surface changes (no new REST/WS contracts). |
| VII. Security | ✅ Pass | FR-015 explicitly preserves the existing server-side authorization boundary for admin actions. Hiding the menu group is UX-only; the underlying REST/WS handlers continue to enforce the admin role via Keycloak JWT exactly as they do today. No auth surface changes. |
| VIII. User Experience | ✅ Pass | Reuses the existing inline-popover pattern (`FeedbackControl`) and existing Tailwind utility classes. No new UI primitive introduced. |

**Result: PASS, no violations.** Complexity Tracking section is intentionally empty.

## Project Structure

### Documentation (this feature)

```text
specs/007-sidebar-settings-menu/
├── plan.md              # this file
├── spec.md              # feature specification (already exists, with Clarifications)
├── research.md          # Phase 0 output — generated below
├── data-model.md        # Phase 1 output — generated below (minimal: no new entities)
├── quickstart.md        # Phase 1 output — generated below
├── contracts/           # Phase 1 output — intentionally empty (no new contracts)
│   └── README.md        # placeholder explaining why no contracts exist
├── checklists/
│   └── requirements.md  # already exists
└── tasks.md             # NOT created here — produced by /speckit.tasks
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── components/
│   │   ├── DashboardLayout.tsx                  # MODIFIED — replace six secondary
│   │   │                                          #   button blocks (expanded :713-820,
│   │   │                                          #   collapsed-rail :630-639) with a
│   │   │                                          #   single Settings trigger + <SettingsMenu />
│   │   ├── settings/
│   │   │   ├── SettingsMenu.tsx                 # NEW — anchored popover with grouped items
│   │   │   │                                          #   (Account / Help / Admin tools);
│   │   │   │                                          #   full WAI-ARIA menu pattern
│   │   │   └── __tests__/
│   │   │       └── SettingsMenu.test.tsx        # NEW — RTL tests for FR-001..FR-015
│   │   └── onboarding/
│   │       ├── OnboardingContext.tsx            # MODIFIED — expose currentStep target key
│   │       │                                          #   in the context value (one extra
│   │       │                                          #   field, no new public API)
│   │       └── tooltipCatalog.ts                # MODIFIED — add `sidebar.settings`
│   │                                                #   tooltip text
│   ├── hooks/                                   # UNCHANGED
│   ├── catalog.ts                               # UNCHANGED
│   └── App.tsx                                  # UNCHANGED — `isAdmin` already piped
│                                                  #   to DashboardLayout (line 213); the
│                                                  #   six open-callbacks are already
│                                                  #   passed as props.
└── tests/                                       # existing layout — new tests live
                                                 #   alongside SettingsMenu.tsx in
                                                 #   __tests__/ (matches feedback pattern)

# UNCHANGED: backend/, .specify/, all docs outside specs/007-…
```

**Structure Decision**: AstralBody is a web application with the existing `backend/` + `frontend/` split. Frontend-only changes live under `frontend/src/components/settings/`, a new sibling of `feedback/`, `audit/`, `llm/`, `onboarding/`. This matches the per-feature folder convention established by features 003–006 (each feature got its own component subdir under `components/`). No backend module is created.

The new `SettingsMenu.tsx` lives in its own folder so colocated tests (`__tests__/SettingsMenu.test.tsx`) follow the same pattern as `frontend/src/components/onboarding/__tests__/`.

## Complexity Tracking

> No Constitution violations. Section intentionally empty.
