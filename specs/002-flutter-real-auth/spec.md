# Feature Specification: Flutter Real Authentication Implementation

**Feature Branch**: `002-flutter-real-auth`  
**Created**: 2026-02-27  
**Status**: Draft  
**Input**: User description: "Create a new spec for copying the frontend/ directory styles and functionality using real auth as it is defined in the current frontend/ directory over to the flutter/ directory. do not modify any other files other than in the flutter/ directory. make sure before you are finished you check to make sure the flutter frontend connects with the python backend currently running on port 8001."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Authenticate with Real OIDC/Keycloak (Priority: P1)

As a user, I want to authenticate using the same OIDC/Keycloak system as the React frontend, so I can access the multi-agent system with proper security and user management.

**Why this priority**: Authentication is the gateway to the application. Real authentication (not mock) is required for production use, proper user management, and security compliance.

**Independent Test**: Can be fully tested by launching the Flutter app, completing OIDC authentication flow, and verifying the user is authenticated and can access the dashboard.

**Acceptance Scenarios**:

1. **Given** the user is not authenticated, **When** they open the Flutter app, **Then** they see a login screen with OIDC/Keycloak login button
2. **Given** valid OIDC credentials, **When** the user authenticates successfully, **Then** they are redirected to the main dashboard with their user profile displayed
3. **Given** authentication fails (invalid credentials, network error), **When** the user tries to login, **Then** they see an appropriate error message
4. **Given** the user is authenticated, **When** they logout, **Then** they are returned to the login screen and their session is terminated

---

### User Story 2 - Use Chat Interface with Dynamically Rendered Components (Priority: P1)

As a user, I want to send messages to the orchestrator and receive responses with dynamically rendered UI components, matching the exact functionality and appearance of the React frontend.

**Why this priority**: Chat is the primary interaction mechanism. The core value proposition is conversing with AI agents to accomplish tasks, which requires proper UI component rendering.

**Independent Test**: Can be tested by sending a message and verifying the response contains properly rendered UI components (text, cards, tables, charts) that match the React frontend's appearance.

**Acceptance Scenarios**:

1. **Given** the user is authenticated, **When** they type a message and send it, **Then** the message appears in chat with proper styling and they see thinking/executing status indicators
2. **Given** the LLM responds with UI components, **When** the response arrives, **Then** the components are rendered according to the DynamicRenderer specification with identical visual design to React
3. **Given** a tool execution is in progress, **When** the user sends a message, **Then** they see appropriate status messages (thinking, executing, done) with matching styling
4. **Given** the WebSocket connection drops, **When** the user tries to send a message, **Then** they receive appropriate feedback about connection status with matching error styling

---

### User Story 3 - File Upload and Analysis (Priority: P2)

As a user, I want to upload CSV/text files and have them analyzed by agents, with the same drag-and-drop interface and preview capability as the React frontend.

**Why this priority**: File analysis is a key use case for data-oriented tasks. It extends the chat capability to handle real user data and must match the existing user experience.

**Independent Test**: Can be tested by uploading a CSV file and verifying the backend receives it, the agent responds with analysis, and the UI matches the React frontend's file upload interface.

**Acceptance Scenarios**:

1. **Given** the user is in chat, **When** they attach a CSV file via drag-and-drop or file picker, **Then** the file appears as an attachment with preview capability matching React styling
2. **Given** a file is attached, **When** they send the message, **Then** the file is uploaded to the backend and the agent receives the file path, with progress indicators matching React
3. **Given** a large file (>10KB), **When** it's uploaded, **Then** it's handled via the upload endpoint with proper chunking/streaming and progress feedback matching React
4. **Given** file upload fails, **When** the user tries to send, **Then** they receive an error message with actionable feedback styled identically to React

---

### User Story 4 - Saved Components Management (Priority: P2)

As a user, I want to save, view, combine, and condense UI components from chat responses, with the same drawer interface and functionality as the React frontend.

**Why this priority**: Component management enhances productivity by allowing users to save and reuse valuable outputs. The interface must match for consistent user experience.

**Independent Test**: Can be tested by saving a component from chat, viewing it in the drawer, and performing combine/condense operations with UI matching the React frontend.

**Acceptance Scenarios**:

1. **Given** a UI component is rendered in chat, **When** the user clicks "Add all to UI", **Then** savable components are extracted and saved with identical visual feedback to React
2. **Given** saved components exist, **When** the user opens the drawer, **Then** they see all saved components with titles and previews matching React's drawer design
3. **Given** two components are selected, **When** the user combines them, **Then** the LLM merges them and returns a unified component with progress indicators matching React
4. **Given** multiple components are selected, **When** the user condenses them, **Then** the LLM reduces them to fewer cohesive components with identical UI flow to React

---

### User Story 5 - Backend Connectivity Verification (Priority: P1)

As a developer, I want to verify that the Flutter frontend successfully connects to the Python backend on port 8001, so I can ensure full system integration before completion.

**Why this priority**: Backend connectivity is essential for all functionality. Without proper connection to the orchestrator, none of the chat, file upload, or component features will work.

**Independent Test**: Can be tested by running the Flutter app against the live backend and verifying WebSocket connection, API endpoints, and authentication flow all function correctly.

**Acceptance Scenarios**:

1. **Given** the Python backend is running on port 8001, **When** the Flutter app starts, **Then** it establishes WebSocket connection and shows "Connected" status
2. **Given** the backend is unavailable, **When** the Flutter app starts, **Then** it shows appropriate connection error with retry mechanism
3. **Given** authenticated user, **When** they perform any backend operation (chat, file upload), **Then** the operation succeeds with proper data exchange
4. **Given** backend API changes, **When** the Flutter app attempts to connect, **Then** it gracefully handles version mismatches with informative errors

---

### Edge Cases

