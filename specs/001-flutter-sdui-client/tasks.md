# Tasks: Flutter SDUI Thin Client

**Input**: Design documents from `/specs/001-flutter-sdui-client/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Paths are relative to repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Archive React frontend, configure Flutter project for AstralBody, establish directory structure, set minimum platform versions

- [x] T001 Archive React frontend by moving frontend/ to frontend-archive-react/
- [x] T002 Update pubspec.yaml with AstralBody dependencies (fl_chart, flutter_appauth, flutter_inappwebview, flutter_secure_storage, connectivity_plus, flutter_color_picker) and set minimum platform versions (iOS 17+, Android API 28+) in astralprojection-flutter/pubspec.yaml
- [x] T003 [P] Create new directory structure: primitives/, platform/tv/, platform/watch/, common/ under astralprojection-flutter/lib/components/
- [x] T004 [P] Update Dockerfile to remove React frontend-builder stage and frontend references
- [x] T005 [P] Update docker-compose.yml to remove frontend port 5173 mapping
- [x] T006 [P] Set minimum deployment targets: iOS 17.0 in ios/Podfile and Runner.xcodeproj, tvOS 17.0 in tvOS target, watchOS 10.0 in watchOS target, Android minSdkVersion 28 in android/app/build.gradle

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented. Rewrites the protocol layer, auth, device profiling, rendering engine, loading overlay, SDUI caching, and dynamic theming.

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T007 Rewrite auth_provider.dart for Keycloak OIDC code flow via flutter_appauth with BFF proxy at /auth/token; implement silent JWT refresh using refresh token (no user interruption) with automatic redirect to re-authentication when refresh token is expired in astralprojection-flutter/lib/state/auth_provider.dart
- [x] T008 Rewrite web_socket_provider.dart for AstralBody protocol (register_ui, ui_render, ui_update, ui_append, ui_event) per backend/shared/protocol.py; re-send register_ui with updated device dimensions on orientation/window resize in astralprojection-flutter/lib/state/web_socket_provider.dart
- [x] T009 [P] Create device_profile_provider.dart that detects device_type, screen dimensions, input_modality, and capabilities per data-model.md in astralprojection-flutter/lib/state/device_profile_provider.dart
- [x] T010 Rewrite dynamic_renderer.dart with AstralBody snake_case primitiveMap (23 component types from primitives.py) in astralprojection-flutter/lib/components/dynamic_renderer.dart
- [x] T011 [P] Create placeholder_widget.dart for unknown component types (bordered box with type name + warning log) in astralprojection-flutter/lib/components/common/placeholder_widget.dart
- [x] T012 [P] Create offline_indicator.dart overlay for WebSocket disconnection state in astralprojection-flutter/lib/components/common/offline_indicator.dart
- [x] T013 [P] Create loading_overlay.dart widget displaying blurred background, centered spinner, and rotating humorous loading messages (e.g., "Loading...", "Reticulating Splines...") shown between authentication and first ui_render response in astralprojection-flutter/lib/components/common/loading_overlay.dart
- [x] T014 [P] Implement SDUI tree disk persistence: save last rendered component tree to local storage (SharedPreferences or file) so on app restart the cached UI displays while reconnecting, replaced by fresh backend state once ui_render is received in astralprojection-flutter/lib/state/web_socket_provider.dart
- [x] T015 [P] Implement dynamic theme provider that applies backend-sent theme config (colors, typography, spacing) from the protocol, with a sensible default fallback theme until backend theme is received in astralprojection-flutter/lib/state/theme_provider.dart
- [x] T016 Update app.dart to register DeviceProfileProvider, ThemeProvider, loading overlay, and wire updated auth/WebSocket providers in astralprojection-flutter/lib/app.dart
- [x] T017 Update config.dart with AstralBody backend host/port and mock auth toggle in astralprojection-flutter/lib/config.dart
- [x] T018 Fix backend TV button adaptation: allow primary buttons on TV in backend/rote/adapter.py _adapt_button method (line ~248)

**Checkpoint**: Foundation ready — protocol, auth, device profile, rendering engine, loading overlay, SDUI caching, and dynamic theming operational. User story implementation can now begin.

---

## Phase 3: User Story 1 — Phone/Tablet User Interacts with SDUI Dashboard (Priority: P1) MVP

**Goal**: A user opens the app on a phone or tablet, authenticates via Keycloak, sees the loading overlay with humorous messages, and then sees a fully backend-driven SDUI dashboard with backend-provided theming. All 23 primitive component types render correctly. User interactions (button taps, form submissions) send actions to backend and trigger re-renders. Orientation changes trigger re-registration with updated device dimensions.

**Independent Test**: Launch on phone/tablet emulator, authenticate, verify loading overlay appears with spinner and rotating messages, verify all component types in the backend-composed dashboard render correctly without layout overflow. Tap a button and confirm re-render. Rotate device and confirm layout re-adapts.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T019 [P] [US1] Unit test for dynamic_renderer primitive mapping and recursive rendering in astralprojection-flutter/test/unit/dynamic_renderer_test.dart
- [x] T020 [P] [US1] Unit test for web_socket_provider register_ui, ui_render, ui_update, ui_event handling and SDUI tree disk persistence/restore in astralprojection-flutter/test/unit/web_socket_provider_test.dart
- [x] T021 [P] [US1] Unit test for auth_provider Keycloak OIDC flow, token storage, and silent JWT refresh in astralprojection-flutter/test/unit/auth_provider_test.dart
- [x] T022 [P] [US1] Unit test for device_profile_provider detection logic (mobile vs tablet thresholds) in astralprojection-flutter/test/unit/device_profile_test.dart
- [x] T023 [P] [US1] Unit test for theme_provider applying backend theme config with fallback defaults in astralprojection-flutter/test/unit/theme_provider_test.dart

### Implementation for User Story 1 — Primitive Widgets

All primitive widgets are independent files and can be implemented in parallel:

- [x] T024 [P] [US1] Create container_widget.dart rendering vertical stack of children via DynamicRenderer in astralprojection-flutter/lib/components/primitives/container_widget.dart
- [x] T025 [P] [US1] Adapt text_widget.dart from TextView to backend text schema (content, variant: h1/h2/h3/body/caption) in astralprojection-flutter/lib/components/primitives/text_widget.dart
- [x] T026 [P] [US1] Adapt button_widget.dart to backend schema (label, action, payload, variant) with ui_event dispatch in astralprojection-flutter/lib/components/primitives/button_widget.dart
- [x] T027 [P] [US1] Adapt input_widget.dart from InputField to backend schema (placeholder, name, value) with ui_event on submit in astralprojection-flutter/lib/components/primitives/input_widget.dart
- [x] T028 [P] [US1] Adapt card_widget.dart to backend schema (title, variant, content[] children) in astralprojection-flutter/lib/components/primitives/card_widget.dart
- [x] T029 [P] [US1] Create table_widget.dart with headers, rows, pagination (total_rows, page_size, page_offset) and page_change ui_event in astralprojection-flutter/lib/components/primitives/table_widget.dart
- [x] T030 [P] [US1] Create list_widget.dart for ordered/unordered lists in astralprojection-flutter/lib/components/primitives/list_widget.dart
- [x] T031 [P] [US1] Create alert_widget.dart with severity variants (info, success, warning, error) in astralprojection-flutter/lib/components/primitives/alert_widget.dart
- [x] T032 [P] [US1] Create progress_widget.dart with value 0.0-1.0, label, and percentage display in astralprojection-flutter/lib/components/primitives/progress_widget.dart
- [x] T033 [P] [US1] Create metric_widget.dart with title, value, subtitle, icon, and optional progress bar in astralprojection-flutter/lib/components/primitives/metric_widget.dart
- [x] T034 [P] [US1] Adapt code_widget.dart from CodeView to backend schema (code, language, show_line_numbers) in astralprojection-flutter/lib/components/primitives/code_widget.dart
- [x] T035 [P] [US1] Create image_widget.dart for remote/data URL images with optional width/height in astralprojection-flutter/lib/components/primitives/image_widget.dart
- [x] T036 [P] [US1] Create grid_widget.dart with columns, gap, and responsive column capping in astralprojection-flutter/lib/components/primitives/grid_widget.dart
- [x] T037 [P] [US1] Create tabs_widget.dart with labeled tab panels rendering content[] children in astralprojection-flutter/lib/components/primitives/tabs_widget.dart
- [x] T038 [P] [US1] Create divider_widget.dart for horizontal rule separator in astralprojection-flutter/lib/components/primitives/divider_widget.dart
- [x] T039 [P] [US1] Create collapsible_widget.dart with title, default_open, expandable content[] in astralprojection-flutter/lib/components/primitives/collapsible_widget.dart
- [x] T040 [P] [US1] Create bar_chart_widget.dart using fl_chart with title, labels, datasets in astralprojection-flutter/lib/components/primitives/bar_chart_widget.dart
- [x] T041 [P] [US1] Create line_chart_widget.dart using fl_chart with title, labels, datasets in astralprojection-flutter/lib/components/primitives/line_chart_widget.dart
- [x] T042 [P] [US1] Create pie_chart_widget.dart using fl_chart with title, labels, data, colors in astralprojection-flutter/lib/components/primitives/pie_chart_widget.dart
- [x] T043 [P] [US1] Create plotly_chart_widget.dart with WebView rendering on mobile/tablet and metric fallback on TV/watch in astralprojection-flutter/lib/components/primitives/plotly_chart_widget.dart
- [x] T044 [P] [US1] Create color_picker_widget.dart with label, color_key, and value in astralprojection-flutter/lib/components/primitives/color_picker_widget.dart
- [x] T045 [P] [US1] Adapt file_upload_widget.dart from FileUploadField to backend schema (label, accept, action) in astralprojection-flutter/lib/components/primitives/file_upload_widget.dart
- [x] T046 [P] [US1] Create file_download_widget.dart with label, url, filename in astralprojection-flutter/lib/components/primitives/file_download_widget.dart

### Implementation for User Story 1 — Layout, Navigation & Auth UI

- [x] T047 [US1] Update workspace_layout.dart to render SDUIComponentTree from web_socket_provider state, show loading_overlay while awaiting first ui_render, and show cached SDUI tree on app restart in astralprojection-flutter/lib/components/workspace/workspace_layout.dart
- [x] T048 [US1] Update nav_bar.dart for responsive phone/tablet navigation in astralprojection-flutter/lib/components/navigation/nav_bar.dart
- [x] T049 [US1] Update app_theme.dart with phone and tablet theme variants as default fallback, deferring to backend-provided theme via ThemeProvider when available in astralprojection-flutter/lib/components/theme/app_theme.dart
- [x] T050 [US1] Rewrite login_page.dart for Keycloak OIDC flow (system browser redirect) with mock auth fallback in astralprojection-flutter/lib/components/auth/login_page.dart
- [x] T051 [US1] Update project_dropdown.dart for AstralBody REST API project listing in astralprojection-flutter/lib/components/workspace/project_dropdown.dart

### Widget Tests for User Story 1

- [x] T052 [P] [US1] Widget tests for text, button, input, card primitives in astralprojection-flutter/test/widget/primitives/text_widget_test.dart, button_widget_test.dart, input_widget_test.dart, card_widget_test.dart
- [x] T053 [P] [US1] Widget tests for table, list, alert, progress, metric primitives in astralprojection-flutter/test/widget/primitives/table_widget_test.dart, list_widget_test.dart, alert_widget_test.dart, progress_widget_test.dart, metric_widget_test.dart
- [x] T054 [P] [US1] Widget tests for chart widgets (bar, line, pie, plotly) in astralprojection-flutter/test/widget/primitives/chart_widget_test.dart
- [x] T055 [P] [US1] Widget tests for layout widgets (container, grid, tabs, collapsible, divider) in astralprojection-flutter/test/widget/primitives/
- [x] T056 [P] [US1] Widget tests for code, image, color_picker, file_upload, file_download in astralprojection-flutter/test/widget/primitives/
- [x] T057 [P] [US1] Widget tests for placeholder_widget, offline_indicator, and loading_overlay in astralprojection-flutter/test/widget/placeholder_test.dart, offline_indicator_test.dart, loading_overlay_test.dart

### Integration Tests for User Story 1

- [x] T058 [US1] Integration test: phone end-to-end flow (auth via KEYCLOAK_TEST_USER/KEYCLOAK_TEST_PASSWORD env vars → loading overlay with spinner → connect → render → interact → re-render → rotate device → verify re-adaptation) in astralprojection-flutter/test/integration/phone_rendering_test.dart
- [x] T059 [US1] Integration test: tablet layout adaptation with same SDUI tree (auth via env vars) in astralprojection-flutter/test/integration/tablet_rendering_test.dart
- [x] T060 [US1] Integration test: app restart shows cached SDUI tree while reconnecting, then replaces with fresh backend state in astralprojection-flutter/test/integration/cached_ui_test.dart

**Checkpoint**: Phone and tablet users can authenticate, see loading overlay, receive backend-composed SDUI dashboards with dynamic theming, interact with all 23 component types, and see cached UI on restart. MVP delivered.

---

## Phase 4: User Story 2 — Real-Time Chat and Agent Interaction on Mobile (Priority: P1)

**Goal**: Users can chat with backend agents in real time. Messages stream via WebSocket with inline SDUI components (tables, charts, alerts). File upload, save/combine workflows work. Auto-reconnect on connection loss with cached UI persistence.

**Independent Test**: Connect to backend WebSocket from mobile emulator, send a chat message, verify streamed SDUI components render inline. Drop connection and verify auto-reconnect restores state. Kill app, reopen, verify cached UI shows while reconnecting.

### Tests for User Story 2

- [x] T061 [P] [US2] Unit test for ui_append message handling and chat message streaming in astralprojection-flutter/test/unit/chat_streaming_test.dart
- [x] T062 [P] [US2] Unit test for auto-reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s) in astralprojection-flutter/test/unit/web_socket_reconnect_test.dart

### Implementation for User Story 2

- [x] T063 [US2] Implement ui_append handler for real-time chat message streaming with inline SDUI components in astralprojection-flutter/lib/state/web_socket_provider.dart
- [x] T064 [US2] Implement auto-reconnect with exponential backoff and session_id preservation in astralprojection-flutter/lib/state/web_socket_provider.dart
- [x] T065 [US2] Implement chat input bar with message send (ui_event chat_message) and file upload in astralprojection-flutter/lib/components/workspace/workspace_layout.dart
- [x] T066 [US2] Implement save_component and combine_components action workflows in astralprojection-flutter/lib/components/workspace/workspace_layout.dart
- [x] T067 [US2] Integration test: WebSocket chat flow with inline SDUI and reconnection in astralprojection-flutter/test/integration/websocket_flow_test.dart

**Checkpoint**: Users can chat with agents, see real-time SDUI-rendered responses, upload files, save/combine components, and survive connection drops gracefully with cached UI.

---

## Phase 5: User Story 3 — TV User Browses Dashboard (Priority: P2)

**Goal**: Users on Android TV / Apple TV see the same backend-driven dashboard optimized for 10-foot viewing with backend-provided TV theme. D-pad/remote navigation with clear focus indicators on all interactive elements.

**Independent Test**: Launch on TV emulator, navigate dashboard with D-pad/arrow keys, verify components render with large text/spacing and focus indicators highlight interactive elements.

### Tests for User Story 3

- [x] T068 [P] [US3] Widget tests for TV focus navigation and focus indicators on interactive primitives in astralprojection-flutter/test/widget/tv_focus_test.dart
- [x] T069 [P] [US3] Widget tests for TV theme (1.5x text scale, generous spacing) in astralprojection-flutter/test/widget/tv_theme_test.dart

### Implementation for User Story 3

- [x] T070 [P] [US3] Create tv_focus_manager.dart wrapping root with FocusTraversalGroup and D-pad Shortcuts for remote navigation in astralprojection-flutter/lib/platform/tv/tv_focus_manager.dart
- [x] T071 [P] [US3] Create tv_theme.dart with 1.5x text scale, generous spacing, high-contrast focus colors as TV fallback theme (overridden by backend TV theme via ThemeProvider when available) in astralprojection-flutter/lib/platform/tv/tv_theme.dart
- [x] T072 [US3] Add FocusNode and visual focus indicators to all interactive primitives (button, input, tabs, collapsible) for TV mode in astralprojection-flutter/lib/components/primitives/
- [x] T073 [US3] Register TV theme and focus manager in app.dart, activate based on device_profile device_type in astralprojection-flutter/lib/app.dart
- [x] T074 [US3] Integration test: TV D-pad navigation, focus traversal, and component rendering in astralprojection-flutter/test/integration/tv_rendering_test.dart

**Checkpoint**: TV users can browse the full dashboard with remote/D-pad navigation, clear focus indicators, and TV-optimized sizing.

---

## Phase 6: User Story 4 — Apple Watch User Receives Glanceable Updates (Priority: P3)

**Goal**: Apple Watch users open a companion app and see glanceable SDUI views: key metrics, alerts, status cards. Minimal interaction (tap to acknowledge). Unsupported components degrade gracefully. Watch app is a native watchOS companion (SwiftUI) per research R5. Minimum watchOS 10.0.

**Independent Test**: Launch watchOS app on watch simulator, receive SDUI tree from backend, verify only watch-compatible components (text, metric, alert, card, button) render on the small screen.

### Tests for User Story 4

- [x] T075 [P] [US4] Widget tests for watch_renderer component filtering (only text, metric, alert, card, button) in astralprojection-flutter/test/widget/watch_renderer_test.dart
- [x] T076 [P] [US4] Widget tests for watch_theme compact layout (40mm screen) in astralprojection-flutter/test/widget/watch_theme_test.dart

### Implementation for User Story 4

- [x] T077 [P] [US4] Create watch_renderer.dart that filters SDUI tree to watch-subset components and degrades unsupported types (charts to metric, tables to lists) in astralprojection-flutter/lib/platform/watch/watch_renderer.dart
- [x] T078 [P] [US4] Create watch_theme.dart with compact glanceable layout optimized for ~200px viewport in astralprojection-flutter/lib/platform/watch/watch_theme.dart
- [x] T079 [US4] Create native watchOS companion app target (min watchOS 10.0) with SwiftUI SDUI renderers for text, metric, alert, card, button in astralprojection-flutter/ios/ (Xcode watchOS target)
- [x] T080 [US4] Implement watch WebSocket connection sending register_ui with device_type "watch" and watch capabilities in watchOS companion app
- [x] T081 [US4] Integration test: watch glanceable rendering and graceful degradation in astralprojection-flutter/test/integration/watch_rendering_test.dart

**Checkpoint**: Apple Watch users see glanceable metrics, alerts, and cards from the backend. Unsupported components degrade gracefully. Tap interactions acknowledged.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Quality, accessibility, performance, and documentation improvements across all user stories

- [x] T082 [P] Add /// Dart doc comments to all public members across astralprojection-flutter/lib/
- [x] T083 [P] Run dart analyze and fix all lint errors across astralprojection-flutter/
- [x] T084 [P] Accessibility audit: add Semantics widgets for VoiceOver (iOS) and TalkBack (Android) to all rendered primitives
- [ ] T085 Performance optimization: verify dashboard interactive within 5s (phone/tablet/TV), 3s (watch), SDUI updates visible within 1s
- [x] T086 Update CLAUDE.md to remove React frontend references and reflect Flutter client
- [ ] T087 Run full quickstart.md validation (all 10 steps) and fix any issues
- [ ] T088 Verify 90%+ test coverage via flutter test --coverage per constitution requirement

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup (T002 for dependencies) — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational (Phase 2) completion
- **US2 (Phase 4)**: Depends on Foundational (Phase 2); builds on US1 primitives for inline SDUI rendering
- **US3 (Phase 5)**: Depends on Foundational (Phase 2); reuses US1 primitives with TV adaptations
- **US4 (Phase 6)**: Depends on Foundational (Phase 2); reuses subset of US1 primitives with watch filtering
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — No dependencies on other stories. Delivers all 23 primitive renderers.
- **US2 (P1)**: Can start after Phase 2 — Uses US1 primitives for inline chat rendering. Best started after US1 primitives exist (T024-T046).
- **US3 (P2)**: Can start after Phase 2 — Adds TV focus/theme layer on top of US1 primitives. Independent of US2.
- **US4 (P3)**: Can start after Phase 2 — Watch renderer filters US1 primitives + native SwiftUI companion. Independent of US2/US3.

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD)
- Primitive widgets before layout/navigation integration
- Core implementation before integration tests
- Story complete and checkpoint validated before moving to next priority

### Parallel Opportunities

- **Phase 1**: T003, T004, T005, T006 can run in parallel
- **Phase 2**: T009, T011, T012, T013, T014, T015 can run in parallel; T007, T008 are independent of each other but T010 depends on knowing the primitive map
- **Phase 3**: All 23 primitive widget tasks (T024-T046) can run in parallel; all widget test groups (T052-T057) can run in parallel; all unit test tasks (T019-T023) can run in parallel
- **Phase 4-6**: US3 and US4 can run in parallel with each other (after US1 primitives exist)

---

## Parallel Example: User Story 1 Primitives

```bash
# Launch all unit tests for US1 together (write first, expect failures):
Task T019: "Unit test for dynamic_renderer"
Task T020: "Unit test for web_socket_provider"
Task T021: "Unit test for auth_provider"
Task T022: "Unit test for device_profile_provider"
Task T023: "Unit test for theme_provider"

