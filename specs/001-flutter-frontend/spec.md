# Feature Specification: Flutter Frontend 1:1 Replacement

**Feature Branch**: `1-flutter-frontend`  
**Created**: 2026-02-27  
**Status**: Draft  
**Input**: User description: "I need to build a Flutter application that serves as a 1:1 functional replacement for the existing React frontend located in the `frontend/` directory.

The specification must be derived directly from the current `frontend/` codebase. The new application must:
1. **Replicate User Flows:** Support every user action (login, navigation, form submissions, data viewing) exactly as they exist in the React app.
2. **Integrate with Existing Backend:** Consume the API provided by the `backend/` directory using the exact same endpoints and data structures.
3. **Match UI/UX:** Replicate the visual hierarchy, feedback mechanisms (loading states, success/error messages), and layout logic of the current frontend.

The "Spec" is effectively: "Whatever the current React app does, the Flutter app must also do.""

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Authentication and Initial Dashboard (Priority: P1)

As a user, I want to authenticate via OIDC/Keycloak (or mock auth) and see the main dashboard with connection status, so I can start interacting with the multi-agent system.

**Why this priority**: Authentication is the gateway to the application. Without it, no other features are accessible. The dashboard provides system status which is critical for user confidence.

**Independent Test**: Can be fully tested by launching the app, completing authentication, and verifying the dashboard displays connection status, agent count, and tool count.

**Acceptance Scenarios**:

1. **Given** the user is not authenticated, **When** they open the app, **Then** they see a login screen with SSO button
2. **Given** valid credentials, **When** the user authenticates successfully, **Then** they see the main dashboard with sidebar and header
3. **Given** the orchestrator is connected, **When** the dashboard loads, **Then** it shows "Connected" status and lists connected agents
4. **Given** mock auth is enabled, **When** the user opens the app, **Then** they are automatically logged in as a dev user

---

### User Story 2 - Real-time Chat with LLM Agents (Priority: P1)

As a user, I want to send messages to the orchestrator and receive responses with dynamically rendered UI components, so I can interact with AI agents and get actionable insights.

**Why this priority**: Chat is the primary interaction mechanism. The core value proposition is conversing with AI agents to accomplish tasks.

**Independent Test**: Can be tested by sending a message and verifying the response contains properly rendered UI components (text, cards, tables, charts).

**Acceptance Scenarios**:

1. **Given** the user is authenticated and connected, **When** they type a message and send it, **Then** the message appears in chat and they see thinking/executing status
2. **Given** the LLM responds with UI components, **When** the response arrives, **Then** the components are rendered according to the DynamicRenderer specification
3. **Given** a tool execution is in progress, **When** the user sends a message, **Then** they see appropriate status messages (thinking, executing, done)
4. **Given** the WebSocket connection drops, **When** the user tries to send a message, **Then** they receive appropriate feedback about connection status

---

### User Story 3 - File Upload and Analysis (Priority: P2)

As a user, I want to upload CSV/text files and have them analyzed by agents, so I can get insights from my data without manual processing.

**Why this priority**: File analysis is a key use case for data-oriented tasks. It extends the chat capability to handle real user data.

**Independent Test**: Can be tested by uploading a CSV file and verifying the backend receives it and the agent responds with analysis.

**Acceptance Scenarios**:

1. **Given** the user is in chat, **When** they attach a CSV file, **Then** the file appears as an attachment with preview capability
2. **Given** a file is attached, **When** they send the message, **Then** the file is uploaded to the backend and the agent receives the file path
3. **Given** a large file (>10KB), **When** it's uploaded, **Then** it's handled via the upload endpoint with proper chunking/streaming
4. **Given** file upload fails, **When** the user tries to send, **Then** they receive an error message with actionable feedback

---

### User Story 4 - Saved Components Management (Priority: P2)

As a user, I want to save, view, combine, and condense UI components from chat responses, so I can build a library of reusable insights and dashboards.

**Why this priority**: Component management enhances productivity by allowing users to save and reuse valuable outputs.

**Independent Test**: Can be tested by saving a component from chat, viewing it in the drawer, and performing combine/condense operations.

**Acceptance Scenarios**:

1. **Given** a UI component is rendered in chat, **When** the user clicks "Add all to UI", **Then** savable components are extracted and saved
2. **Given** saved components exist, **When** the user opens the drawer, **Then** they see all saved components with titles and previews
3. **Given** two components are selected, **When** the user combines them, **Then** the LLM merges them and returns a unified component
4. **Given** multiple components are selected, **When** the user condenses them, **Then** the LLM reduces them to fewer cohesive components

---

### User Story 5 - Chat History and Navigation (Priority: P2)

As a user, I want to view my chat history, load previous conversations, and start new chats, so I can maintain context across sessions.

