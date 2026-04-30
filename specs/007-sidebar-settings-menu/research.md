# Phase 0 Research: Condensed Sidebar Settings Menu

**Feature**: 007-sidebar-settings-menu
**Date**: 2026-04-30

This document resolves every "NEEDS CLARIFICATION" surface from the spec / Technical Context. The five spec-level clarifications were resolved in `/speckit.clarify` (see `spec.md` § Clarifications). This file documents the remaining technical decisions: which existing patterns to mirror, which icon to use, and how the SettingsMenu should integrate with the onboarding tutorial.

---

## Decision 1 — Popover implementation pattern

**Decision**: Adapt the inline-popover pattern from `frontend/src/components/feedback/FeedbackControl.tsx:39-197` into a generalized `SettingsMenu` component. Click-outside via `document.addEventListener("click", …)` inside a `useEffect` keyed on `open`, with a `popoverRef` for containment checks. Closing via Escape via a `keydown` listener on `window` while open.

**Rationale**:
- Constitution Principle V (FR-013) bars introducing a new third-party menu/popover library.
- `FeedbackControl` already implements every dismissal behavior we need (click-outside, escape via parent, ref-based containment), and is the only inline popover currently in the codebase. Mirroring it keeps the bundle and review surface minimal.
- The pattern uses `position: relative` on the trigger wrapper and `position: absolute` on the popover itself, so it composes cleanly with both the expanded sidebar (vertical button list) and the collapsed icon rail (vertical icon column).

**Alternatives considered**:
- **Radix UI `@radix-ui/react-dropdown-menu`**: would deliver full ARIA menu pattern out of the box, but adds a transitive dependency tree and is barred by FR-013.
- **Headless UI `@headlessui/react` `Menu`**: same constraint — barred by FR-013.
- **Existing `Tooltip` primitive (`frontend/src/components/onboarding/Tooltip.tsx`)**: rejected — tooltips are read-only hover affordances, not interactive containers; they do not implement focus management.

**Implications for the implementation**:
- The full WAI-ARIA menu pattern (FR-012: arrow-keys, Home/End, focus trap, focus return) is *not* provided by `FeedbackControl` and must be implemented by hand. Plan to add a `useEffect` that listens for `keydown` events while open and routes ArrowUp/ArrowDown/Home/End/Tab into a small focused-index state machine, restoring focus to the trigger on close.

---

## Decision 2 — Settings trigger icon

**Decision**: Use `Settings` from `lucide-react` as the icon for the Settings sidebar entry.

**Rationale**:
- `lucide-react` is already imported throughout `DashboardLayout.tsx:7-33` for every existing sidebar icon (`Bot`, `Wrench`, `KeyRound`, `ListChecks`, `Compass`, `BookOpen`, `ShieldAlert`, `Plus`, `LogOut`, `Menu`, `ChevronRight`, `WifiOff`, `Wifi`, `X`).
- The `Settings` (gear) glyph is the universally recognized symbol for a configuration/options menu.
- Adding it is a one-line import addition with no new dependency.

**Alternatives considered**:
- `Cog` (lucide-react): nearly identical visually, but `Settings` is the more semantically conventional name.
- `MoreHorizontal` / `MoreVertical` (kebab/dots): visually less specific — "more" implies overflow, not configuration. The menu groups Account / Help / Admin tools, which are *settings*, not overflowed primary actions.
- Custom SVG: rejected — no need; lucide already covers it.

---

## Decision 3 — Onboarding tutorial integration

**Decision**: Expose the current tutorial step's target key from `OnboardingContext.tsx` as `currentStepTargetKey: string | null`. `SettingsMenu` reads it via `useOnboarding()` and runs an effect: if the active step's target key matches one of the menu's item keys (e.g., `sidebar.audit`, `sidebar.tutorial-admin`, `sidebar.replay-tour`, `sidebar.user-guide`, `sidebar.feedback-admin`), the menu auto-opens. When the target key transitions to a non-menu key (or to null), the menu auto-closes. The `data-tutorial-target` attributes on the moved buttons remain unchanged (e.g., `sidebar.audit` continues to be `sidebar.audit`), so existing tutorial step records in feature 005's `tutorial_step` table continue to resolve without an admin edit.

**Rationale**:
- `TutorialOverlay.tsx:35-41` resolves step targets via `document.querySelector('[data-tutorial-target="…"]')`. This means the moved menu items MUST be present in the DOM when the step activates — i.e., the menu must already be open. A reactive auto-open is therefore *required* to satisfy FR-010 + SC-005, not optional.
- Reusing the existing `data-tutorial-target` keys avoids any changes to the `tutorial_step` table contents — admins do not need to re-edit step copy or re-run a migration.
- Auto-close on target transition (Q4 from `/speckit.clarify`) prevents the menu from obscuring a subsequent step targeting an off-menu element (e.g., chat input, agent panel).

