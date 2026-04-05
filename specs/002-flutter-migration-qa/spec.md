# Feature Specification: Flutter Migration QA & Feature Parity

**Feature Branch**: `002-flutter-migration-qa`  
**Created**: 2026-04-03  
**Status**: Draft  
**Input**: User description: "We have just completed the migration away from React to Flutter for the frontend. A lot of aspects are broken with the flutter frontend. the login page should have a username/pass field but also include the oauth login option. Test flutter on apple/android phones and tablets, apple watch, and TV. Use the KEYCLOAK_TEST_USER and KEYCLOAK_TEST_PASSWORD env variables to test. Make sure the test user can log in and test all aspects of the React based system that was ported over to the flutter system to make sure it looks, feels, and operates in a similar manner to the previous frontend."

## Clarifications

### Session 2026-04-03

- Q: Should the deliverable be automated tests, manual QA checklists, or both? → A: Both — run all automatable tests directly on the system (Flutter widget + integration tests against the live stack), and provide manual checklists for everything that cannot be automated (visual parity, device-specific UX).
- Q: Is Android TV in scope for TV testing? → A: No — TV testing is Apple TV only. Remove Android TV references from Story 4.
- Q: What is the acceptance threshold for visual parity (SC-007)? → A: Structural match — same layout, colors, branding, and spacing; minor cross-framework rendering differences are acceptable. No pixel-perfect requirement.
- Q: Is accessibility (a11y) testing in scope? → A: Out of scope for this QA pass.
- Q: Should tests use mocked services or the real stack? → A: Real stack only — the backend Docker container and external Keycloak instance are running and available. All tests (widget and integration) should target the live services.

## User Scenarios & Testing

### User Story 1 — Login with Username & Password (Priority: P1)

A user opens the Flutter app on any supported device and sees a login screen with both a username/password form and an "SSO Login" button. They enter their credentials (or use the Keycloak test account) and are authenticated, landing on the main dashboard.

**Why this priority**: Authentication is the gateway to every other feature. If users cannot log in, nothing else is testable or usable.

**Independent Test**: Using the `KEYCLOAK_TEST_USER` and `KEYCLOAK_TEST_PASSWORD` environment variables, a tester enters the credentials on the login screen and verifies they reach the authenticated dashboard.

**Acceptance Scenarios**:

1. **Given** the user is unauthenticated, **When** they enter valid username and password and tap "Sign In", **Then** they are authenticated and the main dashboard loads.
2. **Given** the user is unauthenticated, **When** they enter invalid credentials, **Then** an inline error message is displayed and the form remains accessible.
3. **Given** the user is unauthenticated, **When** they tap "Sign In with SSO", **Then** the Keycloak OIDC flow launches (browser redirect or in-app browser) and upon successful authentication they land on the dashboard.
4. **Given** the user has a stored session, **When** they reopen the app, **Then** the session is silently restored without requiring re-login (until token expiry).

---

### User Story 2 — Dashboard & Chat Feature Parity on Phone/Tablet (Priority: P1)

A user on an iOS or Android phone or tablet navigates the Flutter app and finds the same core features as the previous React frontend: sidebar with chat history and agent list, real-time chat with the AI agent, SDUI component rendering inline, file upload/attachment support, voice input/output controls, and saved component workflows (save, combine, condense).

**Why this priority**: Phone and tablet are the primary form factors. Feature parity here covers the largest user base and validates the core SDUI rendering pipeline end-to-end.

**Independent Test**: A tester logs in on an iPhone and an Android tablet, opens a chat session, sends messages, receives SDUI-rendered responses, uploads a file, uses voice input, and manages saved components — comparing each interaction against the archived React frontend behavior.

**Acceptance Scenarios**:

1. **Given** an authenticated user on a phone, **When** they open the app, **Then** they see a dashboard with a sidebar (or drawer on small screens) listing chat history and available agents.
2. **Given** an authenticated user in a chat session, **When** the backend sends a SDUI response containing text, cards, tables, charts, or other primitives, **Then** each component renders correctly and is interactive (buttons fire events, inputs accept text).
3. **Given** an authenticated user, **When** they tap the file attachment button, **Then** a file picker opens and the selected file is staged for upload and sent with the next message.
4. **Given** an authenticated user, **When** they use voice input, **Then** their speech is transcribed and inserted into the chat input field.
5. **Given** an authenticated user, **When** they save, combine, or condense components, **Then** the workflow completes and the result appears in their saved components list.
6. **Given** a user on a tablet in landscape orientation, **When** they view the dashboard, **Then** the layout adapts with a persistent sidebar rather than a drawer.

---

### User Story 3 — Visual & UX Parity with React Frontend (Priority: P1)

