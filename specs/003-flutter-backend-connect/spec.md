# Feature Specification: Flutter-Backend SDUI Integration

**Feature Branch**: `003-flutter-backend-connect`  
**Created**: 2026-04-05  
**Status**: Draft  
**Input**: User description: "Connect Flutter frontend to AstralBody backend — wire SDUI rendering, chat flow, UI drawer with auto-condense, and visual polish of primitives"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Send Chat and See SDUI Response (Priority: P1)

As a user, I type a message in the chat input bar and press send. The message reaches the AstralBody backend via WebSocket, the backend processes it through the orchestrator and agents, and the resulting SDUI components render visibly in the main content area. I see status indicators ("thinking", "executing") while the backend works, and the final response appears as styled, interactive UI components.

**Why this priority**: This is the foundational interaction — without chat producing visible results, no other feature matters. It validates the entire end-to-end pipeline.

**Independent Test**: Send a chat message with the AstralBody backend running. Verify that status updates appear during processing and SDUI components (cards, tables, text, metrics, etc.) render in the main workspace area.

**Acceptance Scenarios**:

1. **Given** the Flutter app is connected to AstralBody via WebSocket, **When** I type "hello" and press send, **Then** I see a status indicator (e.g., "thinking...") followed by SDUI components rendering in the main content area.
2. **Given** the backend returns a complex response with multiple component types (card, table, chart, metric), **When** the `ui_render` message arrives, **Then** all components render correctly with proper layout and hierarchy.
3. **Given** the backend is processing a multi-turn request, **When** intermediate status updates arrive, **Then** I see real-time status text (thinking, executing tool names, done).
4. **Given** streaming content arrives, **When** data is appended to an existing component, **Then** the UI updates incrementally without replacing the entire view.

---

### User Story 2 - Add Components to UI Drawer (Priority: P2)

As a user viewing SDUI components rendered from a chat response in the main content area, I can select individual components and add them to a persistent UI drawer (component library). The drawer is accessible from the main interface and shows all my saved components as visual cards. This lets me curate the pieces of dynamic UI I want to keep and build into a cohesive interface.

**Why this priority**: This is the core "build a dynamic interface" workflow. Users need to pick and choose which SDUI outputs to persist beyond a single chat response.

**Independent Test**: After receiving SDUI components from a chat response, select one or more components, add them to the drawer, open the drawer, and verify the saved components appear as cards.

**Acceptance Scenarios**:

1. **Given** SDUI components are rendered in the main content area from a chat response, **When** I view any component, **Then** I see a persistent "+" icon in the top-right corner of the component that triggers "Add to UI" on tap.
2. **Given** I press "Add to UI" on a component, **When** the save completes, **Then** the component appears in the UI drawer and I receive visual confirmation (e.g., brief toast or animation).
3. **Given** I have saved multiple components to the drawer, **When** I open the UI drawer, **Then** I see all saved components displayed as visual preview cards in a scrollable grid.
4. **Given** I want to remove a saved component, **When** I press the delete button on a component card in the drawer, **Then** the component is removed from the drawer.

---

### User Story 3 - Auto-Condense Components (Priority: P3)

As a user with multiple saved components in the UI drawer, I can press an "Auto Condense" button that intelligently merges compatible components together. The backend analyzes the saved components and combines those that logically belong together (e.g., related metrics into a dashboard card, related data into a unified table), reducing clutter and creating a more cohesive interface.

**Why this priority**: This transforms a collection of individual components into a purposeful, unified interface — the key differentiator of the dynamic UI building experience.

**Independent Test**: Save 2+ components to the drawer, press "Auto Condense", and verify that compatible components merge into fewer, combined components while incompatible ones remain separate.

**Acceptance Scenarios**:

1. **Given** I have 2 or more components saved in the UI drawer, **When** I press the "Auto Condense" button, **Then** the system sends a condense request to the backend and shows a loading/progress indicator.
2. **Given** the backend returns condensed results, **When** the drawer updates, **Then** compatible components are merged into fewer combined components and I can see the new, combined layouts.
3. **Given** some components cannot be logically combined, **When** auto-condense runs, **Then** those components remain as-is rather than being forced into an unsuitable merge.
4. **Given** I condense components, **When** I inspect a condensed component, **Then** I can see the full content in an expanded/detail view.