**Alternatives considered**:
- **Imperative API**: have `OnboardingContext` expose `openSettingsMenu()` / `closeSettingsMenu()` and call them from the step orchestrator. Rejected — couples Onboarding to a specific UI surface; if more containers (drawers, modals) ever need similar treatment, this scales poorly.
- **Listen on a window event**: emit `tutorial:step-changed` on `window` and have `SettingsMenu` subscribe. Rejected — the existing context already has the data; one extra context field is cleaner than ad-hoc events.
- **Renumber `data-tutorial-target` keys to e.g. `settings.audit`**: rejected — would require an admin-side migration of the `tutorial_step.target_key` column, and the keys are already namespaced (`sidebar.*`) in a way that survives the move (the items are *still* sidebar entries, they just live one level deeper).

**Implications**:
- `OnboardingContext.tsx` gains one new value in its provider's `value={…}` object — `currentStepTargetKey: string | null`. No public type change visible to consumers that don't ask for it.
- A small constant `SETTINGS_MENU_TARGET_KEYS = new Set([...])` lives in `SettingsMenu.tsx` so the auto-open logic is colocated with the menu definition.

---

## Decision 4 — Section ordering and labels

**Decision**: Section order in the rendered menu is **Account → Help → Admin tools**. Section labels exactly match those strings. Within sections, item order is:
- Account: Audit log, LLM settings (matches the order they were added — features 003 then 006).
- Help: Take the tour, User guide (tour first as the more lightweight option).
- Admin tools: Tool quality, Tutorial admin (matches feature order 004 then 005).

**Rationale**:
- Reading order corresponds to expected usage frequency for an average user (Account daily, Help occasional, Admin rare).
- Matches the spec's listing order in FR-003 / FR-004 / FR-005.

**Alternatives considered**:
- Putting Help last (after Admin): rejected — non-admin users would see an empty space where Admin would have been, which is jarring; ending with Help keeps both populations' menu shapes similar.
- Alphabetizing within sections: rejected — feature-add order has implicit chronological/thematic meaning that alphabetization would break (e.g., "Take the tour" before "User guide" reads as a natural progression).

---

## Decision 5 — Mobile drawer behavior

**Decision**: On a narrow viewport where the sidebar collapses to the mobile drawer, the Settings menu opens *inside* the drawer (anchored to the Settings entry as it appears in the drawer). It does not pop out beyond the drawer's viewport.

**Rationale**:
- Spec edge case "Mobile drawer" already commits to this: the menu opens "*inside* the drawer (or anchored such that it remains visible)".
- The same `position: absolute` containment used by `FeedbackControl` works inside the drawer because the drawer's parent has `position: relative`.
- Avoids the much harder UX problem of a popover that floats outside an otherwise-modal drawer.

**Alternatives considered**:
- Bottom-sheet on mobile: would require a separate code path for narrow viewports. Rejected for simplicity (FR-013 spirit — keep one component shape).

---

## Decision 6 — Test scope

**Decision**: One new test file `frontend/src/components/settings/__tests__/SettingsMenu.test.tsx` covering:
1. Renders a button with `aria-haspopup="menu"`, `aria-expanded="false"` initially.
2. Clicking the trigger sets `aria-expanded="true"` and renders Account + Help sections.
3. With `isAdmin={true}`, also renders Admin tools section with both items.
4. With `isAdmin={false}`, Admin tools section heading and items are absent from the DOM (FR-006 / SC-003).
5. With one of the user-callback props absent (e.g., `onOpenAuditLog={undefined}`), the corresponding item is omitted (FR-014).
6. With *all* items in a group absent, the group heading is hidden (FR-014).
7. Clicking a menu item invokes the corresponding callback exactly once and closes the menu (FR-007 / FR-008).
8. Clicking outside the menu closes it without invoking any callback.
9. Pressing Escape while the menu is open closes it and returns focus to the trigger.
10. Pressing Tab to the trigger then Enter opens the menu and focuses the first item.
11. Arrow keys move focus between items; Home/End jump to first/last.
12. Tab/Shift-Tab cycle within menu items (focus trap).
13. When `currentStepTargetKey` matches a menu item key (e.g., `sidebar.audit`), the menu opens automatically.
14. When `currentStepTargetKey` transitions away from a menu key, the menu closes automatically.

Existing `DashboardLayout` tests (if any) are updated to expect the consolidated trigger instead of the six individual buttons. Snapshot tests are deleted/regenerated rather than patched.

**Rationale**:
- Each test maps directly to a numbered FR or SC, ensuring the contract is mechanically verified.
- 14 cases is comparable to existing test files (`OnboardingContext.test.tsx`, feature 006's panel tests) and keeps a single file readable.

**Alternatives considered**:
- E2E Playwright/Cypress tests: rejected — out of scope for the existing test pyramid; the project tests at the RTL/Vitest layer.

---

## Coverage check

Every NEEDS CLARIFICATION marker from the spec has been resolved (see `spec.md` § Clarifications). Every Technical Context field is filled with concrete values. No outstanding research items remain. Phase 1 may proceed.
