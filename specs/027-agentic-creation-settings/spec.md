# Feature Specification: Agentic Agent/Tool Creation & Top-Bar Settings Menu

**Feature Branch**: `027-agentic-creation-settings`
**Created**: 2026-06-10
**Status**: Draft
**Input**: User description: "Agentic agent/tool creation plus a static top-bar settings menu for the server-rendered UI. Two parts: (1) More agentic behavior — the system can create agents and tools on the fly: when a chat request can't be served by existing agents/tools, the orchestrator can generate a new draft agent or new tool mid-conversation (building on the existing draft-agent lifecycle: generate/test/refine/approve from feature 012), surfaced and controllable through the server-driven UI. (2) A static settings menu in the top bar of the web shell where the user can adjust agent permissions (feature 013), personality/personalization settings (feature 025), LLM provider settings (feature 006), audit log (feature 003), onboarding/tutorial replay + user guide (features 005/008), admin tools for admin users, theme, and log out (feature 016 sign-out semantics). It should carry everything the former React settings menu offered."

## Clarifications

### Session 2026-06-10

- Q: Autonomy level for on-the-fly creation when a capability gap is detected? → A: **Auto-create and self-test** — the assistant autonomously generates the draft and runs a self-test against the user's request, presenting working results; only promotion to the live fleet requires explicit user approval. Declining discards the auto-created draft.
- Q: Where may new tools be created? → A: **New/draft agents AND live agents the user owns.** A change to a live agent is prepared and self-tested as a draft revision; applying it requires user approval and automatically re-passes the security/approval gate before going live. If the gate fails, the live agent continues running unchanged.
- Q: Chrome scope for 027? → A: **Top bar + settings menu + the surfaces they open only.** The remaining chrome (sidebar/recent chats, dashboard empty-state, floating chat panel, component-flow toolbar) stays deferred to the server-rendered-chrome feature (see SERVER_RENDERED_CHROME_SPEC.md).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The assistant creates agents and tools on the fly (Priority: P1)

A user asks the assistant for something no currently-available agent or tool can do (e.g., "track the journals I review and remind me of deadlines"). Instead of a dead-end "no tool available" reply, the assistant recognizes the capability gap and acts on it autonomously: it generates a new draft agent (or a draft revision adding a tool to an agent the user owns), runs a self-test against the user's original request, and presents the working result in the same conversation — "I didn't have a way to do that, so I built one; here's what it produced." The user can try it further, ask for refinements, and approve it; approval runs the existing automated security checks and promotes the capability into the user's live fleet, immediately usable. Declining discards the auto-created draft. The user never leaves the chat.

**Why this priority**: This is the headline "more agentic behavior" ask. Today a capability gap ends the conversation; the existing draft-agent machinery (generate → test → refine → approve, feature 012) is fully built server-side but unreachable since the React UI was removed (026). Connecting the gap-detection to that lifecycle inside chat turns the product from a fixed toolbox into a self-extending assistant — the single largest value jump in this feature.

**Independent Test**: In a chat, request a capability that no connected agent provides. Verify the assistant autonomously creates a draft, self-tests it against the request, and presents the result; that the user can refine and approve it; and that after approval the same request succeeds using the newly created capability — all within one session.

**Acceptance Scenarios**:

1. **Given** a chat where no available agent/tool can serve the user's request, **When** the assistant detects the gap, **Then** it tells the user what was missing, autonomously generates a draft agent/tool to fill it, and runs a self-test against the user's original request (instead of only reporting failure).
2. **Given** an auto-created draft whose self-test succeeded, **When** the assistant presents the result, **Then** the user sees the draft's name, what it does, the self-test outcome, and clear approve / refine / discard choices — in the same conversation.
3. **Given** an auto-created draft whose self-test failed, **When** the assistant presents the outcome, **Then** the failure is stated plainly with the option to auto-refine and retry, hand the user the refine flow, or discard — never a silent dead end.
4. **Given** the user is satisfied with a tested draft, **When** they approve it, **Then** the existing automated security checks run; on pass the capability joins the user's live fleet and is immediately usable without a reload; on fail the draft remains in a rejected-but-editable state with the specific failures shown.
5. **Given** a draft that misbehaves during further testing, **When** the user describes what's wrong, **Then** the system refines the draft and the user can re-test — without losing the draft or starting over.
6. **Given** a presented auto-created draft, **When** the user declines it, **Then** the draft is discarded (removed from the drafts list) and the assistant answers as best it can with existing capabilities.
7. **Given** any auto-creation, self-test, refinement, approval, rejection, or discard event, **When** it occurs, **Then** it is recorded in the audit trail attributed to the requesting user.

