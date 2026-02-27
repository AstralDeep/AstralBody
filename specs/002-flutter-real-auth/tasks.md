---

description: "Task list for Flutter Real Authentication Implementation"
---

# Tasks: Flutter Real Authentication Implementation

**Input**: Design documents from `/specs/002-flutter-real-auth/`
**Prerequisites**: plan.md (available), spec.md (required), research.md (available), data-model.md (available), contracts/ (available)

**Tests**: Tests are OPTIONAL - not requested in spec.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Flutter project**: `flutter/` at repository root
- **Source code**: `flutter/lib/`
- **Configuration**: `flutter/lib/core/config/`
- **Presentation**: `flutter/lib/presentation/`
- **Data layer**: `flutter/lib/data/`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Verify flutter project structure and dependencies in flutter/pubspec.yaml
- [x] T002 [P] Configure OIDC/Keycloak client configuration in flutter/lib/core/config/app_config.dart
- [x] T003 [P] Add OIDC library dependency to flutter/pubspec.yaml (flutter_appauth, oauth2, shared_preferences)
- [x] T004 [P] Update analysis_options.yaml for linting consistency with frontend/
- [x] T005 [P] Add WebSocket library dependency (web_socket_channel) to flutter/pubspec.yaml
- [x] T006 [P] Add file upload library dependency (file_picker, dio) to flutter/pubspec.yaml
- [x] T007 [P] Add chart rendering libraries (fl_chart, webview_flutter) to flutter/pubspec.yaml
- [x] T008 [P] Add local storage library (hive) to flutter/pubspec.yaml

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T009 Implement real OIDC authentication datasource in flutter/lib/data/datasources/oidc_auth_datasource.dart
- [x] T010 [P] Update auth_provider to use real OIDC datasource (remove mock) in flutter/lib/presentation/providers/auth_provider.dart
- [x] T011 [P] Implement token refresh logic for OIDC in flutter/lib/data/datasources/oidc_auth_datasource.dart
- [ ] T012 [P] Update WebSocket service to use real authentication tokens in flutter/lib/data/datasources/websocket_service.dart
- [ ] T013 Create UI component rendering foundation matching React frontend styles in flutter/lib/presentation/widgets/dynamic_renderer.dart
- [ ] T014 [P] Implement file upload service using backend API in flutter/lib/data/datasources/file_upload_service.dart
- [ ] T015 [P] Implement saved components storage service in flutter/lib/data/datasources/saved_components_service.dart
- [ ] T016 [P] Update app theme to match React frontend colors, typography, spacing in flutter/lib/core/theme/app_theme.dart
- [ ] T017 [P] Create data models from data-model.md in flutter/lib/data/models/
- [ ] T018 [P] Implement REST API client based on contracts/rest-api.md in flutter/lib/data/datasources/rest_api_client.dart

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Authenticate with Real OIDC/Keycloak (Priority: P1) 🎯 MVP

**Goal**: Users can authenticate using the same OIDC/Keycloak system as the React frontend, with proper security and user management.

**Independent Test**: Launch the Flutter app, complete OIDC authentication flow, verify user is authenticated and can access the dashboard.

### Implementation for User Story 1

- [ ] T019 [P] [US1] Create OIDC login screen UI matching React frontend in flutter/lib/presentation/pages/login_screen.dart
- [ ] T020 [US1] Integrate OIDC login button with OIDC datasource in flutter/lib/presentation/pages/login_screen.dart
- [ ] T021 [US1] Handle authentication callback and token storage in flutter/lib/presentation/providers/auth_provider.dart
- [ ] T022 [US1] Implement logout functionality with OIDC session termination in flutter/lib/presentation/providers/auth_provider.dart
- [ ] T023 [US1] Update auth_guard to redirect unauthenticated users to OIDC login in flutter/lib/presentation/router/auth_guard.dart
- [ ] T024 [US1] Add error handling for OIDC authentication failures in flutter/lib/presentation/pages/login_screen.dart
- [ ] T025 [US1] Implement user profile display matching React dashboard in flutter/lib/presentation/pages/dashboard_screen.dart

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Use Chat Interface with Dynamically Rendered Components (Priority: P1)