# Launch all 23 primitive widgets in parallel (different files, no deps):
Task T024: "container_widget.dart"
Task T025: "text_widget.dart"
Task T026: "button_widget.dart"
... (all through T046)

# Launch all widget test groups in parallel:
Task T052: "Widget tests for text, button, input, card"
Task T053: "Widget tests for table, list, alert, progress, metric"
Task T054: "Widget tests for chart widgets"
Task T055: "Widget tests for layout widgets"
Task T056: "Widget tests for code, image, color_picker, file widgets"
Task T057: "Widget tests for placeholder, offline_indicator, loading_overlay"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (archive React, configure Flutter, set platform minimums)
2. Complete Phase 2: Foundational (auth with silent refresh, protocol, device profile, renderer, loading overlay, SDUI caching, dynamic theming)
3. Complete Phase 3: User Story 1 (all 23 primitives, phone/tablet rendering)
4. **STOP and VALIDATE**: Launch on phone/tablet emulator, authenticate, verify loading overlay, verify all components render, verify cached UI on restart
5. Deploy/demo MVP — phone/tablet dashboard is fully functional

### Incremental Delivery

1. Setup + Foundational -> Foundation ready
2. Add US1 (Phone/Tablet Dashboard) -> Test independently -> Deploy/Demo (MVP!)
3. Add US2 (Real-Time Chat) -> Test independently -> Deploy/Demo
4. Add US3 (TV Dashboard) -> Test independently -> Deploy/Demo
5. Add US4 (Apple Watch) -> Test independently -> Deploy/Demo
6. Each story adds a new device target without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: US1 primitives (T024-T046) — high parallelism, 23 independent files
   - Developer B: US1 layout/navigation (T047-T051) — after a few primitives exist
