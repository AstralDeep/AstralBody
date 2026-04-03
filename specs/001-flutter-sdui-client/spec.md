# Feature Specification: Flutter SDUI Thin Client

**Feature Branch**: `001-flutter-sdui-client`  
**Created**: 2026-04-03  
**Status**: Draft  
**Input**: User description (original): "Replace the frontend with Flutter to make the system device agnostic. The client device frontend acts as a dummy renderer based on the backend SDUI components. Target devices: Apple & Android phones and tablets, Apple Watch, and TV."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Phone/Tablet User Interacts with SDUI Dashboard (Priority: P1)

A user opens the AstralBody app on their iPhone, Android phone, or tablet. The app connects to the backend, authenticates via Keycloak, and receives a full SDUI component tree describing the dashboard layout. The Flutter client renders each component (text, cards, charts, tables, buttons, inputs) faithfully as received. When the user taps a button or submits a form, the client sends the action to the backend and re-renders with the updated component tree. The user never encounters a hard-coded screen—every view is driven by backend responses.

**Why this priority**: Phone and tablet are the highest-volume device categories. This story validates the core SDUI rendering pipeline end-to-end on the most common form factors.

**Independent Test**: Can be fully tested by launching the app on a phone/tablet emulator, authenticating, and verifying that the backend-composed dashboard renders correctly with all component types. Delivers the foundational rendering engine.

**Acceptance Scenarios**:

1. **Given** the user has valid Keycloak credentials, **When** they open the app on a phone, **Then** the app authenticates and displays the backend-composed dashboard within 3 seconds.
2. **Given** a SDUI component tree containing text, card, button, table, and chart primitives, **When** the client receives it, **Then** every component renders correctly on the screen without layout overflow or clipping.
3. **Given** the user taps a button in the rendered UI, **When** the action is sent to the backend, **Then** the backend returns an updated component tree and the client re-renders accordingly.
4. **Given** the user is on a tablet, **When** the same SDUI tree is received, **Then** the layout adapts to the larger screen while preserving content and component hierarchy.

---

### User Story 2 - Real-Time Chat and Agent Interaction on Mobile (Priority: P1)

A user opens the chat interface on their mobile device. The app establishes a WebSocket connection. Messages from backend agents (including inline SDUI components such as tables, charts, and alerts) stream in real time. The user can type messages, upload files, and interact with inline rendered components—all driven by backend instructions.

**Why this priority**: Real-time agent interaction is the primary value proposition of AstralBody. Without WebSocket-based SDUI streaming, the app provides no differentiated functionality.

**Independent Test**: Can be tested by connecting to the backend WebSocket from a mobile emulator, sending a chat message, and verifying that streamed SDUI components render inline within the chat.

**Acceptance Scenarios**:

1. **Given** the user is authenticated and on the chat screen, **When** a message with embedded SDUI components arrives via WebSocket, **Then** the components render inline within the chat flow.
2. **Given** the user types a message and taps send, **When** the backend processes it, **Then** the response (including any SDUI components) appears in real time without page reload.
3. **Given** the WebSocket connection drops, **When** connectivity is restored, **Then** the app reconnects automatically and re-syncs the conversation state.

---

### User Story 3 - TV User Browses Dashboard (Priority: P2)

A user launches AstralBody on their smart TV (Android TV, Apple TV, or similar). The app renders the same backend-driven dashboard optimized for a large screen viewed from a distance. Navigation is handled via remote/D-pad controls. The SDUI layout adapts to TV-appropriate sizing—larger fonts, focus-based navigation, and simplified interaction patterns.

**Why this priority**: TV extends the device-agnostic promise to large-screen environments. It validates that the SDUI architecture works with input modalities beyond touch.

**Independent Test**: Can be tested by launching the app on a TV emulator, navigating the dashboard with D-pad controls, and verifying that all components render legibly and focus navigation works.

**Acceptance Scenarios**:

1. **Given** the app is launched on a TV, **When** the backend sends a SDUI component tree, **Then** the client renders components with TV-appropriate sizing (large text, generous spacing).
2. **Given** the user navigates with a D-pad/remote, **When** they move focus between interactive elements, **Then** focused elements are clearly highlighted and selectable.
3. **Given** a SDUI tree contains interactive components (buttons, forms), **When** the user selects them with the remote, **Then** actions are dispatched to the backend and the UI updates accordingly.

