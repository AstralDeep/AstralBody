# Feature Specification: Condensed Sidebar Settings Menu

**Feature Branch**: `007-sidebar-settings-menu`
**Created**: 2026-04-30
**Status**: Draft
**Input**: User description: "As a user, I want a condensed view of all the sidebar buttons. Add a settings/options/something button that shows all the new buttons (audit, tutorial, etc). maybe user and admin scoped"

## Clarifications

### Session 2026-04-30

- Q: Beyond the 6 utility buttons, which other top-level sidebar elements (New chat, Logout, Status section) move into Settings? → A: None — New chat, Logout, and the Status section all stay outside Settings; only the 6 utility buttons move.
- Q: What UI form should the Settings menu take (popover, slide-out panel, modal sheet, inline expansion)? → A: Anchored popover/dropdown attached to the Settings sidebar entry — no backdrop scrim, closes on outside click or Escape (same lightweight inline pattern used by `FeedbackControl`).
- Q: How should menu items behave when their underlying open-callback is unavailable? → A: Omit the item entirely (matches today's per-button conditional rendering). If all items in a group are omitted, the group heading is also hidden.
- Q: When the tutorial highlights an item inside Settings, what happens to the menu after the user advances past that step? → A: Auto-close the menu as soon as the tutorial advances past the in-menu step (or when the next step targets an element outside the menu).
- Q: Should the spec explicitly state that admin-item menu visibility is UX-only and authorization is enforced server-side? → A: Yes — add an explicit Security & Authorization requirement so client-side menu gating is never mistaken for the security boundary, and require server-side admin-role checks for every admin-scoped action regardless of menu state.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reduce Sidebar Clutter Behind a Single Settings Entry (Priority: P1)

A signed-in user opens the workspace and sees a sidebar with chat history and a small number of primary entries. Secondary utility actions (viewing their personal audit log, configuring their LLM provider, replaying the tutorial, opening the user guide, and any admin tools) live behind a single "Settings" entry that opens a grouped menu. The user clicks Settings, scans the grouped list, picks the action they want, and is taken to the same panel they would have reached today.

**Why this priority**: This is the entire reason the feature exists. Without consolidation, the sidebar continues to grow one button per shipped feature, and primary content (chat history) is pushed down or hidden. Delivering this story alone — even without admin scoping or other niceties — is a usable product improvement on its own.

**Independent Test**: Open the workspace as any signed-in user; verify the sidebar shows at most two utility entries (Agents and Settings) instead of the current six-plus; click Settings; verify all previously-direct entries (Audit log, LLM settings, Take the tour, User guide) are reachable from inside the menu and open the same panels they did before.

**Acceptance Scenarios**:

1. **Given** a signed-in user with no admin role, **When** they open the workspace, **Then** the sidebar shows Agents and Settings as the only utility entries (chat history continues to render as before).
2. **Given** the Settings menu is closed, **When** the user clicks the Settings entry, **Then** a grouped menu opens listing Audit log, LLM settings, Take the tour, and User guide.
3. **Given** the Settings menu is open, **When** the user clicks any item, **Then** the menu closes and the corresponding panel opens (the same panel that opened from the original sidebar button).
4. **Given** the Settings menu is open, **When** the user clicks outside the menu OR presses Escape, **Then** the menu closes without opening any panel.
5. **Given** a saved deep-link URL (e.g., a bookmark to the audit log panel), **When** the user opens that URL, **Then** the corresponding panel opens directly without the user having to go through the Settings menu.

---

### User Story 2 - Admin-Only Tools Grouped and Hidden From Non-Admins (Priority: P2)

A platform admin opens the same workspace and sees the same Settings entry, but the menu additionally surfaces an "Admin tools" section with the admin-only items (Tool quality review, Tutorial admin). A non-admin signing in to the same product never sees the Admin tools section at all — not greyed-out, not present.

**Why this priority**: Admin tools currently render with no visual grouping; they sit alongside the user's own audit log and LLM settings. Grouping them under a clear "Admin" label inside the menu reduces the chance a confused user clicks an admin-scoped item, and hiding the section entirely for non-admins is consistent with how the buttons are already conditionally rendered today (so this is a UX/clarity improvement, not a security boundary change).

**Independent Test**: Sign in with an admin account; open Settings; verify "Admin tools" section is visible with Tool quality and Tutorial admin items. Sign in with a non-admin account; open Settings; verify no admin section heading or items appear.

**Acceptance Scenarios**:

1. **Given** a user whose role includes admin, **When** they open the Settings menu, **Then** an "Admin tools" section is visible containing Tool quality and Tutorial admin.
2. **Given** a user whose role does not include admin, **When** they open the Settings menu, **Then** no Admin tools section heading appears and no admin items are listed.
3. **Given** an admin clicks Tool quality from inside the Settings menu, **When** the admin panel opens, **Then** the panel behaves identically to opening it from a sidebar button today (same URL state, same content).

---

### User Story 3 - Help Items Discoverable From the Same Place (Priority: P3)

A user who needs help (replaying the tutorial or reading the user guide) finds those entries in the same Settings menu, grouped under a clear "Help" label, instead of scrolling past unrelated items.

**Why this priority**: This is a discoverability polish. The product already has both "Take the tour" and "User guide" buttons; this story ensures consolidation does not bury them. A first-time user who is mid-task and needs help should be able to find these without leaving the chat workspace.

**Independent Test**: Open Settings; verify a "Help" group heading exists with Take the tour and User guide as its only items; click each; verify the tour replays / user guide opens the same way it does today.

**Acceptance Scenarios**:

1. **Given** the Settings menu is open, **When** the user scans the menu, **Then** a "Help" section heading is visible with at least Take the tour and User guide listed below it.
2. **Given** the user clicks Take the tour from inside the menu, **When** the click is registered, **Then** the tutorial replays from the first step (same behavior as today's sidebar button).

---

### Edge Cases

- **Tutorial step targets a moved button**: If the onboarding tutorial includes a step that highlights the (now-moved) Audit log, LLM settings, Tool quality, Tutorial admin, Take the tour, or User guide entry, the tutorial MUST open the Settings menu before highlighting the target so the user actually sees the highlighted element. When the user advances past the in-menu step (or when the next step targets an element outside the menu), the menu MUST auto-close so it does not obscure subsequent targets. (The tutorial steps themselves are owned by feature 005 and edited via the tutorial admin panel, but their step content/target identifiers must continue to resolve.)
- **Mobile drawer**: On a narrow viewport the sidebar collapses into a drawer. Settings must work the same way — the drawer opens, the user clicks Settings, the menu opens *inside* the drawer (or anchored such that it remains visible).
- **Collapsed icon rail (desktop)**: When the desktop sidebar is collapsed to its icon rail, Settings must be reachable from the rail with an icon and tooltip, exactly as the individual buttons are today.
- **Settings clicked while another panel is open**: If a user already has, e.g., the Audit log panel open and clicks Settings → LLM settings, the system should behave the same way it does today when one panel is open and another sidebar button is clicked (existing behavior — no new requirement, but the spec must not regress it).
- **Admin role added/removed mid-session**: A user whose admin role changes during their session does not need real-time re-rendering — the menu's admin section will reflect the new role on next page load. (Consistent with today's behavior of role checks at sign-in.)
- **No items in a group**: If, in some configuration, no help items or no admin items are available, the corresponding section heading should not render (no empty groups).
- **Menu item callback unavailable**: If the open-callback for an individual menu item is unavailable (feature not wired, prop missing, route disabled), the item itself MUST NOT render — it is omitted, not disabled. This composes with the empty-group rule: a group whose every item is omitted also hides its heading.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The workspace MUST present a single "Settings" entry in the sidebar that, when activated, opens a grouped menu of utility actions as an anchored popover (no backdrop scrim) attached to the Settings entry itself.
- **FR-002**: The Settings entry MUST be reachable from the expanded sidebar, the collapsed icon rail, and the mobile sidebar drawer.
- **FR-003**: The Settings menu MUST contain an "Account" group with at minimum: Audit log, LLM settings.
- **FR-004**: The Settings menu MUST contain a "Help" group with at minimum: Take the tour, User guide.
- **FR-005**: The Settings menu MUST contain an "Admin tools" group with at minimum: Tool quality, Tutorial admin — but ONLY when the signed-in user has the admin role.
- **FR-006**: When the signed-in user does not have the admin role, the Admin tools group heading and all admin items MUST be entirely absent from the menu (not rendered as disabled or hidden via CSS).
- **FR-007**: Activating any item in the Settings menu MUST open the same panel and produce the same URL state as activating the original sidebar button for that item produces today.
- **FR-008**: The Settings menu MUST close when the user (a) selects an item, (b) clicks outside the menu, or (c) presses Escape.
- **FR-009**: Existing URL deep-links to specific panels (the per-feature query parameters established by features 003–006) MUST continue to open those panels directly without going through the Settings menu.
- **FR-010**: The onboarding tutorial MUST continue to successfully highlight any step target that previously lived as a top-level sidebar button — including for items that now live inside the Settings menu. The menu MUST auto-open before highlighting an in-menu target, and MUST auto-close when the tutorial advances past the in-menu step (or when the next step's target is not inside the menu).
- **FR-011**: The Agents entry, the New chat (+) action, the Sign out (logout) action, and the Status section (Orchestrator / Agents / Tools indicators) MUST all remain outside the Settings menu and MUST continue to render as top-level sidebar elements. Only the six utility buttons (Audit log, LLM settings, Tool quality, Tutorial admin, Take the tour, User guide) move into Settings.
- **FR-012**: The Settings menu MUST conform to the full WAI-ARIA menu pattern. Specifically: tabbing to the Settings entry and pressing Enter or Space opens the menu and moves focus to the first item; Up/Down arrow keys move focus between items; Home/End move focus to the first/last item; focus is trapped inside the open menu (Tab/Shift-Tab cycles within the menu items); Enter or Space on a focused item activates it; Escape closes the menu and returns focus to the Settings entry. The Settings entry MUST expose the appropriate ARIA roles/attributes (`aria-haspopup`, `aria-expanded`, `role="menu"` / `role="menuitem"`, etc.).
- **FR-013**: The Settings menu MUST NOT introduce any new dependency on a third-party UI library; it must be built using the same primitives the project already uses.
- **FR-014**: When the open-callback for a menu item is unavailable, the item MUST be omitted from the rendered menu (not rendered as disabled). When every item in a group is omitted, the group heading MUST also be hidden so the menu contains no empty groups.
- **FR-015**: Hiding the Admin tools group from non-admins is a UX-only measure and MUST NOT be relied upon as the authorization boundary. Every admin-scoped action surfaced from the Settings menu MUST be enforced by the existing server-side role checks (REST endpoints, WebSocket handlers, and the audit middleware) regardless of whether the menu rendered the item or not. Whenever a new admin item is added to the Settings menu in the future, the corresponding backend route MUST be verified to enforce the admin role server-side before the menu item is shipped.

### Key Entities

This feature does not introduce new persisted entities. It surfaces existing user role information (already provided by the authentication layer) to control which menu groups render.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The number of utility entries (non-chat-history sidebar items) visible at first paint drops from 7 to 2 (Agents and Settings) for every signed-in user, regardless of role.
- **SC-002**: 100% of existing per-feature deep-links (the URLs that today open the audit log, LLM settings, tool quality admin, tutorial admin, and user guide panels directly) continue to open the correct panel without code changes outside the sidebar component, verified by manual smoke test of each link.
- **SC-003**: A non-admin user inspecting the rendered DOM of the open Settings menu finds zero references to admin-only items (Tool quality, Tutorial admin).
- **SC-004**: A first-time user can locate and open the user guide within 10 seconds of being told "the user guide is somewhere in the sidebar," measured against the current baseline (where the User guide is its own top-level entry).
- **SC-005**: Replaying the existing onboarding tutorial completes successfully end-to-end with all currently-shipped steps still reaching their highlighted target element.

## Assumptions

- **A1**: Agents stays as a primary top-level sidebar entry. It is a workflow surface (used during normal task execution), not a setting. The feature description's "all the sidebar buttons" is interpreted as "all the *secondary/utility* sidebar buttons added by features 003–006." (Confirmed in Clarifications Q1 — see Section above.)
- **A2**: The Settings menu is a transient anchored popover/dropdown attached to the Settings sidebar entry (no backdrop scrim, closes on outside click or Escape). It does not get its own URL query parameter. Per-feature panels (audit, llm, etc.) keep their existing URL state.
- **A3**: "Take the tour" and "User guide" are user-scope (everyone gets help), not admin-scope.
- **A4**: Admin role detection follows the existing pattern in the auth layer (role claim from the user's JWT). This feature does not introduce a new admin-detection mechanism.
- **A5**: Mock-auth development mode (which currently grants admin to the dev user) continues to work — the Admin tools section will be visible in dev.
