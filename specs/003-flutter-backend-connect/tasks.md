# Tasks: Flutter-Backend SDUI Integration

**Input**: Design documents from `/specs/003-flutter-backend-connect/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/websocket-protocol.md, quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

**Repos**:
- Backend: `y:\WORK\MCP\AstralBody\` (prefix: `backend/`)
- Flutter: `y:\WORK\MCP\astralprojection-flutter\` (prefix: `lib/`)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Network connectivity and configuration changes that enable all subsequent work

- [x] T001 Make Flutter backend host runtime-configurable with platform defaults (localhost for desktop, 10.0.2.2 for Android emulator, user-configurable for physical devices) in lib/config.dart
- [x] T002 [P] Change Docker port binding from `127.0.0.1:8001:8001` to `8001:8001` in backend/docker-compose.yml for LAN access
- [x] T003 [P] Add LAN IP patterns to CORS_ORIGINS env var in backend/docker-compose.yml or backend/orchestrator/orchestrator.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Protocol fixes and auth wiring that MUST be complete before ANY user story can work

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Fix chat_message payload key from `"text"` to `"message"` in lib/components/chat/chat_input_bar.dart (research.md mismatch #1 -- blocks all chat)
- [x] T005 [P] Fix combine_components payload from `{"component_ids": [...]}` to `{"source_id": "...", "target_id": "..."}` in lib/components/workspace/workspace_layout.dart (research.md mismatch #2)
- [x] T006 [P] Verify and fix save_component call sites to send `chat_id`, `component_data`, `component_type`, `title` per backend contract in lib/components/workspace/workspace_layout.dart (research.md mismatch #3)
- [x] T007 [P] Verify ROTE device type mapping handles `"desktop"` -> `BROWSER` in backend/rote/capabilities.py; add mapping if missing
- [x] T008 Wire mock auth token for dev mode -- ensure Flutter can complete the auth loop (register -> receive login UI -> login -> store token -> re-register) or pre-seed mock token in lib/state/token_storage_provider.dart

**Checkpoint**: Protocol aligned, auth working -- user story implementation can now begin

---

## Phase 3: User Story 1 - Send Chat and See SDUI Response (Priority: P1) MVP

**Goal**: User types a chat message, it reaches the backend via WebSocket, and the resulting SDUI components render visibly in the main content area with status indicators during processing.

**Independent Test**: Send a chat message with the AstralBody backend running. Verify that status updates appear during processing and SDUI components (cards, tables, text, metrics, etc.) render in the main workspace area.

### Implementation for User Story 1

- [x] T009 [US1] Verify chat_input_bar sends ui_event with action `chat_message` and payload `{"message": "...", "chat_id": "..."}` after T004 fix in lib/components/chat/chat_input_bar.dart
- [x] T010 [US1] Verify WebSocket provider correctly handles `chat_status` messages (thinking, executing, fixing, done) and exposes status state in lib/state/web_socket_provider.dart
- [x] T011 [US1] Verify chat status indicator displays real-time status text (thinking, executing tool names, done) in the UI -- wire status from provider to visible widget in lib/components/chat/ or lib/components/workspace/workspace_layout.dart
- [x] T012 [US1] Verify `ui_render` handler replaces the component tree correctly and triggers widget rebuild in lib/state/web_socket_provider.dart
- [x] T013 [US1] Verify `ui_append` handler finds target component by ID and appends streaming data correctly in lib/state/web_socket_provider.dart
- [x] T014 [US1] End-to-end validation: send "hello" via chat input, confirm status updates appear, confirm SDUI components render in workspace_layout.dart, confirm streaming text appends incrementally

**Checkpoint**: Chat -> SDUI rendering works end-to-end. This is the MVP.

---

## Phase 4: User Story 2 - Add Components to UI Drawer (Priority: P2)

**Goal**: Users can select individual SDUI components from chat responses and save them to a persistent UI drawer scoped to the active chat session.

**Independent Test**: After receiving SDUI components from a chat response, tap the "+" icon on a component, open the drawer, and verify the saved component appears as a card.

### Implementation for User Story 2

- [x] T015 [US2] Add persistent "+" icon overlay to every rendered SDUI component in the main content area that triggers `save_component` action in lib/components/dynamic_renderer.dart or lib/components/workspace/workspace_layout.dart
- [x] T016 [US2] Wire the "+" icon tap to send `ui_event` with action `save_component` and payload `{"chat_id": "<active>", "component_data": {...}, "component_type": "<type>", "title": "<extracted>"}` via WebSocket provider
- [x] T017 [US2] Verify `component_saved` server response is handled and updates the savedComponents list in lib/state/web_socket_provider.dart
- [x] T018 [US2] Add visual confirmation (toast or brief animation) when a component is successfully saved in lib/components/workspace/workspace_layout.dart
- [x] T019 [US2] Verify `get_saved_components` is called on chat switch/load and drawer shows only active chat's components in lib/components/workspace/saved_components_drawer.dart

**Checkpoint**: Users can save components from chat responses to the drawer.

---

## Phase 5: User Story 3 - Auto-Condense Components (Priority: P3)

**Goal**: Users press "Auto Condense" in the drawer to intelligently merge compatible saved components via the backend LLM.

**Independent Test**: Save 2+ components to the drawer, press "Auto Condense", and verify that compatible components merge into fewer combined components.

### Implementation for User Story 3

- [x] T020 [US3] Verify "Condense All" button in saved_components_drawer.dart sends `condense_components` action with `{"component_ids": [...]}` for all saved component IDs in lib/components/workspace/saved_components_drawer.dart
- [x] T021 [US3] Verify `components_condensed` server response handler removes old components and adds new condensed ones in lib/state/web_socket_provider.dart
- [x] T022 [US3] Show loading/progress indicator during condense operation (listen to `combine_status` messages) in lib/components/workspace/saved_components_drawer.dart
- [x] T023 [US3] Handle `combine_error` responses -- show user-friendly error message and leave original components untouched in lib/components/workspace/saved_components_drawer.dart
- [x] T024 [US3] Verify drag-and-drop combine in drawer sends corrected `combine_components` payload with `source_id`/`target_id` (depends on T005) in lib/components/workspace/saved_components_drawer.dart

**Checkpoint**: Auto-condense and manual combine both work via the drawer.

---

## Phase 6: User Story 4 - Visually Polished SDUI Primitives (Priority: P4)

**Goal**: All SDUI primitive components look modern, polished, and visually appealing within the dark navy + indigo theme.

**Independent Test**: Render each major SDUI primitive type and verify each looks polished with proper spacing, shadows, typography, and color usage.

### Implementation for User Story 4

- [x] T025 [P] [US4] Polish card components: depth/shadow or border glow, consistent padding, clear title typography, smooth rounded corners in lib/components/primitives/ (card-related widget files)
- [x] T026 [P] [US4] Polish metric components: prominent value font size/weight, theme accent progress bars, balanced layout in lib/components/primitives/ (metric-related widget files)
- [x] T027 [P] [US4] Polish table components: visually distinct headers, alternating row backgrounds or subtle separators, horizontal scroll on narrow screens in lib/components/primitives/ (table-related widget files)
- [x] T028 [P] [US4] Polish chart components (bar, line, pie): theme-consistent colors, readable labels, appropriate sizing with padding in lib/components/primitives/ (chart-related widget files)
- [x] T029 [P] [US4] Polish interactive elements: button press states, input focus states, consistent styling from theme in lib/components/primitives/ (button, input, checkbox widget files)
- [x] T030 [P] [US4] Polish content components: code blocks with syntax highlighting styling, alert variants (info/success/warning/error) with distinct colors, list styling in lib/components/primitives/ (code, alert, list widget files)
- [x] T031 [US4] Overall theme coherence pass: verify dark navy + indigo palette consistency across all 42 primitive widgets, fix any outliers in lib/components/primitives/

**Checkpoint**: All SDUI primitives look professional within the dark theme.

---

## Phase 7: User Story 5 - UI Drawer Access and Management (Priority: P5)

**Goal**: Users can open/close the UI drawer from the main interface, manage saved components (delete, reorder), and drawer state persists across app sessions.

**Independent Test**: Open the drawer, verify saved components display, delete one, close and reopen the app to confirm persistence.

### Implementation for User Story 5

- [x] T032 [US5] Implement right-edge left-arrow indicator that appears only when active chat has saved components (hidden otherwise) in lib/components/workspace/workspace_layout.dart
- [x] T033 [US5] Wire indicator tap to open saved_components_drawer as full-screen overlay; wire dismiss/close button in lib/components/workspace/saved_components_drawer.dart
- [x] T034 [US5] Verify per-component delete button sends `delete_saved_component` with correct `component_id` and updates drawer in lib/components/workspace/saved_components_drawer.dart
- [x] T035 [US5] Implement local persistence: serialize SDUI component tree to SharedPreferences on each `ui_render`/`ui_update` in lib/state/web_socket_provider.dart
- [x] T036 [US5] Implement local persistence: serialize saved components list to SharedPreferences on each update in lib/state/web_socket_provider.dart
- [x] T037 [US5] Load cached component tree and saved components on startup before WebSocket connects; display last-known state immediately in lib/state/web_socket_provider.dart
- [x] T038 [US5] Verify drawer correctly scopes to active chat -- switching chats updates drawer contents via `get_saved_components` in lib/state/web_socket_provider.dart and lib/components/workspace/saved_components_drawer.dart

**Checkpoint**: Drawer is fully accessible, manageable, and persists across sessions.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, error handling, and improvements that affect multiple user stories

- [x] T039 [P] Handle WebSocket disconnection gracefully: show offline indicator, auto-reconnect with exponential backoff (1s-30s), restore session in lib/state/web_socket_provider.dart and lib/components/common/
- [x] T040 [P] Handle unknown SDUI component types: render placeholder widget instead of crashing in lib/components/dynamic_renderer.dart
- [x] T041 [P] Handle slow connections: ensure status indicators remain visible during long processing, add user-friendly timeout messages in lib/components/workspace/workspace_layout.dart
- [x] T042 Run quickstart.md validation: follow all steps end-to-end on desktop and verify each checkpoint passes

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies -- can start immediately
- **Foundational (Phase 2)**: Can start in parallel with Setup; T004-T007 are independent. T008 may depend on T001 (config). BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Phase 2 completion (protocol fixes + auth)
- **User Story 2 (Phase 4)**: Depends on Phase 2 completion; benefits from US1 working to generate components
- **User Story 3 (Phase 5)**: Depends on Phase 2 (T005 combine fix); benefits from US2 for saved components
- **User Story 4 (Phase 6)**: Depends on Phase 2 completion; can run in parallel with US2/US3/US5
- **User Story 5 (Phase 7)**: Depends on Phase 2 completion; benefits from US2 for saved components
- **Polish (Phase 8)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: After Foundational -- no other story dependencies. **MVP target.**
- **US2 (P2)**: After Foundational -- functionally independent but benefits from US1 producing components to save
- **US3 (P3)**: After Foundational -- depends on T005 (combine fix). Benefits from US2 (save workflow)
- **US4 (P4)**: After Foundational -- fully independent, pure visual work
- **US5 (P5)**: After Foundational -- functionally independent but benefits from US2

### Within Each User Story

- Core wiring before UI integration
- Backend-facing changes before UI-facing changes
- End-to-end validation as final task per story

### Parallel Opportunities

- T002, T003 can run in parallel with T001 (different files)
- T004, T005, T006, T007 can all run in parallel (different files)
- US4 (visual polish) tasks T025-T030 are all parallelizable (different primitive files)
- US4 can run entirely in parallel with US2, US3, US5 (no shared files)
- T039, T040, T041 in Polish phase are all parallelizable

---

## Parallel Example: Phase 2 (Foundational)

```
# These can all run in parallel (different files):
T004: Fix chat_message payload in chat_input_bar.dart
T005: Fix combine_components payload in workspace_layout.dart
T006: Verify save_component payload in workspace_layout.dart  # May conflict with T005 (same file) - run after T005
T007: Verify ROTE desktop mapping in capabilities.py
```

## Parallel Example: User Story 4 (Visual Polish)

```
# All parallelizable (different primitive widget files):
T025: Polish cards
T026: Polish metrics
T027: Polish tables
T028: Polish charts
T029: Polish buttons/inputs
T030: Polish code/alerts/lists
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T008) -- CRITICAL, blocks everything
3. Complete Phase 3: User Story 1 (T009-T014)
4. **STOP and VALIDATE**: Send "hello" via chat, confirm full SDUI rendering pipeline works
5. This proves the end-to-end connection between Flutter and AstralBody backend

### Incremental Delivery

1. Setup + Foundational -> Protocol aligned, auth working
2. Add US1 -> Chat works -> **MVP!**
3. Add US2 -> Save components to drawer -> Demo save workflow
4. Add US3 -> Auto-condense -> Demo intelligent merging
5. Add US4 -> Visual polish -> Professional appearance
6. Add US5 -> Drawer management + persistence -> Complete experience
7. Polish -> Edge cases, offline support, hardening

### Notes

- Both repos need changes but Flutter-side is primary (~90% of tasks)
- Backend changes are minimal (Docker config, ROTE mapping verification)
- Protocol fixes are Flutter-only -- backend contract is authoritative
- Visual polish (US4) is the most parallelizable phase
