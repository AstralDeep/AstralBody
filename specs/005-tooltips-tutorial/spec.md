# Feature Specification: Tool Tips and Getting Started Tutorial

**Feature Branch**: `005-tooltips-tutorial`
**Created**: 2026-04-28
**Status**: Draft
**Input**: User description: "As a user, I want tool tips and a getting started tutorial."

## Clarifications

### Session 2026-04-28

- Q: Where should tooltip text live for server-driven (SDUI) components? → A: Hybrid — frontend owns tooltips for static UI (sidebar, panels, modals); backend owns tooltips for SDUI components (per-payload field).
- Q: Where should per-user onboarding state be stored? → A: Backend (PostgreSQL) — one row per user; consistent across devices and browsers.
- Q: Do admins get a different tutorial track? → A: One tutorial; for admin users, additional admin-specific steps are appended after the user-flow steps.
- Q: How should tutorial step copy be edited? → A: Build a backend-stored, admin-editable content surface — tutorial copy is editable in an admin UI without an engineering code review.
- Q: When auto-launching, what counts as a user's "first authenticated session"? → A: Auto-launch for any user without an onboarding-state row, regardless of when their account was created — existing users will see the tutorial once.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - First-Run Guided Tutorial (Priority: P1)

A user signs in for the first time and is greeted by a guided, multi-step tutorial that walks them through the core workflow of the product: starting a chat with an agent, opening the agents panel to see what is available, reviewing their audit log, and giving feedback on a component. The tutorial advances at the user's pace, can be skipped at any step, and remembers that the user has seen it so it does not interrupt them again on the next sign-in.

**Why this priority**: Without onboarding, new users land on a sparse SDUI dashboard with no obvious starting point. The tutorial is the single highest-leverage change for time-to-first-value, and every other piece of help (tooltips, in-product hints) builds on the orientation it provides.

**Independent Test**: Sign in as a fresh user, complete or skip the tutorial, sign out, sign back in, and confirm the tutorial does not re-launch automatically. Each step's "next" and "skip" controls are individually exercisable, so the flow can be QA'd end-to-end without depending on tooltips or replay.

**Acceptance Scenarios**:

1. **Given** a user who has never completed or skipped onboarding, **When** they sign in and the dashboard loads, **Then** the tutorial overlay appears within 2 seconds and highlights the first step.
2. **Given** the user is on any tutorial step, **When** they click "Next", **Then** the overlay advances to the next step and visibly anchors to the new target area.
3. **Given** the user is on any tutorial step, **When** they click "Skip tour" or press Escape, **Then** the overlay closes and is recorded as skipped, and does not re-open on subsequent sign-ins.
4. **Given** the user has completed the tutorial, **When** they sign in again, **Then** the tutorial does not auto-launch.
5. **Given** the user is part-way through the tutorial, **When** they refresh the browser, **Then** they are returned to the same step (or to the next un-seen step) on reload.
6. **Given** a step's target panel is not available to the user (e.g., an admin-only panel for a non-admin), **When** the tutorial reaches that step, **Then** the step is skipped automatically and the user advances to the next applicable step without seeing a broken anchor.

---

### User Story 2 - Contextual Tooltips on Interactive Controls (Priority: P2)

While using the dashboard, the user hovers (or keyboard-focuses) any interactive control — sidebar buttons, agent cards, action icons inside a server-rendered component, and the like — and sees a short, contextual tooltip explaining what it does. Tooltips appear quickly, do not block primary content, and are dismissible by moving the cursor away or pressing Escape.

**Why this priority**: Tooltips reduce ongoing friction for both new and returning users by replacing trial-and-error. They are most valuable *after* the tutorial has given the user a mental model of the dashboard, which is why they sit below the tutorial in priority.

**Independent Test**: With the tutorial completed or skipped, hover every interactive control on the dashboard one at a time and confirm a tooltip with non-empty help text appears for every control that has associated help. Keyboard-focus the same controls via Tab and confirm tooltips appear identically.

**Acceptance Scenarios**:

