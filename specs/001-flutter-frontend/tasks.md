---

description: "Task list for Flutter Frontend 1:1 Replacement"
---

# Tasks: Flutter Frontend 1:1 Replacement

**Input**: Design documents from `/specs/001-flutter-frontend/`
**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Tests**: Tests are OPTIONAL - not explicitly requested in specification

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Flutter project**: `flutter/flutter_frontend/`
- **Clean architecture**: `lib/core/`, `lib/data/`, `lib/domain/`, `lib/presentation/`
- **Assets**: `assets/`
- **Tests**: `test/`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create Flutter project in `flutter/flutter_frontend/`
- [x] T002 [P] Configure `pubspec.yaml` with dependencies: riverpod, go_router, dio, web_socket_channel, flutter_secure_storage, flutter_dotenv, intl, url_launcher, file_picker, permission_handler, flutter_svg, cached_network_image
- [ ] T003 [P] Set up project structure (clean architecture) with directories: `lib/core/`, `lib/data/`, `lib/domain/`, `lib/presentation/`, `assets/`, `test/`
- [ ] T004 [P] Configure linting and formatting tools (analysis_options.yaml)
- [ ] T005 [P] Set up Git version control and .gitignore

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T006 [P] Extract color palette from Tailwind config (`frontend/tailwind.config.js`) and create Flutter `ThemeData` with Material 3 overrides in `lib/core/theme/app_theme.dart`
- [ ] T007 [P] Define custom text styles matching Inter font in `lib/core/theme/text_styles.dart`
- [ ] T008 [P] Create reusable theme extensions for custom colors in `lib/core/theme/color_extensions.dart`
- [ ] T009 [P] Copy images from `frontend/public/` to `assets/images/`: `AstralDeep.png`, `astra-fav.png`, `vite.svg`
- [ ] T010 [P] Set up font assets (Inter, JetBrains Mono) in `pubspec.yaml` and `assets/fonts/`
- [ ] T011 [P] Configure GoRouter with basic routes in `lib/presentation/router/app_router.dart`
- [ ] T012 [P] Create base error handling and logging infrastructure in `lib/core/errors/`
- [ ] T013 [P] Set up environment configuration management in `lib/core/config/`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Authentication and Initial Dashboard (Priority: P1) 🎯 MVP

**Goal**: Users can authenticate via OIDC/Keycloak (or mock auth) and see the main dashboard with connection status

**Independent Test**: Launch app, complete authentication, verify dashboard displays connection status, agent count, and tool count

### Implementation for User Story 1

- [ ] T014 [P] [US1] Create authentication provider with Riverpod in `lib/presentation/providers/auth_provider.dart`
- [ ] T015 [P] [US1] Implement OIDC/Keycloak client in `lib/data/datasources/auth_datasource.dart`
- [ ] T016 [P] [US1] Implement mock auth fallback (dev mode) in `lib/data/datasources/mock_auth_datasource.dart`
- [ ] T017 [P] [US1] Set up token storage using flutter_secure_storage in `lib/data/datasources/token_storage.dart`
- [ ] T018 [US1] Create login screen UI matching React's `LoginScreen.tsx` in `lib/presentation/pages/login_screen.dart`
- [ ] T019 [US1] Implement role-based access control (admin/user) in `lib/core/auth/role_checker.dart`
- [ ] T020 [US1] Create dashboard layout with sidebar and header in `lib/presentation/pages/dashboard_layout.dart`
- [ ] T021 [US1] Implement WebSocket connection status display in `lib/presentation/widgets/connection_status.dart`
- [ ] T022 [US1] Create agent list display in sidebar in `lib/presentation/widgets/agent_list.dart`
- [ ] T023 [US1] Implement recent chat history display in sidebar in `lib/presentation/widgets/chat_history_list.dart`
- [ ] T024 [US1] Add route guards for authentication in `lib/presentation/router/auth_guard.dart`

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Real-time Chat with LLM Agents (Priority: P1)

**Goal**: Users can send messages to the orchestrator and receive responses with dynamically rendered UI components

**Independent Test**: Send a message and verify the response contains properly rendered UI components (text, cards, tables, charts)

### Implementation for User Story 2