- What happens when OIDC/Keycloak server is unavailable during authentication?
- How does the system handle malformed UI component JSON from the backend in Flutter vs React?
- What happens when authentication token expires during a long-running chat session?
- How does the app handle offline mode or poor network connectivity for cached components?
- What happens when a user tries to upload an unsupported file type?
- How does the system handle concurrent file uploads and chat messages with the same performance as React?
- What happens when screen sizes differ between mobile (Flutter) and web (React) - how should responsive design adapt?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST authenticate users via OIDC/Keycloak (real auth, not mock) with identical flow and UI to React frontend
- **FR-002**: System MUST establish and maintain WebSocket connection to orchestrator backend on port 8001 with identical reconnection logic to React
- **FR-003**: System MUST display real-time connection status and agent information with matching visual design to React dashboard
- **FR-004**: System MUST send and receive chat messages with the orchestrator using identical message formats and UI styling to React
- **FR-005**: System MUST render UI components dynamically based on backend specifications with pixel-perfect matching to React (text, card, table, metric, alert, progress, grid, list, code, bar_chart, line_chart, pie_chart, plotly_chart, divider, button, collapsible, file_upload, file_download)
- **FR-006**: System MUST support file upload (CSV, text, JSON, MD) with drag-and-drop and preview matching React's implementation
- **FR-007**: System MUST support file download from backend with authentication matching React's implementation
- **FR-008**: System MUST save UI components from chat responses to persistent storage with identical data model and UI to React
- **FR-009**: System MUST display saved components in a drawer with management operations (delete, combine, condense) matching React's drawer design
- **FR-010**: System MUST maintain chat history with automatic title generation matching React's implementation
- **FR-011**: System MUST support role-based access (admin/user) with appropriate UI restrictions matching React
- **FR-012**: System MUST handle authentication token refresh and reconnection automatically with identical logic to React
- **FR-013**: System MUST provide visual feedback for all user actions (loading states, success/error messages) with identical styling to React
- **FR-014**: System MUST replicate the exact visual design, layout, spacing, typography, colors, and animations of the React frontend
- **FR-015**: System MUST use the same backend API endpoints, WebSocket protocols, and data structures as the React frontend
- **FR-016**: System MUST only modify files within the flutter/ directory; no changes to frontend/, backend/, or other project directories
- **FR-017**: System MUST successfully connect to and communicate with the Python backend running on port 8001 before feature completion

### Key Entities

- **User**: Represents an authenticated user via OIDC/Keycloak. Contains id, roles, authentication token, profile information.
- **ChatSession**: Represents a conversation with the orchestrator. Contains messages, saved components, metadata (id, title, updated_at).
- **SavedComponent**: Represents a UI component saved from chat. Contains component data, type, title, creation timestamp.
- **UIComponent**: Represents a renderable UI primitive from the backend specification. Has type and properties specific to each component type, must render identically to React.
- **BackendConnection**: Represents the connection to the Python orchestrator. Contains WebSocket state, API endpoint configuration, authentication status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can authenticate via OIDC/Keycloak and reach the dashboard within 10 seconds of app launch (matching React performance)
- **SC-002**: Chat messages are delivered and responses rendered within 3 seconds under normal network conditions (matching React performance)
- **SC-003**: File uploads under 10MB complete within 30 seconds with progress feedback (matching React performance)
- **SC-004**: UI components render identically to React version (pixel-perfect comparison with <5% visual variance)
- **SC-005**: All user actions available in React frontend are available in Flutter frontend (100% feature parity verified by test suite)
- **SC-006**: App maintains WebSocket connection with automatic reconnection within 5 seconds of network recovery (matching React behavior)
- **SC-007**: Saved components persist across app restarts and device changes (with same user account, matching React functionality)
- **SC-008**: Users can complete primary tasks (auth, chat, file upload, component save) without encountering blocking bugs (95% success rate in user testing)
- **SC-009**: App performance matches or exceeds React version on target platforms (60fps animations, smooth scrolling, matching React experience)
- **SC-010**: Backend connectivity verified - Flutter app successfully connects to Python backend on port 8001 and performs all operations
- **SC-011**: Code changes limited to flutter/ directory only - no modifications to frontend/, backend/, or other project directories
- **SC-012**: Real authentication (OIDC/Keycloak) fully implemented with mock auth disabled or configurable via environment variable

## Assumptions

1. The existing backend API (orchestrator on port 8001) will remain unchanged and compatible
2. WebSocket protocol and message formats will remain identical between React and Flutter implementations
3. OIDC/Keycloak configuration (issuer, client ID, scopes) will remain compatible
4. UI component JSON schema from backend will remain stable and identical for both frontends
5. File upload/download endpoints will remain unchanged
6. The React frontend serves as the reference implementation for all UI/UX decisions and visual design
7. Flutter app will target mobile platforms (iOS/Android) primarily, but should maintain visual parity with web-based React frontend
8. Existing React frontend code can be analyzed to extract styling values (colors, spacing, typography, animations)

## Dependencies

1. Backend orchestrator must be running and accessible on port 8001
2. Keycloak authentication server (or equivalent OIDC provider) must be configured and running
3. Existing React frontend codebase for reference implementation and styling extraction
4. Flutter development environment with necessary dependencies for OIDC authentication

## Open Questions / Resolved

1. **OIDC library choice**: Any OIDC library that works with Keycloak (compatible with backend authentication configuration). The implementation should check the backend configuration for Keycloak integration details.
2. **Responsive design approach**: The responsive design should incorporate dynamically generated UI components just like in the frontend/ directory, maintaining the same component rendering behavior across different screen sizes.
3. **Platform-specific features**: Focus on Chrome compatibility for initial implementation. Native device features can be added later if needed, but are not required for the initial parity implementation.
