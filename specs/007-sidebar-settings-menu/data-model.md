# Phase 1 Data Model: Condensed Sidebar Settings Menu

**Feature**: 007-sidebar-settings-menu
**Date**: 2026-04-30

## Persisted entities

**None.** This feature introduces no new database tables, no new browser-storage keys, no new server-side stores, and no new audit-event classes. The spec's "Key Entities" section explicitly states: *"This feature does not introduce new persisted entities."*

The existing user-role information (the `admin` role claim from the user's Keycloak JWT, surfaced via `App.tsx:160-177` and passed to DashboardLayout as the `isAdmin` boolean prop) is **read-only consumed** by the new component; it is not extended, re-modeled, or persisted anywhere new.

## In-memory / component-local state

The new `SettingsMenu` component holds the following ephemeral React state:

| Field | Type | Purpose | Lifetime |
|---|---|---|---|
| `open` | `boolean` | Controls popover visibility. | Per component mount. |
| `focusedIndex` | `number` (or `-1`) | Index of the menu item currently focused for keyboard navigation (FR-012). `-1` means no item focused (menu closed or just-opened-no-focus state). | Reset to 0 on open, cleared on close. |
| `triggerRef` | `React.RefObject<HTMLButtonElement>` | Reference to the Settings trigger button so focus can be restored on close. | Component lifetime. |
| `popoverRef` | `React.RefObject<HTMLDivElement>` | Reference to the popover container for click-outside containment checks. | Component lifetime. |
| `itemRefs` | `React.MutableRefObject<Array<HTMLButtonElement \| null>>` | Per-item refs so `focusedIndex` changes can call `.focus()` on the right element. | Component lifetime. |

None of this is persisted. None of it crosses a network or storage boundary. Closing the popover clears `open` and `focusedIndex`; unmounting the component releases everything.

## Read-only inputs (props)

`SettingsMenu` receives these props from `DashboardLayout`:

| Prop | Type | Source | Notes |
|---|---|---|---|
| `isAdmin` | `boolean` | `App.tsx:213` (already piped) | Controls whether the Admin tools section renders (FR-005 / FR-006). |
| `onOpenAuditLog` | `(() => void) \| undefined` | `App.tsx` (already passed to DashboardLayout) | Item omitted when undefined (FR-014). |
| `onOpenLlmSettings` | `(() => void) \| undefined` | `App.tsx` | Same. |
| `onOpenFeedbackAdmin` | `(() => void) \| undefined` | `App.tsx` | Admin-scoped item; only relevant when `isAdmin === true`. |
| `onOpenTutorialAdmin` | `(() => void) \| undefined` | `App.tsx` | Admin-scoped. |
| `onReplayTutorial` | `(() => void) \| undefined` | `App.tsx` | Help item. |
| `onOpenUserGuide` | `(() => void) \| undefined` | `App.tsx` | Help item. |
| `tooltipCatalog` | `Record<string, string>` (existing) | `frontend/src/components/onboarding/tooltipCatalog.ts` | Lookup keyed by `sidebar.<item>` for tooltip text. |

**No new prop types are introduced** — every prop above is already on `DashboardLayout`. `SettingsMenu` is, in effect, a UI-only refactor of `DashboardLayout`'s rendering.

## Context inputs

`SettingsMenu` consumes the existing `OnboardingContext` (one new field):

| Field | Type | Notes |
|---|---|---|
| `currentStepTargetKey` | `string \| null` | NEW field on the existing context, populated by the same selector that `TutorialOverlay` already uses. Read-only from `SettingsMenu`'s perspective. Triggers auto-open / auto-close per FR-010. |

## State transitions

The popover is a finite state machine with two states (`closed` / `open`) and the following transitions:

| From | Event | To | Side effects |
|---|---|---|---|
| closed | trigger clicked | open | `focusedIndex = 0`; first item receives DOM focus on next tick. |
| closed | Enter/Space pressed on trigger (focused) | open | Same as click. |
| closed | tutorial step's `currentStepTargetKey` becomes a menu-item key | open | `focusedIndex = -1` (don't steal focus from the tutorial overlay). |
| open | trigger clicked | closed | Trigger receives focus (FR-012 focus return). |
| open | menu item clicked | closed | Item callback invoked exactly once; trigger receives focus. |
| open | Escape pressed | closed | Trigger receives focus. |
| open | click outside popover & trigger | closed | No focus change (the user's pointer landed elsewhere). |
| open | tutorial step's `currentStepTargetKey` becomes a non-menu key or null | closed | No focus change. |
| open | Arrow Down | open | `focusedIndex = (focusedIndex + 1) % items.length`. |
| open | Arrow Up | open | `focusedIndex = (focusedIndex - 1 + items.length) % items.length`. |
| open | Home | open | `focusedIndex = 0`. |
| open | End | open | `focusedIndex = items.length - 1`. |
| open | Tab | open | Same as Arrow Down (focus stays trapped within items). |
| open | Shift+Tab | open | Same as Arrow Up. |
| open | Enter/Space on focused item | closed | Item callback invoked; trigger receives focus. |

## Validation rules

There is no user-supplied data to validate. The only "validation" is structural:

- **FR-006 (admin gating)**: when `isAdmin === false`, the entire Admin tools group MUST be absent from the rendered tree (verified by `queryByRole('menu')` finding no items with the admin section's identifying attributes).
- **FR-014 (callback omission)**: when an open-callback prop is `undefined`, the corresponding menu item MUST be absent from the rendered tree (not rendered with `disabled` or visually hidden).
- **FR-014 (empty group hiding)**: when every item in a group is absent, the group's section heading and surrounding wrapper MUST be absent from the rendered tree (not rendered as an empty section).

These are tested as hard structural assertions in `SettingsMenu.test.tsx` (see `research.md` § Decision 6).

## Relationships

```text
isAdmin (JWT role)
   │
   └─→ App.tsx:160-177 (extracts roles from realm_access.roles + resource_access.*.roles)
         │
         └─→ DashboardLayout (prop, line 213)
               │
               └─→ SettingsMenu (prop)
                     │
                     ├─ Account section (always rendered if any item present)
                     │     ├─ Audit log     ← onOpenAuditLog
                     │     └─ LLM settings  ← onOpenLlmSettings
                     │
                     ├─ Help section (always rendered if any item present)
                     │     ├─ Take the tour ← onReplayTutorial
                     │     └─ User guide    ← onOpenUserGuide
                     │
                     └─ Admin tools section (only rendered when isAdmin === true
                                              AND at least one admin item callback is defined)
                           ├─ Tool quality  ← onOpenFeedbackAdmin
                           └─ Tutorial admin ← onOpenTutorialAdmin

OnboardingContext.currentStepTargetKey
   │
   └─→ SettingsMenu effect (auto-open / auto-close)
         │
         └─ Compares against SETTINGS_MENU_TARGET_KEYS:
              { sidebar.audit, sidebar.feedback-admin,
                sidebar.tutorial-admin, sidebar.replay-tour,
                sidebar.user-guide /* , sidebar.llm if it exists */ }
```

## Migration impact

Zero. No DB schema changes, no audit-event class additions, no localStorage key changes, no WebSocket message additions, no REST endpoint additions, no env-var changes. Deploying this feature requires only a frontend rebuild.