- [ ] T025 [P] [US2] Create Dio client with interceptors in `lib/data/datasources/api_client.dart`
- [ ] T026 [P] [US2] Implement WebSocket client using `web_socket_channel` in `lib/data/datasources/websocket_client.dart`
- [ ] T027 [P] [US2] Create WebSocket provider with Riverpod in `lib/presentation/providers/websocket_provider.dart`
- [ ] T028 [P] [US2] Create data models: `Agent`, `ChatSession`, `ChatStatus`, `UIComponent` in `lib/data/models/`
- [ ] T029 [P] [US2] Add JSON serialization (`json_serializable`) to all data models
- [ ] T030 [US2] Create chat interface UI in `lib/presentation/pages/chat_interface.dart`
- [ ] T031 [US2] Implement message input with send button in `lib/presentation/widgets/message_input.dart`
- [ ] T032 [US2] Create chat history display (user + assistant messages) in `lib/presentation/widgets/chat_message_list.dart`
- [ ] T033 [US2] Implement loading states (thinking, executing) in `lib/presentation/widgets/chat_status_indicator.dart`
- [ ] T034 [US2] Create DynamicRenderer for backend UI primitives in `lib/presentation/widgets/dynamic_renderer.dart`
- [ ] T035 [US2] Map each component type to Flutter widget in `lib/presentation/widgets/ui_components/`
- [ ] T036 [US2] Implement suggested prompts (from `SUGGESTIONS` array) in `lib/presentation/widgets/suggested_prompts.dart`

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - File Upload and Analysis (Priority: P2)

**Goal**: Users can upload CSV/text files and have them analyzed by agents

**Independent Test**: Upload a CSV file and verify the backend receives it and the agent responds with analysis

### Implementation for User Story 3

- [ ] T037 [P] [US3] Implement file picker for CSV/text/JSON/MD files using `file_picker` in `lib/data/datasources/file_picker_service.dart`
- [ ] T038 [P] [US3] Create multipart file upload to `/api/upload` endpoint in `lib/data/datasources/file_upload_service.dart`
- [ ] T039 [P] [US3] Implement file download from `/api/download/{session_id}/{filename}` in `lib/data/datasources/file_download_service.dart`
- [ ] T040 [US3] Add drag-and-drop support for file upload in `lib/presentation/widgets/file_drag_drop.dart`
- [ ] T041 [US3] Create file attachment UI with preview in `lib/presentation/widgets/file_attachment.dart`
- [ ] T042 [US3] Implement file preview functionality in `lib/presentation/widgets/file_preview.dart`
- [ ] T043 [US3] Add upload progress and error handling in `lib/presentation/widgets/upload_progress.dart`
- [ ] T044 [US3] Handle large files (>10KB) via upload endpoint with proper chunking/streaming

**Checkpoint**: At this point, User Stories 1, 2, and 3 should all work independently

---

## Phase 6: User Story 4 - Saved Components Management (Priority: P2)

**Goal**: Users can save, view, combine, and condense UI components from chat responses

**Independent Test**: Save a component from chat, view it in the drawer, and perform combine/condense operations

### Implementation for User Story 4

- [ ] T045 [P] [US4] Create `SavedComponent` data model in `lib/data/models/saved_component.dart`
- [ ] T046 [P] [US4] Implement saved components repository in `lib/data/repositories/saved_components_repository.dart`
- [ ] T047 [P] [US4] Create saved components provider with Riverpod in `lib/presentation/providers/saved_components_provider.dart`
- [ ] T048 [US4] Create UISavedDrawer for saved components management in `lib/presentation/widgets/ui_saved_drawer.dart`
- [ ] T049 [US4] Implement component previews with titles in `lib/presentation/widgets/component_preview.dart`
- [ ] T050 [US4] Add delete, combine, condense operations in `lib/presentation/widgets/component_operations.dart`
- [ ] T051 [US4] Create ComponentSaveButton ("Add all to UI") in `lib/presentation/widgets/component_save_button.dart`
- [ ] T052 [US4] Implement drag-and-drop reordering of saved components
- [ ] T053 [US4] Show combine/condense status and errors in UI

**Checkpoint**: At this point, User Stories 1-4 should all work independently

---

## Phase 7: User Story 5 - Chat History and Navigation (Priority: P2)

**Goal**: Users can view chat history, load previous conversations, and start new chats

