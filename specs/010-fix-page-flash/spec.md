# Feature Specification: Fix Page Flash from Repeated Feedback Quality Requests

**Feature Branch**: `010-fix-page-flash`
**Created**: 2026-05-01
**Status**: Draft
**Input**: User description: "As a user, I want the screen not to flash on page load and when new UI components are being added to the screen. I believe the feedback mechanism calls are doing this. The docker logs show repeated GET /api/admin/feedback/quality/flagged?limit=100 requests firing in rapid succession during page load, historical chat loading, and new queries. I'm almost positive these admin feedback quality requests are causing the screen flash."

## Clarifications

### Session 2026-05-01

- Q: Should the fix apply only to the observed feedback-quality endpoint, to all admin-only background fetches with this anti-pattern, or to all background data fetches (admin and non-admin) issued from globally mounted regions? → A: All background data fetches (admin and non-admin) that fire from globally mounted regions.
- Q: What is the canonical rule for how often a given background endpoint may be re-fetched during normal use? → A: Once per session per endpoint; refreshed only on explicit user action or view open. This limit MUST NOT apply to backend-pushed SDUI components (server-driven UI streams), which continue to flow to the frontend without per-session caching.
- Q: Should the implementer discover and fix every offending fetch found, or should the spec list a fixed set up front? → A: Implementer audits all globally mounted regions and fixes every offending fetch; acceptance is pattern-based, not endpoint-list-based.
- Q: How should "globally mounted region" be defined for audit purposes? → A: A region rendered on every authenticated route regardless of which view the user is on (layout shell, persistent sidebar/header, app-level providers). Route-scoped regions are out of scope even if they mount once per visit.
- Q: Is fixing the SDUI streaming flash (existing components remounting when new ones stream in) part of this feature, or only the redundant-fetch flash? → A: Both. This feature must eliminate redundant-fetch flashes AND streaming-reconciliation flashes (existing components must not remount when new SDUI components arrive).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stable screen on initial page load (Priority: P1)

When a user first opens the application, the page should render and remain visually stable. Currently the screen flashes (re-renders/remounts visibly) immediately after load while a background data check fires repeatedly. The user perceives this as a broken or unfinished UI.

**Why this priority**: First impression. A flashing UI on the very first interaction undermines confidence in the product and is the most user-visible defect of the three observed scenarios.

**Independent Test**: Open the application from a cold state and observe the first 5 seconds of the dashboard. The visible UI must not flash, blink, or remount, and the network activity should not show the same data-quality endpoint being called more than once during that window.

**Acceptance Scenarios**:

1. **Given** a user opens the application for the first time in a session, **When** the dashboard finishes loading, **Then** no visible flash, flicker, or component remount occurs during or after the initial render.
2. **Given** a user is viewing the dashboard immediately after load, **When** background data-quality information is being retrieved, **Then** the retrieval happens at most once for that load and does not cause any visible re-render of the surrounding UI.

---

### User Story 2 - Stable screen when loading a historical chat (Priority: P1)

When a user selects a previous conversation from history, the chat content should appear smoothly without the surrounding layout flashing. Today, opening a historical chat triggers a burst of repeated background requests that coincide with visible flashes.

**Why this priority**: Reviewing prior conversations is a core workflow. Flashes during this action interrupt reading flow and feel like the app is reloading itself unexpectedly.

**Independent Test**: With at least one historical chat available, click into it and observe the transition. The chat content should appear without surrounding panels (sidebar, header, chat shell) flashing or remounting, and no repeated bursts of the same background request should fire.

**Acceptance Scenarios**:

1. **Given** a user has multiple historical chats, **When** they click on one to load it, **Then** only the message content area updates and no other layout regions flash or remount.
2. **Given** a historical chat is being loaded, **When** background data-quality information is needed, **Then** any related request fires no more than once for the load action.

---

### User Story 3 - Stable screen when submitting a new query (Priority: P1)

When a user sends a new message, the response area should update without the surrounding UI flashing. Today, sending a query triggers another burst of repeated background requests that coincide with visible flashes as new UI components stream in.

**Why this priority**: Sending queries is the most frequent action in the product. Flashes on every send compound user frustration and make the app feel unstable under normal use.

**Independent Test**: Submit a new query and observe the UI as the response renders. The chat shell, sidebar, and header must remain stable while only the message stream updates, and the same background endpoint must not be called repeatedly during streaming.

**Acceptance Scenarios**:

1. **Given** a user is on an active conversation, **When** they submit a new query, **Then** only the message stream area updates and the rest of the UI does not flash or remount.
2. **Given** a query is in progress and new UI components are streaming in, **When** components are added to the screen, **Then** their addition is smooth and does not cause the existing UI to flash.
3. **Given** any user action (page load, chat switch, query submit), **When** background quality/feedback data is fetched, **Then** the fetch occurs at most once per logical action, not repeatedly.

---

### Edge Cases

