# Tasks: Flutter Migration QA & Feature Parity

**Input**: Design documents from `/specs/002-flutter-migration-qa/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included — spec requests both automated tests and manual QA checklists.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `src/backend/` (AstralBody repo root)
- **Flutter client**: `astralprojection-flutter/lib/` (sibling repo)
- **Flutter tests**: `astralprojection-flutter/test/` (sibling repo)
- **React reference**: `frontend-archive-react/` (archived, read-only)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify project state, add missing dependencies, configure test tooling

- [X] T001 Verify Flutter project compiles and `dart analyze` passes in astralprojection-flutter/
- [X] T002 Add `record` (^5.x) package for STT audio recording to astralprojection-flutter/pubspec.yaml and document rationale (Constitution V)
- [X] T003 [P] Add `flutter_math_fork` package for LaTeX math rendering to astralprojection-flutter/pubspec.yaml and document rationale (Constitution V)
- [X] T004 [P] Create test helper that reads `.env` credentials from AstralBody repo for integration tests in astralprojection-flutter/test/helpers/env_helper.dart
- [X] T005 [P] Verify backend starts and `/auth/login` endpoint responds per contract in src/backend/orchestrator/auth.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core fixes that MUST complete before user story work begins

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T006 Implement Keycloak OIDC authorization code + PKCE flow in astralprojection-flutter/lib/state/auth_provider.dart using flutter_appauth with BFF token proxy at /auth/token per contracts/auth-flow.md
- [X] T007 Implement token persistence (store JWT + refresh token in flutter_secure_storage) and silent refresh logic in astralprojection-flutter/lib/state/auth_provider.dart
- [X] T008 [P] Refactor login page to always show BOTH username/password form AND SSO button (remove MOCK_AUTH toggle of UI layout) in astralprojection-flutter/lib/components/auth/login_page.dart per research.md R2
- [X] T009 [P] Update app theme with exact React color values (background 0xFF0F1221, surface 0xFF1A1E2E, primary 0xFF6366F1, secondary 0xFF8B5CF6, text 0xFFF3F4F6, accent 0xFF06B6D4) in astralprojection-flutter/lib/components/theme/app_theme.dart per research.md R9

**Checkpoint**: Foundation ready — auth works end-to-end, login shows both forms, theme matches React

---

## Phase 3: User Story 1 — Login with Username & Password (Priority: P1) 🎯 MVP

**Goal**: Users can authenticate via username/password or Keycloak SSO on any device and reach the dashboard

**Independent Test**: Enter `KEYCLOAK_TEST_USER` / `KEYCLOAK_TEST_PASSWORD` on login screen → verify dashboard loads within 5 seconds

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T010 [P] [US1] Write widget test for login page rendering both auth forms (username/password + SSO button) in astralprojection-flutter/test/widget/auth/login_page_test.dart
- [X] T011 [P] [US1] Write unit test for AuthProvider mock auth login flow (success + failure) in astralprojection-flutter/test/unit/auth_provider_test.dart
- [X] T012 [P] [US1] Write unit test for AuthProvider OIDC flow (token exchange, profile extraction, token refresh) in astralprojection-flutter/test/unit/auth_provider_oidc_test.dart
- [X] T013 [P] [US1] Write integration test for full login → dashboard journey using test credentials in astralprojection-flutter/test/integration/auth_integration_test.dart

### Implementation for User Story 1

- [X] T014 [US1] Wire login page username/password form to POST /auth/login endpoint, handle 200 (store token, navigate to dashboard) and 401 (inline error) in astralprojection-flutter/lib/components/auth/login_page.dart
- [X] T015 [US1] Wire login page SSO button to flutter_appauth authorizeAndExchangeCode with Keycloak authority, client ID, scopes, redirect URI, and BFF token endpoint override in astralprojection-flutter/lib/components/auth/login_page.dart
- [X] T016 [US1] Implement JWT claim extraction (sub, preferred_username, realm_access.roles) for AuthProfile construction in astralprojection-flutter/lib/state/auth_provider.dart
- [X] T017 [US1] Implement session restore on app launch — read tokens from flutter_secure_storage, check expiry, silent refresh if needed in astralprojection-flutter/lib/state/auth_provider.dart
- [X] T018 [US1] Handle auth error states: invalid credentials (inline error), Keycloak unreachable (clear message + retry), token refresh failure (redirect to login) in astralprojection-flutter/lib/state/auth_provider.dart
- [X] T019 [US1] Verify login page glass-morphism card styling matches React LoginScreen.tsx (gradient background, BackdropFilter blur, semi-transparent card) in astralprojection-flutter/lib/components/auth/login_page.dart

**Checkpoint**: User Story 1 complete — users can log in via both methods and reach dashboard

---

## Phase 4: User Story 2 — Dashboard & Chat Feature Parity on Phone/Tablet (Priority: P1)

**Goal**: Phone/tablet users get the same core features as the React frontend: sidebar, chat, SDUI rendering, file upload, voice I/O, saved components, agent permissions

**Independent Test**: Log in on iPhone + Android tablet, open chat, send messages, receive SDUI responses, upload file, use voice, manage saved components — compare against React

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T020 [P] [US2] Write widget test for saved components drawer (save, combine DnD, condense) in astralprojection-flutter/test/widget/workspace/saved_components_drawer_test.dart
- [X] T021 [P] [US2] Write widget test for agent permissions bottom sheet (scope cards, tool toggles) in astralprojection-flutter/test/widget/agents/agent_permissions_sheet_test.dart
- [X] T022 [P] [US2] Write unit test for VoiceInputService (WebSocket streaming, PCM16 format) in astralprojection-flutter/test/unit/voice_input_service_test.dart
- [X] T023 [P] [US2] Write unit test for VoiceOutputService (TTS audio playback via just_audio) in astralprojection-flutter/test/unit/voice_output_service_test.dart
- [X] T024 [P] [US2] Write unit test for GeolocationService (silent capture, capability gating) in astralprojection-flutter/test/unit/geolocation_service_test.dart

### Implementation for User Story 2

- [X] T025 [P] [US2] Create VoiceInputService — open WebSocket to /api/voice/stream, stream PCM16 at 24kHz, receive transcript in astralprojection-flutter/lib/services/voice_input_service.dart
- [X] T026 [P] [US2] Create VoiceOutputService — receive audio URL from backend, play via just_audio in astralprojection-flutter/lib/services/voice_output_service.dart
- [X] T027 [P] [US2] Create GeolocationService — silent GPS capture, gated by DeviceProfile.hasGeolocation in astralprojection-flutter/lib/services/geolocation_service.dart
- [X] T028 [US2] Create SavedComponentsDrawer widget — grid layout, LongPressDraggable + DragTarget for combine, "Condense All" button, delete per component, full-screen inspect in astralprojection-flutter/lib/components/workspace/saved_components_drawer.dart
- [X] T029 [US2] Wire SavedComponentsDrawer to WebSocket messages: save_component, get_saved_components, delete_saved_component, combine_components, condense_components per contracts/sdui-protocol.md in astralprojection-flutter/lib/components/workspace/saved_components_drawer.dart
- [X] T030 [US2] Create AgentPermissionsSheet bottom sheet — 4 scope cards (read/green, write/amber, search/blue, system/purple), expandable tool lists with toggles, confirmation dialog in astralprojection-flutter/lib/components/agents/agent_permissions_sheet.dart
- [X] T031 [US2] Wire AgentPermissionsSheet to backend system_config and agent_registered messages for scope/tool data in astralprojection-flutter/lib/components/agents/agent_permissions_sheet.dart
- [X] T032 [US2] Add voice input/output controls to chat interface — show mic button + speaker toggle, hide on devices without microphone (TV) per DeviceProfile in astralprojection-flutter/lib/components/workspace/
- [X] T033 [US2] Verify sidebar renders chat history list and agent list with status indicators, matches React structure (collapsible on phone, persistent on tablet landscape) in astralprojection-flutter/lib/components/navigation/
- [X] T034 [US2] Verify file upload via file_picker works — tap attachment button, select file, stage for upload, send with message in astralprojection-flutter/lib/components/primitives/
- [X] T035 [US2] Verify all 23 SDUI primitive types render correctly on phone/tablet — cross-reference against React rendering for each type listed in contracts/sdui-protocol.md
- [X] T036 [US2] Add LaTeX math rendering support using flutter_math_fork within flutter_markdown for inline/block math expressions in astralprojection-flutter/lib/components/primitives/

**Checkpoint**: User Story 2 complete — full feature parity with React on phone/tablet

---

## Phase 5: User Story 3 — Visual & UX Parity with React Frontend (Priority: P1)

**Goal**: Flutter app visually matches React frontend — same branding, colors, glass-morphism, layout patterns, and interaction flows

**Independent Test**: Side-by-side comparison of login, dashboard, chat, agent permissions screens between React (frontend-archive-react/) and Flutter app

### Tests for User Story 3

- [X] T037 [P] [US3] Write widget test verifying AstralDeep branding (logo, app name, tagline) renders on login screen in astralprojection-flutter/test/widget/auth/login_branding_test.dart
- [X] T038 [P] [US3] Write widget test verifying glass-morphism card styling (BackdropFilter, semi-transparent surface) on key screens in astralprojection-flutter/test/widget/theme/glass_card_test.dart

### Implementation for User Story 3

- [X] T039 [US3] Create reusable GlassCard widget matching React .glass-card CSS (BackdropFilter blur, surface.withOpacity(0.6), border Color(0xFFFFFFFF).withOpacity(0.1)) in astralprojection-flutter/lib/components/common/glass_card.dart
- [X] T040 [US3] Apply GlassCard to login form, sidebar, and chat message cards replacing plain Container widgets in astralprojection-flutter/lib/components/
- [X] T041 [US3] Verify dashboard layout proportions match React — sidebar width, chat area proportions, navigation patterns in astralprojection-flutter/lib/components/workspace/
- [X] T042 [US3] Verify SDUI component rendering styles match React — card borders, button styles, table formatting, chart colors per contracts/sdui-protocol.md in astralprojection-flutter/lib/components/primitives/
- [X] T043 [US3] Verify error states match React — connection lost indicator, auth failure messages, empty states in astralprojection-flutter/lib/components/common/
- [X] T044 [US3] Create manual QA checklist for visual parity: side-by-side screenshots of login, dashboard, chat, agent permissions, saved components comparing React vs Flutter

**Checkpoint**: User Story 3 complete — Flutter visually matches React across all key screens

---

## Phase 6: User Story 4 — TV Dashboard Navigation (Priority: P2)

**Goal**: Apple TV users can navigate the full dashboard using D-pad/remote with TV-optimized fonts and spacing

**Independent Test**: Launch on Apple TV simulator, navigate entirely with D-pad, log in, browse dashboard

### Tests for User Story 4

- [X] T045 [P] [US4] Write widget test for TV focus navigation — D-pad moves focus predictably between login fields, buttons in astralprojection-flutter/test/widget/platform/tv_focus_test.dart
- [X] T046 [P] [US4] Write widget test for TV theme adjustments — 1.5x text scale, 32px padding, generous touch targets in astralprojection-flutter/test/widget/platform/tv_theme_test.dart

### Implementation for User Story 4

- [X] T047 [US4] Verify TvFocusManager handles D-pad navigation on login screen — focus order: username → password → Sign In → SSO button in astralprojection-flutter/lib/components/platform/tv/
- [X] T048 [US4] Verify TV theme applies correct scaling — text 1.5x, content padding 32px, button padding 48h/24v, visual density comfortable (4.0) per contracts/device-profile.md in astralprojection-flutter/lib/components/platform/tv/
- [X] T049 [US4] Verify any dashboard destination is reachable within 5 D-pad presses from home screen in astralprojection-flutter/lib/components/platform/tv/
- [X] T050 [US4] Verify voice/file controls are hidden on TV (DeviceProfile.hasMicrophone=false, hasFileSystem=false) in astralprojection-flutter/lib/components/platform/tv/
- [X] T051 [US4] Create manual QA checklist for Apple TV: D-pad navigation flow, focus indicators (3px amber #FFD600 border), text readability at 10ft distance

**Checkpoint**: User Story 4 complete — Apple TV fully navigable via D-pad

---

## Phase 7: User Story 5 — Apple Watch Glanceable Dashboard (Priority: P3)

**Goal**: Watch users see simplified dashboard with key metrics, alerts, and summary cards; unsupported components degrade gracefully

**Independent Test**: Launch on Apple Watch simulator, log in, verify supported components render, unsupported show placeholders, loads within 3 seconds

### Tests for User Story 5

- [X] T052 [P] [US5] Write widget test for WatchRenderer component degradation — charts→metric, table→list, unsupported→placeholder in astralprojection-flutter/test/widget/platform/watch_renderer_test.dart
- [X] T053 [P] [US5] Write widget test for watch dashboard load time (< 3 seconds target) in astralprojection-flutter/test/widget/platform/watch_performance_test.dart

### Implementation for User Story 5

- [X] T054 [US5] Verify WatchRenderer supported component set (text, metric, alert, card, button, list, progress, divider, container) renders correctly per contracts/device-profile.md in astralprojection-flutter/lib/components/platform/watch/
- [X] T055 [US5] Verify WatchRenderer degradation rules — bar/line/pie/plotly_chart→metric (title + first value), table→list (first column), others silently skipped in astralprojection-flutter/lib/components/platform/watch/
- [X] T056 [US5] Verify button events fire correctly on watch — tap button, event dispatched via WebSocket, response updates display in astralprojection-flutter/lib/components/platform/watch/
- [X] T057 [US5] Verify watch DeviceProfile reports correct capabilities (has_touch=true, has_microphone=false, has_camera=false, has_file_system=false) in astralprojection-flutter/lib/state/device_profile_provider.dart
- [X] T058 [US5] Create manual QA checklist for Apple Watch: component rendering, glanceable layout, 3s load time, button interactivity

**Checkpoint**: User Story 5 complete — Watch displays glanceable dashboard with correct degradation

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Cross-device QA, performance validation, edge cases, and final cleanup

- [X] T059 [P] Verify graceful placeholder widget renders for unknown SDUI component types (never crash) in astralprojection-flutter/lib/components/dynamic_renderer.dart
- [X] T060 [P] Verify offline indicator displays on WebSocket disconnect + auto-reconnect with exponential backoff (1s→2s→4s→8s→16s→30s max) per contracts/sdui-protocol.md in astralprojection-flutter/lib/state/web_socket_provider.dart
- [X] T061 [P] Verify cached SDUI tree loads from SharedPreferences during reconnect and on app restart in astralprojection-flutter/lib/state/web_socket_provider.dart
- [X] T062 [P] Verify device rotation preserves chat state and scroll position, layout adapts responsively in astralprojection-flutter/lib/components/workspace/
- [X] T063 [P] Verify device profile re-sent on orientation change with new dimensions per contracts/device-profile.md in astralprojection-flutter/lib/state/device_profile_provider.dart
- [X] T064 Run full test suite (`flutter test` + `dart analyze`) and ensure all new tests pass in astralprojection-flutter/
- [X] T065 Run performance benchmarks: login < 5s (phone/tablet), SSO login < 10s, SDUI updates < 1s, watch dashboard < 3s, reconnect < 10s
- [X] T066 Create comprehensive cross-device manual QA matrix covering all 5 form factors (iOS phone, Android phone, iOS tablet, Android tablet, Apple TV) + Apple Watch per research.md R8
- [X] T067 Run `dart analyze` and resolve any new warnings or errors in astralprojection-flutter/
- [X] T068 Update astralprojection-flutter/pubspec.yaml dependency documentation with rationale for any newly added packages (Constitution V)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup (T001-T005) — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (especially T006-T008)
- **User Story 2 (Phase 4)**: Depends on Foundational; partially depends on US1 for login (but independently testable with mock auth)
- **User Story 3 (Phase 5)**: Depends on Foundational (T009 theme); benefits from US1+US2 completion for full screen comparison
- **User Story 4 (Phase 6)**: Depends on Foundational; independent of US2/US3
- **User Story 5 (Phase 7)**: Depends on Foundational; independent of other stories
- **Polish (Phase 8)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: Foundation only — no cross-story dependencies
- **US2 (P1)**: Foundation only — independently testable (login via mock auth)
- **US3 (P1)**: Foundation (theme) — benefits from US1+US2 for full visual comparison but core work is independent
- **US4 (P2)**: Foundation only — TV form factor is independent
- **US5 (P3)**: Foundation only — Watch form factor is independent

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- UI components before wiring to backend
- Core functionality before edge cases
- Story complete before moving to next priority

### Parallel Opportunities

- Setup tasks T002, T003, T004, T005 can all run in parallel
- Foundational T008 (login page) and T009 (theme) can run in parallel with each other (but T006/T007 are sequential — OIDC then token persistence)
- Once Foundation completes, US1 through US5 can run in parallel (different form factors, different files)
- Within US2: T025, T026, T027 (voice input, voice output, geolocation) are independent services in separate files
- Within US2: T028/T029 (saved components) and T030/T031 (agent permissions) are independent features
- All test tasks within a phase marked [P] can run in parallel

---

## Parallel Example: User Story 2

```bash
# Launch all tests for US2 together:
Task T020: "Widget test for saved components drawer"
Task T021: "Widget test for agent permissions sheet"
Task T022: "Unit test for VoiceInputService"
Task T023: "Unit test for VoiceOutputService"
Task T024: "Unit test for GeolocationService"

# Launch all independent services together:
Task T025: "Create VoiceInputService"
Task T026: "Create VoiceOutputService"
Task T027: "Create GeolocationService"

# Launch independent feature widgets together:
Task T028: "Create SavedComponentsDrawer"
Task T030: "Create AgentPermissionsSheet"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1 (Login)
4. **STOP and VALIDATE**: Test login via both auth methods on phone
5. Deploy/demo if ready — users can authenticate

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 (Login) → Test independently → MVP! Users can authenticate
3. Add US2 (Dashboard & Chat Parity) → Test independently → Core feature parity achieved
4. Add US3 (Visual Parity) → Test independently → Full visual match with React
5. Add US4 (TV) → Test independently → TV form factor validated
6. Add US5 (Watch) → Test independently → All form factors covered
7. Polish → Cross-device QA, performance, edge cases

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: US1 (Login) + US3 (Visual Parity)
   - Developer B: US2 (Dashboard Features — voice, saved components, agent permissions)
   - Developer C: US4 (TV) + US5 (Watch)
3. Stories complete and integrate independently
4. Team reconvenes for Phase 8 Polish + cross-device QA