**Why this priority**: History persistence is essential for practical usage, allowing users to resume work.

**Independent Test**: Can be tested by creating multiple chats, switching between them, and verifying messages persist.

**Acceptance Scenarios**:

1. **Given** the user has previous chats, **When** they open the sidebar, **Then** they see recent chats with titles and dates
2. **Given** a chat is selected from history, **When** they click it, **Then** the chat loads with all previous messages and components
3. **Given** the user wants a fresh start, **When** they click "New Chat", **Then** a new chat session is created with empty message history
4. **Given** a chat has saved components, **When** it's loaded, **Then** the saved components drawer shows those components

---

### Edge Cases

- What happens when the WebSocket connection is lost during file upload?
- How does the system handle malformed UI component JSON from the backend?
- What happens when authentication token expires during a long-running chat session?
- How does the app handle offline mode or poor network connectivity?
- What happens when a user tries to upload an unsupported file type?
- How does the system handle concurrent file uploads and chat messages?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST authenticate users via OIDC/Keycloak with mock auth fallback
- **FR-002**: System MUST establish and maintain WebSocket connection to orchestrator backend
- **FR-003**: System MUST display real-time connection status and agent information
- **FR-004**: System MUST send and receive chat messages with the orchestrator
- **FR-005**: System MUST render UI components dynamically based on backend specifications (text, card, table, metric, alert, progress, grid, list, code, bar_chart, line_chart, pie_chart, plotly_chart, divider, button, collapsible, file_upload, file_download)
- **FR-006**: System MUST support file upload (CSV, text, JSON, MD) with drag-and-drop and preview
- **FR-007**: System MUST support file download from backend with authentication
- **FR-008**: System MUST save UI components from chat responses to persistent storage
- **FR-009**: System MUST display saved components in a drawer with management operations (delete, combine, condense)
- **FR-010**: System MUST maintain chat history with automatic title generation
- **FR-011**: System MUST support role-based access (admin/user) with appropriate UI restrictions
- **FR-012**: System MUST handle authentication token refresh and reconnection automatically
- **FR-013**: System MUST provide visual feedback for all user actions (loading states, success/error messages)
- **FR-014**: System MUST replicate the exact visual design and layout of the React frontend
- **FR-015**: System MUST use the same backend API endpoints and data structures as the React frontend

### Key Entities

- **ChatSession**: Represents a conversation with the orchestrator. Contains messages, saved components, metadata (id, title, updated_at).
- **SavedComponent**: Represents a UI component saved from chat. Contains component data, type, title, creation timestamp.
- **Agent**: Represents a connected specialist agent. Contains id, name, tools, status.
- **UIComponent**: Represents a renderable UI primitive from the backend specification. Has type and properties specific to each component type.
- **User**: Represents an authenticated user. Contains id, roles, authentication token.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can authenticate and reach the dashboard within 10 seconds of app launch
- **SC-002**: Chat messages are delivered and responses rendered within 3 seconds under normal network conditions
- **SC-003**: File uploads under 10MB complete within 30 seconds with progress feedback
- **SC-004**: UI components render identically to React version (pixel-perfect comparison)
- **SC-005**: All user actions available in React frontend are available in Flutter frontend (100% feature parity)
- **SC-006**: App maintains WebSocket connection with automatic reconnection within 5 seconds of network recovery
- **SC-007**: Saved components persist across app restarts and device changes (with same user account)
- **SC-008**: Users can complete primary tasks (auth, chat, file upload, component save) without encountering blocking bugs
- **SC-009**: App performance matches or exceeds React version on target platforms (60fps animations, smooth scrolling)
- **SC-010**: Backward compatibility maintained - Flutter app works with existing backend without modifications

## Assumptions

1. The existing backend API (orchestrator on port 8001) will remain unchanged
2. WebSocket protocol and message formats will remain identical
3. OIDC/Keycloak configuration will remain compatible
4. UI component JSON schema from backend will remain stable
5. File upload/download endpoints will remain unchanged
6. The Flutter app will target mobile platforms (iOS/Android) primarily, with potential for web/desktop
7. Existing React frontend will serve as the reference implementation for all UI/UX decisions

## Dependencies

1. Backend orchestrator must be running and accessible
2. Keycloak authentication server (or mock auth configuration)
3. LLM service configured in backend for agent responses
4. Specialist agents (weather, medical, general) connected to orchestrator

## Open Questions / NEEDS CLARIFICATION

1. **Target platforms**: Should the Flutter app support web/desktop in addition to mobile, or is mobile-only sufficient?
2. **Offline capabilities**: Should the app have any offline functionality (cached chats, draft messages)?
3. **Push notifications**: Should the app support push notifications for chat messages when in background?
4. **Native device features**: Should the app leverage native device features (camera, GPS, contacts) that the React web app doesn't have?