**Goal**: Users can send messages to the orchestrator and receive responses with dynamically rendered UI components, matching the exact functionality and appearance of the React frontend.

**Independent Test**: Send a message and verify the response contains properly rendered UI components (text, cards, tables, charts) that match the React frontend's appearance.

### Implementation for User Story 2

- [ ] T026 [P] [US2] Enhance dynamic renderer to support all UI component types from contracts/ui-component-schema.md in flutter/lib/presentation/widgets/dynamic_renderer.dart
- [ ] T027 [US2] Update chat message UI to match React frontend styling in flutter/lib/presentation/widgets/chat_message_widget.dart
- [ ] T028 [US2] Implement thinking/executing status indicators matching React in flutter/lib/presentation/widgets/status_indicator.dart
- [ ] T029 [US2] Integrate WebSocket message sending with UI feedback in flutter/lib/presentation/providers/websocket_provider.dart
- [ ] T030 [US2] Render UI components from WebSocket responses in chat view in flutter/lib/presentation/pages/chat_screen.dart
- [ ] T031 [US2] Handle WebSocket connection drops with appropriate error styling in flutter/lib/presentation/providers/websocket_provider.dart
- [ ] T032 [US2] Implement WebSocket protocol per contracts/websocket-protocol.md in flutter/lib/data/datasources/websocket_service.dart
- [ ] T033 [US2] Create chat session management UI matching React in flutter/lib/presentation/pages/chat_screen.dart

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - File Upload and Analysis (Priority: P2)

**Goal**: Users can upload CSV/text files and have them analyzed by agents, with the same drag-and-drop interface and preview capability as the React frontend.

**Independent Test**: Upload a CSV file and verify the backend receives it, the agent responds with analysis, and the UI matches the React frontend's file upload interface.

### Implementation for User Story 3

- [ ] T034 [P] [US3] Create file upload UI with drag-and-drop matching React in flutter/lib/presentation/widgets/file_upload_widget.dart
- [ ] T035 [US3] Implement file picker integration for mobile platforms in flutter/lib/presentation/widgets/file_upload_widget.dart
- [ ] T036 [US3] Connect file upload widget to file upload service in flutter/lib/presentation/providers/file_upload_provider.dart
- [ ] T037 [US3] Display file preview capability matching React styling in flutter/lib/presentation/widgets/file_preview_widget.dart
- [ ] T038 [US3] Implement progress indicators for file upload matching React in flutter/lib/presentation/widgets/upload_progress_indicator.dart
- [ ] T039 [US3] Handle file upload errors with actionable feedback styled identically to React in flutter/lib/presentation/widgets/file_upload_widget.dart
- [ ] T040 [US3] Implement file type validation per backend contract in flutter/lib/data/datasources/file_upload_service.dart

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: User Story 4 - Saved Components Management (Priority: P2)

**Goal**: Users can save, view, combine, and condense UI components from chat responses, with the same drawer interface and functionality as the React frontend.

**Independent Test**: Save a component from chat, view it in the drawer, and perform combine/condense operations with UI matching the React frontend.

### Implementation for User Story 4

- [ ] T041 [P] [US4] Create saved components drawer UI matching React design in flutter/lib/presentation/widgets/saved_components_drawer.dart
- [ ] T042 [US4] Implement "Add all to UI" button extraction logic in flutter/lib/presentation/providers/websocket_provider.dart
- [ ] T043 [US4] Connect drawer to saved components service for CRUD operations in flutter/lib/presentation/providers/saved_components_provider.dart
- [ ] T044 [US4] Implement combine components UI flow matching React in flutter/lib/presentation/widgets/combine_components_dialog.dart
- [ ] T045 [US4] Implement condense components UI flow matching React in flutter/lib/presentation/widgets/condense_components_dialog.dart
- [ ] T046 [US4] Add visual feedback for component operations identical to React in flutter/lib/presentation/widgets/saved_components_drawer.dart
- [ ] T047 [US4] Implement component persistence using Hive per research.md in flutter/lib/data/datasources/saved_components_service.dart