---

### User Story 4 - Apple Watch User Receives Glanceable Updates (Priority: P3)

A user wearing an Apple Watch receives a notification or opens the AstralBody companion app. The watch displays a simplified, glanceable SDUI view—key metrics, alerts, or status cards rendered from the backend component tree. The watch app supports minimal interaction: tapping a card to acknowledge an alert or view a detail. Complex workflows (chat, file upload) are not available on the watch.

**Why this priority**: Watch is a companion experience with a constrained screen. It extends platform reach but is not the primary interaction surface.

**Independent Test**: Can be tested by launching the WatchOS app, receiving a SDUI component tree from the backend, and verifying that glanceable components (metric cards, alerts) render correctly on the small screen.

**Acceptance Scenarios**:

1. **Given** the user opens the watch app, **When** the backend sends a SDUI component tree, **Then** only watch-compatible components (text, metric, alert, card) render on the small screen.
2. **Given** the backend sends a component type unsupported on watch (e.g., full table, chart), **When** the client receives it, **Then** it degrades gracefully by showing a summary or placeholder.
3. **Given** the user taps an alert card on the watch, **When** the action is sent to the backend, **Then** the backend acknowledges it and returns an updated view.

---

### Edge Cases

- What happens when the backend sends a component type the client doesn't recognize? The client MUST render a graceful placeholder and log a warning—never crash.
- How does the system handle very large component trees (100+ components in a single response)? The client renders progressively and maintains responsive scrolling.
- What happens when the network connection is lost mid-render? The client displays the last successfully rendered state with an offline indicator.
- How does the watch handle component trees intended for phone/tablet? The backend MUST send device-appropriate trees based on the client's declared device profile.
- What happens when the user rotates a phone/tablet mid-session? The client re-renders the current SDUI tree with updated layout constraints without re-fetching from the backend.
- What does the user see between login and the first backend-rendered UI? The client displays a loading overlay with a blurred background, a centered spinner, and rotating humorous loading messages (e.g., "Loading...", "Reticulating Splines..."). The orchestrator dispatches the initial UI upon seeing the client connection (potentially tailored to the user from previous interactions).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a Flutter-based client application that acts as a passive SDUI renderer, receiving component trees from the backend and rendering them without embedded business logic.
- **FR-002**: The Flutter client MUST support the following target platforms from a single codebase: iOS (iPhone, iPad), Android (phone, tablet), Apple Watch (watchOS), and TV (Android TV / tvOS).
- **FR-003**: The client MUST implement a renderer for every SDUI primitive defined in the backend's component library (text, button, card, container, grid, table, metric, chart types, list, code, alert, progress, divider, input, file upload/download, color picker, collapsible).
- **FR-004**: The client MUST degrade gracefully when encountering an unknown SDUI component type by rendering a visually distinct placeholder element and logging a diagnostic warning.
- **FR-005**: The client MUST establish and maintain a WebSocket connection to the backend for real-time SDUI streaming and chat interaction.
- **FR-006**: The client MUST authenticate users via Keycloak using the project's existing OIDC configuration, extracting roles from JWT tokens for role-based access. The client MUST silently refresh expired JWTs using the refresh token without user interruption; if the refresh token itself is expired, the client redirects to re-authentication.
- **FR-007**: The client MUST declare a device profile (screen category, input modality, supported component types) to the backend upon connection so the backend can compose device-appropriate SDUI trees.
- **FR-008**: The client MUST support adaptive layouts that respond to screen size, orientation changes, and platform-specific constraints without re-fetching the component tree from the backend.
- **FR-009**: The client MUST handle WebSocket disconnection by displaying an offline indicator, retaining the last rendered state, and automatically reconnecting when connectivity is restored. The last rendered SDUI component tree MUST be persisted to disk so that on app restart the client displays the cached UI while reconnecting, replacing it with the fresh backend state once received.
- **FR-010**: The Apple Watch client MUST support a subset of SDUI components suitable for glanceable interaction: text, metric, alert, card, and button. Unsupported components MUST be gracefully omitted or summarized.
- **FR-011**: The TV client MUST support D-pad/remote focus-based navigation with clear visual focus indicators on all interactive elements.
- **FR-012**: The client MUST support the component save/combine/condense workflows currently available, as driven by backend instructions.
- **FR-013**: The client MUST support pagination for large data sets (e.g., tables) as directed by the backend's pagination metadata.
- **FR-014**: The client MUST apply theming (colors, typography, spacing) dynamically from a theme configuration sent by the backend as part of the protocol. The client maintains a sensible default theme as a fallback until the backend theme is received. Visual consistency across platforms is maintained by the backend tailoring theme values per device profile.
- **FR-015**: The client MUST display a loading overlay between authentication and the first `ui_render` response, consisting of a blurred background, a centered spinner, and rotating humorous loading messages (e.g., "Loading...", "Reticulating Splines...").