---

### User Story 4 - Visually Polished SDUI Primitives (Priority: P4)

As a user viewing SDUI components in the Flutter app, the components look modern, polished, and visually appealing. Cards have appropriate depth and shadows, text has clear hierarchy, charts and tables are well-styled, metrics have visual weight, and interactive elements have clear affordances. The dark theme feels premium and cohesive.

**Why this priority**: Visual polish directly impacts user trust and engagement. The components must look professional for the product to feel credible, but it doesn't block functional workflows.

**Independent Test**: Render each major SDUI primitive type (card, table, metric, chart, button, alert, input, code block) and verify each looks polished with proper spacing, shadows, typography, and color usage within the dark theme.

**Acceptance Scenarios**:

1. **Given** a card component renders, **When** I view it, **Then** it has visible depth (shadow or border glow), consistent padding, clear title typography, and smooth rounded corners.
2. **Given** a metric component renders, **When** I view it, **Then** the value is prominently displayed with appropriate font size/weight, optional progress indicator is styled with theme accent colors, and the layout feels balanced.
3. **Given** a table component renders, **When** I view it, **Then** header rows are visually distinct, rows have alternating backgrounds or subtle separators, and the table is horizontally scrollable on narrow screens.
4. **Given** a chart component renders (bar, line, pie), **When** I view it, **Then** it uses theme-consistent colors, has readable labels, and has appropriate sizing with padding.
5. **Given** interactive elements (buttons, inputs) render, **When** I view them, **Then** buttons have clear press states, inputs have visible focus states, and both use consistent styling from the theme.

---

### User Story 5 - UI Drawer Access and Management (Priority: P5)

As a user, I can open and close the UI drawer from the main interface using a clearly visible button. The drawer provides an organized view of my saved components with the ability to delete individual items, drag to reorder, and see component previews. The drawer persists across app sessions.

**Why this priority**: The drawer is the management hub for the dynamic UI building workflow, but basic add/view/condense functionality (P2, P3) takes priority over advanced management features.

**Independent Test**: Open the drawer, verify saved components display, delete one, close and reopen the drawer to confirm persistence.

**Acceptance Scenarios**:

1. **Given** I am on the main screen and have saved components in the active chat, **When** I see the left-arrow indicator on the right screen edge and tap it, **Then** the UI drawer opens as a full-screen view showing my saved components.
2. **Given** the drawer is open with components, **When** I press the X/delete button on a component card, **Then** it is removed with a brief animation.
3. **Given** I have saved components and close the app, **When** I reopen the app, **Then** my saved components are still present in the drawer.
4. **Given** the active chat has no saved components, **When** I look at the right screen edge, **Then** no drawer indicator is visible (the drawer is completely hidden).

---

### Edge Cases

- What happens when the WebSocket disconnects mid-chat? The app should show an offline indicator and auto-reconnect, then resume or notify the user.
- What happens when the backend returns an unknown component type? The app should gracefully skip or show a placeholder rather than crashing.
- What happens when auto-condense fails (backend error)? The user sees an error message and their original components remain untouched.
- What happens when the user tries to add a duplicate component to the drawer? The system allows it (components may have different context even if structurally similar).
- What happens on very slow connections? Status indicators should remain visible, and timeouts should produce user-friendly messages.

## Clarifications

### Session 2026-04-05