A user familiar with the previous React-based AstralDeep interface opens the Flutter app and recognizes the same branding, color scheme, layout patterns, and interaction flows. The experience should feel like a natural continuation, not a different product.

**Why this priority**: User trust and adoption depend on a consistent experience. Visual regressions or UX surprises will undermine confidence in the migration.

**Independent Test**: A side-by-side comparison of key screens (login, dashboard, chat, agent permissions modal) between the archived React frontend and the Flutter app, checking branding, color palette, spacing, typography, and interaction patterns.

**Acceptance Scenarios**:

1. **Given** the login screen, **When** compared to the React login, **Then** the branding (logo, app name "AstralDeep", tagline), color gradient, and glass-morphism card style are visually consistent.
2. **Given** the dashboard layout, **When** compared to the React dashboard, **Then** the sidebar structure, chat area proportions, and navigation patterns match.
3. **Given** a chat message with SDUI components, **When** compared to the same components in React, **Then** the rendering style (card borders, button styles, table formatting, chart colors) is visually consistent.
4. **Given** any error state (connection lost, auth failure, empty state), **When** compared to React, **Then** the error messaging and recovery flows are equivalent.

---

### User Story 4 — TV Dashboard Navigation (Priority: P2)

A user on an Apple TV views the AstralDeep dashboard using a remote/D-pad. The interface is optimized for large screens with TV-appropriate font sizes, spacing, and focus-based navigation.

**Why this priority**: TV is a secondary form factor but was specified in the original migration spec (001). It needs to be validated as functional, though it serves fewer users. Android TV is out of scope for this QA pass.

**Independent Test**: A tester launches the app on an Apple TV emulator, navigates entirely with D-pad controls, logs in, and browses dashboard content.

**Acceptance Scenarios**:

1. **Given** a TV user on the login screen, **When** they navigate with D-pad, **Then** focus moves predictably between the username field, password field, Sign In button, and SSO button.
2. **Given** an authenticated TV user, **When** they view the dashboard, **Then** text is large enough to read from typical TV viewing distance (10 feet) and interactive elements have generous touch targets.
3. **Given** a TV user, **When** they navigate the dashboard, **Then** any destination is reachable within 5 D-pad presses from the home screen.

---

### User Story 5 — Apple Watch Glanceable Dashboard (Priority: P3)

A user on an Apple Watch sees a simplified, glanceable version of the AstralDeep dashboard showing key metrics, alerts, and summary cards. Complex components gracefully degrade or are omitted.

**Why this priority**: Watch is the most constrained form factor. It serves a niche use case (quick status checks) and was scoped as P3 in spec 001.

**Independent Test**: A tester launches the app on an Apple Watch simulator, logs in, and verifies that supported components (text, metric, alert, card, button) render correctly while unsupported ones show graceful placeholders.

**Acceptance Scenarios**:

1. **Given** a Watch user, **When** the backend sends components, **Then** only the watch-supported subset (text, metric, alert, card, button) renders; all others show a placeholder.
2. **Given** a Watch user, **When** they interact with a button, **Then** the event fires correctly and the response updates the display.
3. **Given** a Watch user, **When** the dashboard loads, **Then** it loads within 3 seconds.

---

### Edge Cases

- What happens when the backend sends a SDUI component type the Flutter client does not recognize? The client must render a graceful placeholder widget — never crash.
- What happens when the WebSocket connection drops mid-chat? The client must show an offline indicator, auto-reconnect with exponential backoff, and restore the cached SDUI tree.
- What happens when a user rotates their device during a chat session? The layout must adapt responsively without losing chat state or scroll position.
- What happens when the Keycloak server is unreachable during login? The login screen must display a clear error message and allow retry.
- What happens when a user attempts to use voice input on a device without a microphone (e.g., TV)? The voice input control must be hidden or disabled based on device capabilities.

## Requirements

### Functional Requirements