- A user without admin privileges should not see any visible side effects from admin-only background data even when calls are blocked, suppressed, or skipped.
- If a background data-quality fetch fails, the user-facing UI should remain stable (no flash, no error banner) — the failure must be silent to the regular user.
- When the user navigates rapidly between chats, repeated triggers should be coalesced so the UI does not flash even under fast clicking.
- When the user is idle for an extended period, background polling (if any) must not redraw or flash the UI.
- When a streaming response renders many new components in succession, each addition must be additive without causing already-rendered components to remount.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The application MUST render the initial page load without any visible flash, flicker, or full-region remount of layout components (sidebar, header, chat shell, dashboard panels).
- **FR-002**: Loading a historical chat MUST update only the message content region; surrounding layout components MUST remain stable and not flash or remount.
- **FR-003**: Submitting a new query MUST update only the active message stream region; surrounding layout components MUST remain stable and not flash or remount.
- **FR-004**: Any background data fetch (admin or non-admin) covered by this fix MUST be retrieved at most once per user session per endpoint, with refresh occurring only on explicit user action (manual refresh button, opening the consuming view, etc.) — NOT on every page load, chat switch, or query submit.
- **FR-005**: Permission-restricted background data MUST only be requested when the requesting user has the role/permission required to view it; users without the required permission MUST NOT trigger such requests.
- **FR-006**: Streaming addition of new UI components into a response MUST be additive — already-rendered components MUST NOT remount, re-key, or flash when new SDUI components arrive from the backend stream. Eliminating streaming-reconciliation flashes is in scope for this feature alongside eliminating redundant-fetch flashes.
- **FR-007**: Failures of any background data retrieval MUST NOT cause user-visible visual changes for users who would not otherwise have a UI surface for that data (no flash, no error toast).
- **FR-008**: Within a single user session, the same background data endpoint covered by this fix MUST NOT be invoked more than once unless an explicit user-initiated refresh or view-open action requests it.
- **FR-009**: Background data fetches MUST be issued only when a UI surface that consumes the data is actually visible to the user, not from globally mounted layout components.
- **FR-010**: The fix MUST apply to all background data fetches (admin and non-admin) that are currently issued from globally mounted regions, not only to the observed feedback-quality endpoint.
- **FR-011**: Backend-pushed Server-Driven UI (SDUI) component streams MUST be excluded from the per-session fetch cap; SDUI components continue to flow from backend to frontend in real time without session-scoped caching or deduplication.
- **FR-012**: Acceptance for this feature MUST be pattern-based: no globally mounted UI region may issue a background data fetch on render. The implementer is responsible for auditing all such regions and remediating every offending fetch found, not only those named in this specification.
- **FR-013**: For audit purposes, a "globally mounted region" is defined as any UI region that is rendered on every authenticated route regardless of which view the user is currently on — for example, the layout shell, persistent sidebar, persistent header, and app-level data/state providers. Route-scoped regions (e.g., the admin dashboard, settings panel, individual feature pages) are explicitly out of scope of this audit even if they mount once per visit and could in principle be optimized similarly.

### Key Entities

- **User Session**: The active in-app session for a single user. Carries the user's role/permissions, which gate whether admin-only background data is requested at all.
- **Background Data-Quality Check**: A non-user-facing data fetch used to populate an admin-only quality/flagged-items view. Its lifecycle (when it fires, how often, who triggers it) is the primary subject of this feature.
- **Layout Region**: A persistent UI area (sidebar, header, dashboard shell, chat shell) that should not visually change in response to background data fetches.
- **Message Stream Region**: The transient UI area that legitimately updates as a new message or historical chat content arrives.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero visible page flashes occur during initial page load, historical chat loading, and new query submission — including no flashes from existing UI components remounting when new SDUI components stream in — as observed in 100% of manual smoke runs across the three primary scenarios.
- **SC-002**: Each in-scope background data endpoint is retrieved at most one time per user session (with additional fetches occurring only on explicit user action or view-open), down from the current observed rate of dozens of repeated calls per logical user action. Backend-pushed SDUI component streams are excluded from this cap.
- **SC-003**: Non-admin users generate zero requests for admin-only background data-quality information during any session.
- **SC-004**: For admin users, total background data-quality requests during a typical 5-minute session drop by at least 95% compared to the current observed volume.
- **SC-005**: Time to a stable, non-flashing first paint of the dashboard is achieved within 2 seconds of page load on a typical broadband connection.
- **SC-006**: User-reported issues mentioning "flashing", "flickering", or "screen blinking" trend to zero after the fix is shipped.

## Assumptions

- The repeated `GET /api/admin/feedback/quality/flagged?limit=100` requests observed in docker logs are issued by a globally mounted UI region (e.g., layout, sidebar, or a top-level provider) and re-fire on every render of that region, which is why they correlate with page load, chat switching, and new-query streaming.
- The feedback-quality data is admin-only and not needed by general users; restricting the request to admin-visible surfaces is acceptable product behavior.
- Caching/deduplication of identical background fetches over a short window is acceptable; freshness requirements for this admin data tolerate "at most once per action" semantics.
- The user-perceived "flash" is caused by component remounts (not just network activity); eliminating the redundant fetches is expected to also eliminate the remount churn that produces the flash, but visual stability — not just call count — is the acceptance bar.
- "Page load", "historical chat load", and "new query" are the three logical actions in scope; other admin-only screens that intentionally poll this data are out of scope for this fix.