---

### User Story 2 - A static settings menu in the top bar (Priority: P1)

A signed-in user sees a persistent top bar on every screen of the web app. The top bar contains a clearly-identifiable Settings control that is always in the same place ("static"). Opening it shows a grouped menu carrying every management surface the product offers: an **Account** group (Agents & permissions, LLM settings, Personalization, Audit log, Theme), a **Help** group (Take the tour, User guide), an **Admin tools** group visible only to admins (Tool quality, Tutorial admin), and a **Sign out** action. Selecting an entry opens the corresponding working surface; everything the former React settings menu offered is reachable again.

**Why this priority**: Since the React removal (026), none of these surfaces — agent permissions, personalization, LLM settings, audit log, tutorials, sign-out — has any UI entry point, even though every backend capability behind them is live. This story restores access to the entire management plane in one place; it is co-equal P1 with Story 1 because Story 1's outputs (new agents/tools) are managed through these very surfaces.

**Independent Test**: Sign in as a non-admin: verify the top bar shows the Settings control on every screen, the menu opens with Account/Help groups and Sign out (no Admin tools), and each entry opens its working surface. Sign in as an admin: verify the Admin tools group additionally appears and its entries work. Verify Sign out ends the session per the persistent-login rules.

**Acceptance Scenarios**:

1. **Given** any screen of the signed-in web app, **When** the user looks at the top bar, **Then** a Settings control is present in a consistent location and opens the grouped menu on activation.
2. **Given** the open menu, **When** a non-admin user scans it, **Then** they see the Account group (Agents & permissions, LLM settings, Personalization, Audit log, Theme), the Help group (Take the tour, User guide), and Sign out — and no Admin tools group in the rendered output at all.
3. **Given** the open menu, **When** an admin user scans it, **Then** the Admin tools group (Tool quality, Tutorial admin) is additionally present.
4. **Given** the open menu, **When** the user selects "Agents & permissions", **Then** they can browse their agents (owned, public, drafts), open a specific agent, and adjust its visibility, per-tool enablement/permission kinds, and credentials — with changes persisted only on explicit save and confirmed to the user.
5. **Given** the open menu, **When** the user selects "Personalization", **Then** they can view and edit their assistant's personality ("soul"), review/correct/delete remembered items, and manage scheduled jobs and background consolidation ("dreaming") settings.
6. **Given** the open menu, **When** the user selects "LLM settings", **Then** they can view/edit/test their personal LLM provider configuration as established by feature 006.
7. **Given** the open menu, **When** the user selects "Audit log", **Then** they see their audit trail with filtering and per-entry detail as established by feature 003.
8. **Given** the open menu, **When** the user selects "Sign out", **Then** the session ends following the feature-016 semantics (revocation, offline sign-out queueing when the network is unavailable) and the user lands on the signed-out screen.
9. **Given** the open menu, **When** the user presses Escape or clicks/taps outside it, **Then** the menu closes without side effects.
10. **Given** a narrow/mobile viewport, **When** the user opens the app, **Then** the Settings control remains reachable in the top bar and the menu remains fully usable.

---

### User Story 3 - Manual agent/tool creation and fleet management from the menu (Priority: P2)

A user who prefers deliberate management over in-chat creation opens Settings → Agents & permissions and creates a new agent from a description (the same generate → test → refine → approve journey as Story 1, surfaced as a guided flow), reviews existing drafts, resumes testing a draft they started earlier (including one created from chat), deletes drafts they no longer want, and sees the health/status of their live agents.

**Why this priority**: Chat-driven creation (Story 1) and menu-driven management must converge on the same lifecycle and the same lists — otherwise users get two inconsistent fleets. This story makes the management surface a first-class home for creation, but it is P2 because Story 1 already delivers creation value and Story 2 already delivers management access.

**Independent Test**: From Settings → Agents & permissions, create a new agent from a text description, test it, approve it, and verify it appears in the live list. Verify a draft created earlier from chat (Story 1) appears in the same drafts list and can be resumed, refined, approved, or deleted from here.

**Acceptance Scenarios**:

1. **Given** the Agents & permissions surface, **When** the user starts "Create agent" and submits a description, **Then** a draft is generated and the user is guided to test it, mirroring the chat-driven journey.
2. **Given** a draft created from chat in Story 1, **When** the user opens the drafts list, **Then** that draft appears with its name and status and can be resumed, refined, approved, or deleted.
3. **Given** a live agent the user owns, **When** they view the fleet list, **Then** unhealthy agents remain visible with a clear status rather than disappearing.
4. **Given** a draft the user deletes, **When** the deletion completes, **Then** the draft is gone from the list and cannot be resumed.

---

### User Story 4 - Admin tools stay admin-only (Priority: P3)

A platform admin uses the same Settings menu and additionally sees Admin tools (Tool quality review, Tutorial admin). A non-admin never sees the group — not disabled, not hidden via styling: absent. Authorization for every admin action remains enforced server-side regardless of what the menu shows.

**Why this priority**: Parity with the established admin-gating rules (feature 007). It's P3 because the gating pattern and the admin surfaces already exist server-side; this story is about correctly surfacing — and correctly *not* surfacing — them in the new menu.

**Independent Test**: As admin, open Settings and use Tool quality and Tutorial admin end-to-end. As non-admin, inspect the rendered menu output and verify zero admin-item references; attempt a direct admin action and verify the server rejects it.

**Acceptance Scenarios**:

1. **Given** an admin user, **When** they open the Settings menu, **Then** Admin tools lists Tool quality and Tutorial admin, and each opens its working surface.
2. **Given** a non-admin user, **When** they open the Settings menu, **Then** the rendered output contains no admin entries (verifiable by inspection, not merely visually hidden).
3. **Given** a non-admin who somehow invokes an admin action directly, **When** the request reaches the server, **Then** it is rejected by the existing server-side role checks and audited.

---

### Edge Cases