- **FR-001**: The login screen MUST display both a username/password form and a separate "Sign In with SSO" button for Keycloak OIDC authentication.
- **FR-002**: The app MUST authenticate users via username/password against the backend `/auth/login` endpoint using the same credential flow as the React frontend.
- **FR-003**: The app MUST authenticate users via Keycloak OIDC code flow using the BFF proxy at `/auth/token`, consistent with the configuration in the project `.env` file (`VITE_KEYCLOAK_AUTHORITY`, `VITE_KEYCLOAK_CLIENT_ID`).
- **FR-004**: The app MUST support session persistence — storing JWT and refresh tokens in secure storage and restoring sessions on app relaunch.
- **FR-005**: The app MUST perform silent token refresh using the stored refresh token before expiry, redirecting to login only when refresh fails.
- **FR-006**: The dashboard MUST render a sidebar (or drawer on small screens) with chat history and an agent list, matching the React frontend's navigation structure.
- **FR-007**: The chat interface MUST support real-time message streaming via WebSocket, rendering SDUI components inline as they arrive from the backend.
- **FR-008**: The app MUST render all 23+ SDUI primitive types (container, text, button, input, card, table, list, alert, progress, metric, code, image, grid, tabs, divider, collapsible, bar_chart, line_chart, pie_chart, plotly_chart, color_picker, file_upload, file_download) on phone and tablet form factors.
- **FR-009**: The app MUST support file upload via a file picker and attachment staging, sending files with chat messages.
- **FR-010**: The app MUST support voice input (speech-to-text) and text-to-speech output on devices with microphone/speaker capabilities, hiding these controls on unsupported devices.
- **FR-011**: The app MUST support the saved component workflows: save, combine, and condense — matching the React frontend behavior.
- **FR-012**: The app MUST render graceful placeholder widgets for any unrecognized SDUI component types — never crash.
- **FR-013**: The app MUST display an offline indicator when the WebSocket connection is lost and auto-reconnect with exponential backoff.
- **FR-014**: The app MUST cache the last rendered SDUI tree to disk and display it while reconnecting after an app restart.
- **FR-015**: The app MUST adapt layouts responsively across phone, tablet, TV, and watch form factors, including orientation changes.
- **FR-016**: TV form factor MUST support D-pad/remote focus-based navigation with TV-optimized font sizes and spacing.
- **FR-017**: Watch form factor MUST render only the supported component subset (text, metric, alert, card, button) and degrade gracefully for all others.
- **FR-018**: The app MUST visually match the React frontend's branding: "AstralDeep" naming, gradient color scheme, glass-morphism card styling, and overall layout proportions.
- **FR-019**: The app MUST support agent permission management (viewing and modifying agent permissions) via a modal interface, matching the React frontend's agent permissions flow.
- **FR-020**: The app MUST gate device-specific features (microphone, camera, geolocation) based on actual device capabilities reported by the device profile provider.

### Key Entities

- **User Session**: Authenticated user state including JWT access token, refresh token, token expiry, and user profile (id, username, globalRole).
- **SDUI Tree**: The hierarchical component tree received from the backend via WebSocket, rendered dynamically by the client. Cached to disk for offline resilience.
- **Device Profile**: Device metadata (form factor, screen dimensions, pixel ratio, input modality, supported components) sent to the backend at registration so the server can tailor SDUI responses.
- **Chat Session**: A conversation thread with message history, associated agent, and any staged file attachments.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A user can log in using username/password credentials and reach the dashboard within 5 seconds on phone/tablet.
- **SC-002**: A user can log in using Keycloak SSO and reach the dashboard within 10 seconds (including redirect flow) on phone/tablet.
- **SC-003**: 100% of the 23+ SDUI primitive types render correctly on phone and tablet, matching the visual output of the React frontend.
- **SC-004**: Real-time SDUI updates appear within 1 second of backend dispatch on all form factors.
- **SC-005**: The app auto-reconnects after a connection drop within 10 seconds and restores the cached SDUI tree while reconnecting.
- **SC-006**: All core React frontend features (chat, file upload, voice input/output, saved components, agent permissions) are present and functional in the Flutter app.
- **SC-007**: Side-by-side visual comparison of login, dashboard, and chat screens shows structurally consistent branding, colors, and layout between React and Flutter (minor cross-framework rendering differences acceptable).
- **SC-008**: TV navigation reaches any dashboard destination within 5 D-pad presses from the home screen.
- **SC-009**: Watch dashboard loads within 3 seconds and renders the supported component subset without errors.
- **SC-010**: The app runs without crashes across all 5 target form factors (iOS phone, Android phone, iOS tablet, Android tablet, Apple Watch) during a full test session covering login, chat, and SDUI rendering. TV testing covers Apple TV only.

## Out of Scope

- Accessibility (a11y) testing — not included in this QA pass.
- Android TV — TV testing covers Apple TV only.

## Assumptions

- The backend Docker container and external Keycloak instance are running and available — all tests target the live stack (no mocked services).
- The backend SDUI protocol and WebSocket API are unchanged from spec 001 — this spec covers client-side QA and fixes only.
- The `KEYCLOAK_TEST_USER` and `KEYCLOAK_TEST_PASSWORD` environment variables contain valid credentials for a Keycloak test account with appropriate roles.
- The backend `/auth/login` endpoint supports direct username/password authentication (mock auth or Keycloak resource owner password flow).
- The React frontend archived in `frontend-archive-react/` serves as the reference implementation for visual and functional parity comparisons.
- TV testing will use emulators/simulators if physical devices are unavailable.
- The BFF proxy at `/auth/token` handles client secret injection server-side, so the Flutter client never needs the `KEYCLOAK_CLIENT_SECRET`.