- Q: Are saved components per-chat or a global user library? → A: Per-chat. The UI drawer shows only the active chat session's saved components.
- Q: How does the user trigger "Add to UI" on a rendered SDUI component? → A: Each component always shows a persistent "+" icon in its top-right corner.
- Q: Where does the UI drawer appear in the layout? → A: Right-edge panel, hidden until components are saved. Once components exist, a left-arrow indicator appears on the right screen edge. Tapping it expands the drawer to full-screen. Drawer stays full-screen until explicitly dismissed.
- Q: What is the minimum number of saved components to enable Auto Condense? → A: 2 (matches backend default).
- Q: Does the Flutter frontend build a conversation thread or does the backend own all display? → A: Backend owns all display. The frontend is a pure SDUI renderer — no local message echo. The backend provides text and UI components pre-formatted for rendering.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST deliver chat messages from the Flutter input bar to the AstralBody backend via the existing WebSocket connection and render the resulting SDUI components in the main content area.
- **FR-002**: System MUST display real-time status updates (thinking, executing, done) received from the backend during chat processing.
- **FR-003**: System MUST handle all server-to-client message types: full component tree replacement, partial component updates, streaming content appends, and backend action commands. The frontend is a pure SDUI renderer — the backend owns all display including user message representation. No local message echo.
- **FR-004**: System MUST provide an "Add to UI" action on SDUI components rendered from chat responses, allowing users to save individual components to the UI drawer.
- **FR-005**: System MUST persist saved components to the backend scoped to the active chat session (per-chat) and reflect confirmation of saves.
- **FR-006**: System MUST show a left-arrow indicator on the right screen edge when the active chat has saved components. Tapping the indicator MUST open the UI drawer as a full-screen view showing all saved components as preview cards. The drawer remains hidden when no components are saved.
- **FR-007**: System MUST provide an "Auto Condense" button in the UI drawer that merges compatible saved components and updates the drawer with merged results.
- **FR-008**: System MUST allow deletion of individual saved components from the UI drawer.
- **FR-009**: All SDUI primitive components (card, table, metric, chart, button, input, alert, code, text, grid, tabs, collapsible, progress, list, divider, image) MUST render with polished, theme-consistent styling including appropriate spacing, shadows, typography, and color.
- **FR-010**: Interactive SDUI components (buttons, inputs, file upload) MUST dispatch actions to the backend with the correct action name and payload when the user interacts with them.
- **FR-011**: System MUST handle connection loss gracefully — showing an offline indicator, auto-reconnecting, and restoring the session.
- **FR-012**: System MUST cache the SDUI component tree and saved components locally so the app displays the last-known state on restart before reconnection completes.

### Key Entities

- **SDUI Component**: A unit of server-driven UI described by a type, optional ID, style, and type-specific properties (e.g., label, children, data). Rendered dynamically by the Flutter frontend.
- **Saved Component**: A user-curated SDUI component persisted in the UI drawer, scoped to a specific chat session. Has an ID, the owning chat_id, and the original component data. Switching chats changes which saved components are visible in the drawer.
- **Chat Session**: A conversation thread between the user and the backend orchestrator. Contains a sequence of messages and associated SDUI responses.
- **Device Profile**: The capabilities and constraints of the connecting device, sent during registration and used by the backend to adapt component output for the device.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can send a chat message and see the full SDUI response rendered within 2 seconds of the backend completing processing (excluding backend processing time).
- **SC-002**: All 16+ core SDUI primitive types render correctly and attractively — no broken layouts, missing content, or unstyled fallbacks.
- **SC-003**: Users can add a component to the UI drawer in 2 or fewer taps/clicks from viewing it in a chat response.
- **SC-004**: Auto-condense reduces a set of 5+ compatible components into fewer combined components in a single action, with the user able to see the result within 3 seconds of the backend responding.
- **SC-005**: The app recovers from a WebSocket disconnection and restores the session without user intervention within 30 seconds.
- **SC-006**: Saved components persist across app restarts — reopening the app shows previously saved components before the backend reconnects.
- **SC-007**: 90% of SDUI component types pass a visual quality review (proper spacing, shadows, typography, color consistency with the dark theme) without requiring further iteration.

## Assumptions

- The AstralBody backend is running and accessible at a configurable WebSocket endpoint during development and testing.
- The existing WebSocket provider in the Flutter app correctly establishes connections and handles the initial handshake — the primary gap is in rendering responses and wiring user actions.
- The backend's component condensing capability is functional and returns meaningful merged results when given compatible components.
- The dark navy + indigo theme is the desired design direction — visual polish means refining within this palette, not redesigning the color scheme.
- The SavedComponentsDrawer widget already implemented in the Flutter codebase is the intended foundation for the UI drawer — it needs integration and potentially UI refinements, not a rewrite.