**Independent Test**: Create multiple chats, switch between them, and verify messages persist

### Implementation for User Story 5

- [ ] T054 [P] [US5] Implement chat history repository in `lib/data/repositories/chat_history_repository.dart`
- [ ] T055 [P] [US5] Create chat session persistence in local storage in `lib/data/datasources/chat_storage.dart`
- [ ] T056 [US5] Enhance chat history list with titles and dates in `lib/presentation/widgets/chat_history_item.dart`
- [ ] T057 [US5] Implement chat loading with all previous messages and components
- [ ] T058 [US5] Add "New Chat" button functionality in `lib/presentation/widgets/new_chat_button.dart`
- [ ] T059 [US5] Implement auto-generate chat titles based on content
- [ ] T060 [US5] Persist active chat across app restarts
- [ ] T061 [US5] Display chat preview and date in sidebar

**Checkpoint**: All user stories should now be independently functional

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T062 [P] Documentation updates in `README.md` and code comments
- [ ] T063 [P] Code cleanup and refactoring across all files
- [ ] T064 [P] Performance optimization (60fps animations, smooth scrolling)
- [ ] T065 [P] Add unit tests in `test/` directory
- [ ] T066 [P] Security hardening (input validation, secure storage)
- [ ] T067 [P] Implement deep linking support
- [ ] T068 [P] Add accessibility features (screen reader support, larger text)
- [ ] T069 [P] Create responsive design for mobile/desktop breakpoints
- [ ] T070 [P] Run quickstart validation against React reference
- [ ] T071 [P] Add analytics and crash reporting
- [ ] T072 [P] Implement push notifications for chat messages (if requested)
- [ ] T073 [P] Add offline capabilities (cached chats, draft messages)
- [ ] T074 [P] Leverage native device features (camera, GPS) if needed

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2)
- **Polish (Phase 8)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational (Phase 2) - Depends on US1 for authentication
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) - Depends on US2 for chat interface
- **User Story 4 (P2)**: Can start after Foundational (Phase 2) - Depends on US2 for UI components
- **User Story 5 (P2)**: Can start after Foundational (Phase 2) - Depends on US1 for dashboard and US2 for chat

### Within Each User Story

- Models before services
- Services before UI components
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, user stories can start in parallel with careful coordination
- All data model tasks marked [P] within a story can run in parallel
- Different user stories can be worked on in parallel by different team members after foundational phase

---

## Parallel Example: User Story 1

```bash
# Launch all parallel tasks for User Story 1 together:
Task: "Create authentication provider with Riverpod in lib/presentation/providers/auth_provider.dart"
Task: "Implement OIDC/Keycloak client in lib/data/datasources/auth_datasource.dart"
Task: "Implement mock auth fallback in lib/data/datasources/mock_auth_datasource.dart"
Task: "Set up token storage using flutter_secure_storage in lib/data/datasources/token_storage.dart"
```

## Parallel Example: User Story 2

```bash
# Launch all data model tasks for User Story 2 together:
Task: "Create data models: Agent, ChatSession, ChatStatus, UIComponent in lib/data/models/"
Task: "Add JSON serialization to all data models"
Task: "Create Dio client with interceptors in lib/data/datasources/api_client.dart"
Task: "Implement WebSocket client using web_socket_channel in lib/data/datasources/websocket_client.dart"
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
4. Add User Story 3 → Test independently → Deploy/Demo
5. Add User Story 4 → Test independently → Deploy/Demo
6. Add User Story 5 → Test independently → Deploy/Demo
7. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Authentication & Dashboard)
   - Developer B: User Story 2 (Chat Interface)
   - Developer C: User Story 3 (File Upload)
3. After US1-3 complete:
   - Developer A: User Story 4 (Saved Components)
   - Developer B: User Story 5 (Chat History)
   - Developer C: Polish Phase
4. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify each story works before moving to next
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
- Reference React frontend (`frontend/`) as source of truth for all UI/UX decisions
- Maintain 1:1 feature parity with React frontend
- Use existing backend API endpoints exactly as defined
- Match React's WebSocket protocol and message formats
- Replicate exact visual design (colors, spacing, fonts)
- Support both OIDC/Keycloak and mock authentication
- Handle all UI component types from backend specification