### Key Entities

- **Device Profile**: Represents the client device's capabilities—screen category (phone, tablet, watch, TV), input modality (touch, D-pad, crown), and the set of SDUI components it can render. Sent to the backend on connection.
- **SDUI Component Tree**: A hierarchical JSON structure produced by the backend describing the UI to render. Contains component type, properties, children, and action bindings. The client never modifies this tree—only renders it.
- **Action Binding**: An interaction descriptor attached to interactive components (buttons, inputs). When triggered by user input, the client sends the action payload to the backend and awaits an updated component tree.
- **Session**: A persistent authenticated connection between a client and the backend, maintaining WebSocket state, user identity, and device profile.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can launch the app and reach an interactive dashboard within 5 seconds on phone, tablet, and TV; within 3 seconds on watch.
- **SC-002**: 100% of backend SDUI primitive component types render correctly on phone and tablet; at least the designated subset renders on watch and TV.
- **SC-003**: Real-time messages and SDUI updates appear on screen within 1 second of backend dispatch under normal network conditions.
- **SC-004**: The app maintains a usable experience across all five form factors (iPhone, iPad, Android phone/tablet, Apple Watch, TV) from a single codebase with no platform-specific forks.
- **SC-005**: When an unknown component type is received, the client renders a placeholder without crashing in 100% of cases.
- **SC-006**: After a network disconnection, the client automatically reconnects and resumes within 10 seconds of connectivity restoration.
- **SC-007**: TV navigation via D-pad/remote allows users to reach any interactive element within 5 directional presses from any screen.
- **SC-008**: The app passes accessibility audits on iOS and Android (VoiceOver, TalkBack) for all rendered SDUI components.

## Assumptions

- The backend's existing SDUI primitive library (defined in `primitives.py`) is the source of truth for component types. The Flutter client implements renderers for this existing set; new primitives follow the existing governance process.
- The backend will be extended to accept a device profile from the client and tailor SDUI component trees accordingly (e.g., sending simplified trees to watch, TV-optimized layouts to TV).
- Keycloak OIDC configuration remains unchanged; the Flutter client uses the same realm, client ID, and scopes as the current frontend.
- The Apple Watch app is a companion experience with limited interaction scope—no chat input, file upload, or complex workflows.
- The existing WebSocket protocol and message format remain stable; the Flutter client adopts the same protocol the React frontend currently uses.
- Chart rendering on TV and watch may use simplified visualizations (e.g., static images or summary metrics) where interactive charting is impractical.
- Minimum supported platform versions: iOS 17+, Android API 28+ (Android 9.0), watchOS 10+, tvOS 17+. Only the newest two major OS versions are targeted.

## Clarifications

### Session 2026-04-03

- Q: What should the app display while waiting for the initial SDUI component tree after authentication? → A: Blurred background + centered spinner + rotating humorous loading messages (e.g., "Loading...", "Reticulating Splines..."). The orchestrator dispatches the initial UI upon seeing the client connection, potentially tailored from previous interactions.
- Q: What should happen when the Keycloak JWT expires during an active session? → A: Silent refresh via refresh token with no user interruption.
- Q: Where does the app's visual theme originate? → A: Backend sends theme config (colors, typography) as part of the protocol; client applies dynamically.
- Q: Should the last rendered UI state persist across app restarts? → A: Yes, persist to disk. App restart shows cached UI while reconnecting, then replaces with fresh backend state once received.
- Q: What are the minimum supported platform versions? → A: Aggressive — iOS 17+ / Android API 28+ (Android 9.0) / watchOS 10+ / tvOS 17+.