3. After US1 primitives exist:
   - Developer A: US2 (chat streaming, reconnect)
   - Developer B: US3 (TV focus, theme)
   - Developer C: US4 (watch renderer, SwiftUI companion)
4. Stories complete and integrate independently

---

## Changes from Clarification Session

The following tasks were added or updated based on spec clarifications (session 2026-04-03):

| Change | Clarification | Tasks Affected |
|--------|--------------|----------------|
| Loading overlay | Blurred background + spinner + rotating humorous messages between auth and first ui_render | T013 (new), T057 (new test), T047 (updated), T058 (updated) |
| Silent JWT refresh | Refresh token silently; redirect to re-auth only when refresh token expired | T007 (updated), T021 (updated) |
| SDUI tree disk persistence | Cache last rendered tree to disk; show on app restart while reconnecting | T014 (new), T020 (updated), T047 (updated), T060 (new integration test) |
| Backend dynamic theming | Theme config sent by backend as part of protocol; client applies dynamically with fallback | T015 (new), T023 (new test), T049 (updated), T071 (updated) |
| Minimum platform versions | iOS 17+, Android API 28+, watchOS 10+, tvOS 17+ | T002 (updated), T006 (new), T079 (updated) |
| Orientation re-registration | Re-send register_ui with updated device dimensions on rotation | T008 (updated), T058 (updated) |

---

## Notes

- [P] tasks = different files, no dependencies — safe to run in parallel
- [Story] label maps task to specific user story for traceability
- All component schemas follow contracts/sdui-component-contract.md
- WebSocket protocol follows contracts/websocket-protocol-contract.md
- Backend primitives.py is source of truth for component types (snake_case)
- The Flutter client NEVER contains business logic — pure SDUI renderer
- Watch companion is native SwiftUI (research R5) due to Flutter watchOS limitations
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