1. **Given** an interactive control has associated tooltip text, **When** the user hovers it for at least 500 ms, **Then** the tooltip is displayed adjacent to the control.
2. **Given** an interactive control has associated tooltip text, **When** the user focuses the control with the keyboard, **Then** the tooltip is displayed in the same position as on hover.
3. **Given** a tooltip is visible, **When** the user moves the cursor or focus away, **Then** the tooltip closes within 200 ms.
4. **Given** a tooltip is visible, **When** the user presses Escape, **Then** the tooltip closes immediately.
5. **Given** an interactive control does not have associated tooltip text, **When** the user hovers it, **Then** no tooltip is displayed (the dashboard does not show empty tooltip frames).

---

### User Story 3 - Replay Tutorial On Demand (Priority: P3)

After completing or skipping the tutorial, the user finds a "Take the tour" or equivalent help affordance — visible in the sidebar or a help menu — and uses it to replay the tutorial whenever they want a refresher, after a major UI change, or to share the experience with a teammate.

**Why this priority**: Replay is a quality-of-life addition that turns the one-shot tutorial into a long-term documentation surface. It is meaningful but not blocking for either the first-run experience (P1) or the everyday productivity gain (P2).

**Independent Test**: From a state where the tutorial has been completed or skipped, locate the help affordance, trigger it, and confirm the tutorial launches and behaves identically to the first-run flow without re-locking subsequent dashboard interactions.

**Acceptance Scenarios**:

1. **Given** a user who has completed the tutorial, **When** they activate the help affordance, **Then** the tutorial launches at step 1.
2. **Given** the user replays the tutorial and skips it again, **When** they sign in again, **Then** the tutorial still does not auto-launch.

---

### Edge Cases

- **Returning user, no flag stored**: A long-tenured user without an onboarding-state row (e.g., they signed up before this feature shipped) is treated the same as a brand-new user — the tutorial auto-launches once on their next sign-in. After they complete or skip it, the row is persisted and they are not interrupted again.
- **Window resized or layout reflow mid-step**: When the dashboard layout changes while a tutorial step is anchored to a target, the highlight repositions to the new location of the target rather than dangling.
- **Target element is hidden or scrolled offscreen**: The tutorial scrolls the target into view (or, if that is impossible, opens the panel/modal that contains it) before highlighting.
- **Keyboard-only and screen-reader users**: All tutorial steps and tooltips are reachable, dismissible, and announced without a mouse.
- **Tooltip on a transient/server-rendered control**: A control that appears, disappears, or re-renders mid-interaction (typical for SDUI) does not leave an orphan tooltip behind.
- **Mobile / touch device**: There is no hover, so tooltips appear on long-press or via an explicit info affordance, and tutorial step navigation works without hover targets.
- **Tutorial interrupted by a system event** (e.g., session expiry, server-pushed modal): The tutorial defers, lets the system event resolve, and resumes on the same step without losing position.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a guided getting-started tutorial automatically on a user's first authenticated session, defined as any sign-in for a user who has no onboarding-state row on the backend — regardless of when the user's account was created. This means existing/pre-feature users will see the tutorial once on their next sign-in after the feature ships.
- **FR-002**: The tutorial MUST cover, at minimum, the primary user workflow: starting a chat with an agent, opening the agents panel, reviewing the audit log, and providing component feedback. For users with admin role, additional admin-specific steps (covering the feedback admin surfaces — flagged feedback, proposals, quarantine) MUST be appended after the user-flow steps so admins see one continuous tour rather than a separate track.
- **FR-003**: Users MUST be able to advance, go back, or skip the tutorial at every step.
- **FR-004**: System MUST persist per-user onboarding state (not started / in progress / completed / skipped) on the backend (one row per user, server-side of truth) so the tutorial does not auto-launch for users who have already completed or skipped it, and so state is consistent across devices and browsers.
- **FR-005**: Users MUST be able to relaunch the tutorial on demand from a discoverable help affordance, regardless of their onboarding state.
- **FR-006**: System MUST display a contextual tooltip when the user hovers or keyboard-focuses any interactive UI control that has associated help text.
- **FR-007**: Tooltips MUST be dismissible by moving the pointer/focus away or by pressing Escape, and MUST NOT block primary content beyond the dismissal action.
- **FR-008**: Interactive controls without associated help text MUST NOT display a tooltip frame (no "empty" tooltips).
- **FR-009**: System MUST gracefully skip tutorial steps whose target panel or control is not available to the current user (e.g., admin-only surfaces for non-admin users) without surfacing a broken state.
- **FR-010**: Tutorial and tooltips MUST be operable via keyboard alone and MUST be perceivable to assistive technologies (screen readers).
- **FR-011**: Tooltip and tutorial behavior MUST adapt to the user's device — on touch-only devices, tooltips MUST appear via long-press or an explicit info affordance rather than hover, and tutorial controls MUST be reachable without hover.
- **FR-012**: System MUST record meaningful tutorial events (started, completed, skipped, replayed) in the user's audit log so support staff can confirm whether a user has seen onboarding when assisting them.
- **FR-013**: Tutorial state MUST survive a browser reload mid-tour — on reload, the user resumes at the same step rather than losing progress or restarting from step 1.
- **FR-014**: Tooltip text and tutorial step content MUST be authored and maintained as part of the same definition that introduces the UI control or panel, so a new control or panel ships with its help text rather than acquiring it later in a separate workflow. Authoring is split by surface: static UI (sidebar, panels, modals) owns its tooltip copy on the frontend, while server-driven (SDUI) components carry tooltip text on the backend as a per-payload field on the component primitive — meaning a new SDUI component ships its own help text without requiring a frontend change.
- **FR-015**: Tutorial step copy MUST be editable without an engineering code review for typo or wording fixes. The system MUST provide a backend-stored, admin-editable content surface for tutorial step copy, exposed through an admin UI so authorized users (e.g., product, support) can update step titles and bodies without a code change or deploy.
- **FR-016**: Edits to tutorial step copy MUST take effect for end users without requiring a redeploy — a user starting or replaying the tutorial after an admin edit MUST see the updated copy.
- **FR-017**: Changes to tutorial step copy MUST be recorded in the audit log (who edited which step, when, and what changed) so edits are traceable.
- **FR-018**: Only users with admin role MUST be able to view or modify tutorial step copy through the editing surface; non-admin users MUST receive a permission-denied response if they attempt to access it.