- **Generation fails or stalls**: If draft generation errors or exceeds a reasonable wait, the user gets a clear, recoverable error with an explicit next action (retry, edit description, abandon) — never a silently vanished proposal (carries forward feature 012's recoverable-error rule).
- **Approval security checks fail**: The draft lands in a rejected-but-editable state with specific failures listed; refining and re-approving re-runs the checks (012 behavior preserved through the new entry points).
- **Missing credentials for a new tool**: If a created tool needs credentials the user hasn't supplied, the tool is clearly marked unavailable and the user is routed to the agent's Permissions surface without losing their in-progress conversation or test session.
- **Duplicate approval**: Approving the same draft twice (e.g., from chat and from the menu concurrently) must not create duplicate live agents.
- **Runaway auto-creation**: Repeated capability gaps in one conversation must not generate an unbounded stream of drafts or self-test loops; at most one auto-created draft per distinct gap, with repeat requests routed to it, and self-test/auto-refine attempts bounded before handing control back to the user.
- **Live agent modified while in use**: Applying an approved draft revision to a live agent must not corrupt in-flight conversations; until the revision passes the gate and is applied, the previous version keeps serving, and a failed gate leaves it untouched.
- **Capability exists but is disabled/unauthorized**: If the request could be served by an existing tool the user has disabled or lacks scopes for, the assistant says so and points at the relevant permissions surface instead of proposing to create a duplicate capability.
- **Admin role changes mid-session**: Menu admin-group visibility reflects the role at next page load (consistent with existing role-check behavior); server-side checks always reflect current role.
- **Offline sign-out**: Sign out with no network must queue revocation per feature 016 and still end the local session.
- **Menu on small screens**: The top bar and menu must remain reachable and usable on narrow viewports (the device-adaptation layer governs presentation, not availability).
- **Personality vs. safety**: Personality/personalization edits made from the menu can never override safety, security, or compliance rules (feature 025 precedence preserved).
- **Mid-conversation surface switches**: Opening a settings surface while a chat turn is processing must neither cancel the turn nor lose the surface's unsaved-state warning semantics (changes persist only on explicit save).

## Requirements *(mandatory)*

### Functional Requirements

#### Agentic creation (Story 1, Story 3)

- **FR-001**: When a chat request cannot be served by the agents/tools currently available to the user, the system MUST detect the capability gap, state what was missing, and autonomously generate a draft agent/tool to fill it rather than only reporting failure (subject to FR-007/FR-008 guards).
- **FR-002**: After auto-creating a draft, the system MUST run a self-test against the user's originating request and present the outcome (success output or plain-language failure) together with explicit approve / refine / discard choices. The system MUST NOT promote anything into the user's live fleet without the user's explicit approval, and a declined draft MUST be discarded (removed from the drafts list).
- **FR-003**: Auto-created drafts MUST go through the existing draft-agent lifecycle (generate → test → refine → approve with automated security checks; rejected drafts stay editable and re-submittable) — the autonomous entry point introduces no second lifecycle.
- **FR-004**: The user MUST be able to further test an auto-created draft from within the same conversation, with its draft status clearly indicated, and refine it conversationally based on observed behavior.
- **FR-005**: On approval, the new agent/tool MUST become immediately usable in the same conversation and appear in the user's fleet without a manual reload; on rejection the specific check failures MUST be shown.
- **FR-006**: The system MUST support creating both whole new agents and new tools, including adding tools to live agents the user owns. A live-agent change MUST be prepared and self-tested as a draft revision; applying it requires the user's explicit approval and MUST automatically re-pass the security/approval gate before going live. If the gate fails, the live agent MUST continue running unchanged.
- **FR-007**: Auto-creation MUST be deduplicated within a conversation: the same unresolved gap yields at most one auto-created draft per conversation, and repeat requests route to the existing draft instead of spawning new ones.
- **FR-008**: If an existing-but-disabled or existing-but-unauthorized tool could serve the request, the system MUST say so and route the user to the relevant permissions surface instead of proposing duplicate capability.
- **FR-009**: Every proposal, confirmation, generation, refinement, approval, rejection, and deletion MUST be recorded in the audit trail, attributed to the acting user.
- **FR-010**: Agents/tools created on the fly MUST default to private visibility (owner-only) and MUST be subject to the same ownership, scope, permission, and credential rules as any other agent/tool — creation grants no capability beyond what the user is already authorized for.
- **FR-011**: All creation interactions (proposals, test sessions, approval prompts, results) MUST be delivered through the server-driven UI like every other surface.

#### Top-bar settings menu (Story 2, Story 4)

- **FR-012**: The web shell MUST present a persistent top bar on every signed-in screen containing a Settings control in a fixed, consistent location.
- **FR-013**: Activating Settings MUST open a grouped menu containing: an **Account** group with Agents & permissions, LLM settings, Personalization, Audit log, and Theme; a **Help** group with Take the tour and User guide; an **Admin tools** group with Tool quality and Tutorial admin; and a **Sign out** action.
- **FR-014**: The Admin tools group MUST be present only for users with the admin role, and entirely absent from the rendered output for everyone else; this gating is UX-only and every admin action MUST remain enforced by existing server-side role checks.
- **FR-015**: Each menu entry MUST open a working surface, restoring at minimum the capabilities each underlying feature established:
  - *Agents & permissions*: browse owned/public/draft agents; per-agent visibility, per-tool enablement and permission kinds, credentials; create/resume/approve/delete drafts (Story 3).
  - *LLM settings*: view, edit, and test the personal LLM provider configuration (feature 006).
  - *Personalization*: view/edit personality ("soul"); view/correct/delete memory items; list/inspect/run-now/pause/resume/delete scheduled jobs; control background consolidation ("dreaming") (feature 025).
  - *Audit log*: filterable personal audit trail with per-entry detail (feature 003).
  - *Theme*: choose/adjust the visual theme with changes persisted to the user's preferences.
  - *Take the tour*: replay the onboarding tutorial (feature 005).
  - *User guide*: open the user guide content (feature 008-era guide).
  - *Tool quality / Tutorial admin*: the existing admin review surfaces (admin only).
- **FR-016**: Surfaces opened from the menu MUST persist changes only on explicit save, MUST confirm success, and MUST surface save failures without losing the user's input (carries forward feature 012/013 rules).
- **FR-017**: The menu MUST close on item selection, outside click/tap, or Escape, and MUST be fully operable by keyboard with appropriate accessibility semantics (open with Enter/Space, navigate with arrows, focus returns to the trigger on close).
- **FR-018**: Sign out MUST follow the feature-016 semantics: revocation of the persistent session, queueing of the revocation when offline, and the established sign-out audit events.
- **FR-019**: An entry whose underlying capability is unavailable for the user MUST be omitted from the menu entirely (no disabled placeholders); a group whose every entry is omitted MUST hide its heading.
- **FR-020**: The top bar and menu MUST remain available and usable across supported device classes; presentation may adapt per device, availability may not.
- **FR-021**: All settings surfaces MUST be delivered through the server-driven UI consistent with the product's established delivery architecture (primitives defined centrally, rendered by the server, adapted per device); no client-side application framework may be reintroduced.

### Key Entities

- **Creation Proposal**: A turn-scoped offer to create a specific agent or tool, derived from a detected capability gap — carries what would be created, what it would do, and its confirmation state. At most one active proposal exists per distinct gap per conversation; a confirmed proposal becomes (or attaches to) a Draft Agent.
- **Draft Agent** *(existing)*: The unit of the existing generate → test → refine → approve lifecycle; gains a new origin ("created from chat") alongside the existing manual origin. Retained until owner deletion; private to its owner.
- **Settings Menu Entry**: A non-persisted, role- and availability-filtered navigation item belonging to a group (Account, Help, Admin tools, Sign out).
- **User Role** *(existing)*: Drives Admin tools visibility (UX) while server-side checks remain authoritative.
- **Personalization Profile / Memory Item / Scheduled Job** *(existing, feature 025)*: Surfaced read/write through the Personalization entry; no schema changes implied by this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user who requests an unserved capability can go from the assistant's proposal to an approved, working agent/tool — without leaving the conversation — in under 10 minutes for a typical request (95th percentile of guided test sessions).
- **SC-002**: 0 capability-gap conversations end in a bare "can't do that" when creation is possible: 100% of detected gaps yield either a creation proposal or an explicit pointer to an existing-but-disabled capability.
- **SC-003**: 100% of the former React settings inventory (Agents & permissions, LLM settings, Personalization, Audit log, Theme, Take the tour, User guide, Tool quality, Tutorial admin, Sign out) is reachable from the new top-bar Settings menu, verified surface-by-surface.
- **SC-004**: The Settings control is reachable from every signed-in screen in at most 1 activation (it is always visible in the top bar), and any settings surface opens within 2 activations from anywhere in the app.
- **SC-005**: A non-admin's rendered menu output contains zero admin-item references, across 100% of non-admin sessions inspected.
- **SC-006**: 100% of creation-lifecycle events (proposal → deletion) and sign-out events appear in the audit trail with correct user attribution.
- **SC-007**: Drafts created from chat and drafts created from the menu appear in one unified drafts list, with zero divergence between the two entry points in 100% of tested flows.
- **SC-008**: Sign out completes (or queues, when offline) and locally ends the session in under 5 seconds in 95% of attempts.

## Assumptions

- **A1**: The existing draft-agent lifecycle (feature 012: generate, on-demand start for testing, refine, approve with automated security checks and no human review step, indefinite draft retention, owner deletion) is reused as-is; this feature adds entry points and conversational surfacing, not a new lifecycle.
- **A2**: "Static settings menu" means a persistently visible Settings control in a fixed top-bar position on every signed-in screen — not a configurable or movable element.
- **A3**: The menu inventory is the union of the former React settings menu (feature 007: Audit log, LLM settings, Personalization, Take the tour, User guide, Tool quality, Tutorial admin) plus the items feature 007 deliberately kept outside the menu that now have no other home after the sidebar's removal (Agents & permissions, Sign out) plus Theme. New chat and connection-status indicators are top-bar/shell concerns, not menu entries.
- **A4**: Admin detection continues to use the existing role claim from the authentication layer; mock-auth development mode (admin-by-default) continues to work.
- **A5**: Personalization data boundaries (non-PHI durable memory, PHI exclusion gates, personality-cannot-override-safety) are governed by feature 025 and are unchanged here; this feature only provides the surface.
- **A6**: Per-user LLM configuration storage/validation semantics are governed by feature 006 and are unchanged here.
- **A7**: Sign-out/revocation semantics (365-day persistent login, user-switch revocation, offline revocation queue, auth audit events) are governed by feature 016 and are unchanged here.
- **A8**: Tutorial step content is owned by feature 005's tutorial system; this feature must keep step targets resolvable from the new menu but does not redefine tutorial content.
- **A9**: On-the-fly creation is available to every authenticated user for private agents/tools (the existing ownership model); making a created agent public continues to follow the existing visibility rules and checks.