---

## Phase 7: User Story 5 - Backend Connectivity Verification (Priority: P1)

**Goal**: Verify that the Flutter frontend successfully connects to the Python backend on port 8001, ensuring full system integration before completion.

**Independent Test**: Run the Flutter app against the live backend and verify WebSocket connection, API endpoints, and authentication flow all function correctly.

### Implementation for User Story 5

- [ ] T048 [P] [US5] Create connectivity test screen with connection status indicators in flutter/lib/presentation/pages/connectivity_test_screen.dart
- [ ] T049 [US5] Implement backend health check API call in flutter/lib/data/datasources/backend_health_service.dart
- [ ] T050 [US5] Verify WebSocket connection establishment and reconnection logic in flutter/lib/data/datasources/websocket_service.dart
- [ ] T051 [US5] Test authentication flow with real backend OIDC in flutter/lib/presentation/providers/auth_provider.dart
- [ ] T052 [US5] Validate all backend operations (chat, file upload) succeed with proper data exchange in flutter/lib/presentation/providers/websocket_provider.dart
- [ ] T053 [US5] Implement connection status monitoring and auto-reconnect per contracts/websocket-protocol.md in flutter/lib/presentation/providers/websocket_provider.dart

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T054 [P] Documentation updates in flutter/README.md
- [ ] T055 [P] Code cleanup and refactoring across flutter/lib/
- [ ] T056 [P] Performance optimization across all stories
- [ ] T057 [P] Security hardening (token storage, SSL pinning)
- [ ] T058 [P] Run quickstart.md validation
- [ ] T059 [P] Ensure pixel-perfect visual parity with React frontend via screenshot comparison
- [ ] T060 [P] Update analysis_options.yaml for linting consistency
- [ ] T061 [P] Add comprehensive error handling and logging across all services
- [ ] T062 [P] Implement responsive design for different screen sizes
- [ ] T063 [P] Add accessibility features (screen reader support, high contrast)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational (Phase 2) - May integrate with US1 but should be independently testable
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) - May integrate with US1/US2 but should be independently testable
- **User Story 4 (P2)**: Can start after Foundational (Phase 2) - Depends on US2 for components
- **User Story 5 (P1)**: Can start after Foundational (Phase 2) - Depends on US1 and US2 for backend operations

### Within Each User Story

- Models before services
- Services before UI
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- All tasks marked [P] within a user story can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch all parallel tasks for User Story 1 together:
Task: "Create OIDC login screen UI matching React frontend in flutter/lib/presentation/pages/login_screen.dart"
Task: "Integrate OIDC login button with OIDC datasource in flutter/lib/presentation/pages/login_screen.dart"
Task: "Handle authentication callback and token storage in flutter/lib/presentation/providers/auth_provider.dart"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 5 → Test independently → Deploy/Demo
5. Add User Story 3 → Test independently → Deploy/Demo
6. Add User Story 4 → Test independently → Deploy/Demo
7. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 5
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tasks follow the exact file paths specified
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
- All contracts (REST API, WebSocket protocol, UI component schema) must be strictly followed for compatibility
- Reference React frontend implementation for visual parity
- Test backend connectivity on port 8001 before finalizing

---

## Summary

**Total Tasks**: 63
**Tasks per Phase**:
- Setup: 8 tasks
- Foundational: 10 tasks  
- US1: 7 tasks
- US2: 8 tasks
- US3: 7 tasks
- US4: 7 tasks
- US5: 6 tasks
- Polish: 10 tasks

**Parallel Opportunities**: 42 tasks marked [P] (66% of total)

**MVP Scope**: User Story 1 (Authentication) + Foundational infrastructure

**Independent Test Criteria**: Each user story has clear test criteria for validation

**Format Validation**: All tasks follow checklist format with Task ID, [P] markers, [Story] labels, and file paths