### Key Entities

- **Tutorial Step**: A single beat in the guided flow. Has a title, body copy, an optional target (panel, control, or area to anchor to), navigation rules (next / previous / skip), an availability rule (e.g., requires a panel the user can access), and an audience tag indicating whether it is part of the user-flow steps or the appended admin-only steps. Step copy is stored on the backend and editable through the admin content surface.
- **Tooltip Definition**: A short help string bound to a specific interactive control. Includes the control's identity, the help text, and (optionally) richer content such as a learn-more link.
- **User Onboarding State**: Per-user, backend-stored record of whether the tutorial has been started, completed, or skipped, along with the last step the user saw — enough to suppress auto-launch and to resume after a reload, including across a different device or browser.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 80% of new users either complete or explicitly skip the tutorial during their first session (rather than abandoning the page mid-tour).
- **SC-002**: A new user can send their first chat message to an agent within 5 minutes of first sign-in.
- **SC-003**: After completing the tutorial, at least 90% of new users can locate the audit log on their next session without external help, measured by the rate at which they open it unprompted.
- **SC-004**: Tooltips become visible within 500 ms of hover or keyboard focus on every interactive control that has associated help text — verified by spot-check across the dashboard.
- **SC-005**: A returning user can replay the tutorial at any time without losing in-progress chat state or being signed out.
- **SC-006**: The tutorial does not auto-launch for any user who has previously completed or skipped it — measured rate of duplicate auto-launches per user is 0%.
- **SC-007**: All tutorial flows and tooltip interactions are operable via keyboard alone, validated by a manual accessibility pass before release.

## Assumptions

- The tutorial is a first-run experience for **all** users by default. Non-admin users see only the user-flow steps; admin users see the same user-flow steps followed by appended admin-specific steps in a single continuous tour.
- The tutorial covers **today's** core workflow (chat, agents, audit, feedback). Future panels (e.g., new admin tools) can be added incrementally as separate steps.
- Tooltip and tutorial copy is authored in English only for the initial release. Localization is out of scope for this feature, but the design should not actively prevent it.
- Tooltips are *short* — a sentence or two at most. Anything longer is treated as a tutorial step or as documentation linked from a tooltip, not as the tooltip itself.
- Onboarding events are routed through the existing per-user audit log (feature 003); no new audit infrastructure is introduced.
- The replay affordance lives somewhere visible to the user but is not, on its own, a major UI redesign — a help menu entry or sidebar button is sufficient.
