---
description: "Task list for 041-android-sdui-client"
---

# Tasks: Native Android Client (SDUI Target)

**Input**: Design documents from `specs/041-android-sdui-client/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED — the spec mandates automated tests (FR-016) and Constitution III requires ≥90% changed-code coverage. JVM unit tests cover all `:core` pure logic; Compose UI tests cover representative renderers/screens.

**Organization**: Grouped by user story (US1 P1 → US2 P2 → US3 P2 → US4 P3) for independent implementation and testing. Paths follow plan.md: `android-client/{core,app}/…` with package `com.kyopenscience.astral.{core,app}`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no incomplete-task dependency)
- **[Story]**: US1–US4 (setup/foundational/polish have no story label)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Stand up the Gradle project, modules, dependency catalog, and tooling.

- [X] T001 Create the `android-client/` Gradle project skeleton (Gradle wrapper, `android-client/settings.gradle.kts` including `:core` and `:app`, root `android-client/build.gradle.kts`) per plan.md.
- [X] T002 [P] Configure the `:app` Android module (applicationId/namespace `com.kyopenscience.astral`, minSdk 26, targetSdk current, Compose BOM + Material 3 + Material 3 Adaptive) in `android-client/app/build.gradle.kts`.
- [X] T003 [P] Configure the `:core` pure-Kotlin module (JVM 17, kotlinx.serialization, coroutines; JUnit + kotlinx-coroutines-test) in `android-client/core/build.gradle.kts`.
- [X] T004 [P] Declare the approved dependency set (OkHttp/Okio, kotlinx.serialization-json, AppAuth-Android + AndroidX Browser, Coil, AndroidX Security-Crypto/DataStore/Lifecycle/Navigation-Compose) in `android-client/gradle/libs.versions.toml` (Principle V — to be approved in the PR).
- [X] T005 [P] Configure ktlint/detekt + Android Lint + Kover (≥90% changed-code gate) in `android-client/build.gradle.kts`.
- [X] T006 [P] Add the dark theme / design tokens mirroring the web + Windows palette in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/ui/theme/Theme.kt`.
- [X] T007 Add the Android CI workflow skeleton (lint + `:core:test` + `:app:assembleDebug`) in `.github/workflows/android-ci.yml` (finalized in Polish).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The wire decode, transport, component/canvas model, app shell, and server device profile that EVERY story needs.

**⚠️ CRITICAL**: No user story can begin until this phase is complete.

- [X] T008 [P] Define the WS message models — inbound sealed union on `type` (`ui_render`/`ui_upsert`/`ui_stream_data`/`stream_*`/`chat_*`/`agent_list`/`history_list`/`chat_status`/`chrome_render`/`auth_required`) + outbound (`register_ui`/`ui_event`) per contracts/ws-protocol.md in `android-client/core/src/main/kotlin/com/kyopenscience/astral/core/protocol/Messages.kt`.
- [X] T009 [P] Implement tolerant JSON decode/encode (`ignoreUnknownKeys`, lenient; dynamic `attributes` as `JsonObject`) in `android-client/core/src/main/kotlin/com/kyopenscience/astral/core/protocol/Wire.kt`.
- [X] T010 [P] Unit tests for protocol decode (every inbound type) + outbound encode (`register_ui` device caps, `ui_event`) in `android-client/core/src/test/kotlin/com/kyopenscience/astral/core/protocol/WireTest.kt`.
- [X] T011 [P] Define the SDUI `Component(type, id, attributes, children)` model + decode + identity (`component_id` ?: `id`) per data-model.md in `android-client/core/src/main/kotlin/com/kyopenscience/astral/core/sdui/Component.kt`.
- [X] T012 [P] Implement the pure canvas reducer (`CanvasOp` upsert/remove keyed by `component_id`) in `android-client/core/src/main/kotlin/com/kyopenscience/astral/core/sdui/Canvas.kt`.
- [X] T013 [P] Unit tests for `Component` decode + canvas reducer (upsert/remove/identity) in `android-client/core/src/test/kotlin/com/kyopenscience/astral/core/sdui/ComponentTest.kt`.
- [X] T014 Implement the OkHttp WebSocket transport (connect, send `register_ui` with android `DeviceCapabilities`, inbound `Flow<InboundMessage>`, outbound `ui_event`/`chat_message`, reconnect/backoff, connection-state) in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/transport/OrchestratorClient.kt`.
- [X] T015 Implement the renderer registry scaffold + labeled-placeholder fallback (FR-005) + the Compose canvas host (children keyed by `component_id`, applies `CanvasOp` in place) in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/render/Registry.kt` and `.../render/CanvasHost.kt`.
- [X] T016 Implement the app shell + ViewModel (connect on launch, observe inbound `Flow` → chat/canvas state, dispatch `ui_event`) in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/MainActivity.kt` and `.../ui/AppViewModel.kt`.
- [X] T017 [P] Server: add an `android` value to `DeviceType` + a full-capability `_BASE_HOST_CONFIG["android"]` entry (mirroring `windows`) in `backend/rote/capabilities.py`.
- [X] T018 [P] Server: Python unit tests for the `android` ROTE profile (device_type → full-capability profile; `supported_types` honored) in `backend/rote/tests/test_android_profile.py`.

**Checkpoint**: A token can register, frames decode, and a component renders/updates in the canvas — stories can begin.

---

## Phase 3: User Story 1 - Sign in and converse on a phone (Priority: P1) 🎯 MVP

**Goal**: Real Keycloak sign-in + chat round-trip rendered as native UI on a phone.

**Independent Test**: On a phone, complete OIDC sign-in, send a message, see a native-rendered response (no web view).

- [X] T019 [P] [US1] Implement OIDC Authorization-Code + PKCE via AppAuth (discovery from the authority, login in a Custom Tab against `astral-mobile`, redirect `com.kyopenscience.astral:/oauth2redirect`, code→token exchange) in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/auth/OidcAuth.kt`.
- [X] T020 [P] [US1] Implement the encrypted refresh-token store + silent refresh + sign-out (AndroidX Security/DataStore) in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/auth/TokenStore.kt`.
- [X] T021 [US1] Wire auth into the transport: real bearer in `register_ui`; `auth_required` → silent re-auth then reconnect; "no access" role → clear message (FR-001) in `.../app/transport/OrchestratorClient.kt` + `.../app/auth/`.
- [X] T022 [P] [US1] Debug-only dev-token path (`BuildConfig.DEBUG`-gated, absent from release per FR-002) in `android-client/app/src/debug/kotlin/com/kyopenscience/astral/app/auth/DevAuth.kt`.
- [X] T023 [P] [US1] Basic Composable renderers (`text`, `card`, `container`, `alert`, `button`) registered in the registry in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/render/renderers/Basic.kt`.
- [X] T024 [US1] Chat screen: input + send (`ui_event chat_message`), user/assistant text turns, `chat_status` indicator, `chat_created` active-chat in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/ui/ChatScreen.kt`.
- [X] T025 [US1] Render `ui_render` (target canvas/chat) + `ui_upsert` into the canvas with the basic vocabulary in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/ui/CanvasView.kt`.
- [X] T026 [P] [US1] JVM unit tests: token store + auth config; the `register_ui` device-caps builder (`device_type=android`, screen, `supported_types`) in `android-client/app/src/test/kotlin/com/kyopenscience/astral/app/auth/TokenStoreTest.kt` and `.../transport/DeviceCapsTest.kt`.
- [ ] T027 [US1] Compose UI test: a signed-in chat round-trip renders a basic response natively in `android-client/app/src/androidTest/kotlin/com/kyopenscience/astral/app/ChatRenderTest.kt`.

**Checkpoint**: MVP — sign in, chat, basic native rendering all work independently.

---

## Phase 4: User Story 2 - Full rich-UI parity with live updates (Priority: P2)

**Goal**: The full primitive vocabulary renders natively; streaming updates in place; unknown types → placeholder.

**Independent Test**: Trigger rich + streaming responses; each renders natively, streams update in place, an unknown type shows a placeholder.

- [X] T028 [P] [US2] Port the streaming consumer (`streamFrameToOps`/`subscribeAckOps`/`streamErrorOps`: session filter, monotonic seq dedupe, terminal final/forget, error→alert; render `components`, ignore `html`) per research D4 in `android-client/core/src/main/kotlin/com/kyopenscience/astral/core/streaming/Streaming.kt`.
- [X] T029 [P] [US2] Unit tests for the streaming consumer (mirror the Windows `test_streaming.py` cases) in `android-client/core/src/test/kotlin/com/kyopenscience/astral/core/streaming/StreamingTest.kt`.
- [X] T030 [US2] Dispatch `ui_stream_data`/`stream_subscribed`/`stream_error`/`stream_unsubscribed` in the transport and bind ops to the canvas; subscribe via `ui_event stream_subscribe` in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/stream/StreamController.kt`.
- [X] T031 [P] [US2] Layout/content renderers (`grid`, `hero`, `badge`, `metric`, `keyvalue`, `timeline`, `rating`, `divider`, `progress`, `collapsible`) in `.../app/render/renderers/Layout.kt`.
- [X] T032 [P] [US2] Data renderers (`list`, `table`, `tabs`, `chat_history`, `skeleton`) virtualized via `LazyColumn` in `.../app/render/renderers/Data.kt`.
- [X] T033 [P] [US2] Input/code/file renderers (`input`, `param_picker`, `code`, `file_upload`, `file_download`/`download_card`) in `.../app/render/renderers/Input.kt`.
- [X] T034 [P] [US2] Chart renderers (`bar_chart`/`line_chart`/`pie_chart` via Compose Canvas) + `image` (Coil) in `.../app/render/renderers/Charts.kt` and `.../render/renderers/Media.kt`.
- [X] T035 [US2] Advertise the native `supported_types` in `register_ui` device caps (exclude `plotly_chart`/`audio`/`color_picker`/`theme_apply`/`generative` → placeholder) in `.../app/transport/DeviceCaps.kt`.
- [X] T036 [P] [US2] Vocabulary-parity test: advertised `supported_types` ⊆ `webrender.allowed_primitive_types()` and every advertised type has a renderer (mirror the Windows drift guard) in `android-client/app/src/test/kotlin/com/kyopenscience/astral/app/render/VocabularyParityTest.kt`.
- [ ] T037 [US2] Compose UI tests: each renderer group, unknown-type placeholder (FR-005), and streaming in-place update in `android-client/app/src/androidTest/kotlin/com/kyopenscience/astral/app/RenderersTest.kt` and `.../StreamingUiTest.kt`.

**Checkpoint**: Rich responses + live streaming render natively; US1 still works.

---

## Phase 5: User Story 3 - Adapt fluidly across all screen sizes (Priority: P2)

**Goal**: One layout reflows across phone/tablet/foldable (two-pane ↔ stacked) preserving state.

**Independent Test**: Run the same build on phone + tablet/foldable (or resize); layout adapts with no clipping/horizontal scroll, state preserved.

- [ ] T038 [US3] Adaptive scaffold via `WindowSizeClass`: Compact → stacked/navigable (chat ↔ canvas); Medium/Expanded → two-pane (chat rail + canvas) in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/ui/AdaptiveScaffold.kt`.
- [ ] T039 [US3] Preserve conversation + scroll position across rotation/fold/split (`rememberSaveable` + ViewModel) in `.../app/ui/AdaptiveScaffold.kt` and `.../ui/AppViewModel.kt`.
- [ ] T040 [P] [US3] Compose UI tests: Compact vs Expanded layout selection + state preserved across a configuration change in `android-client/app/src/androidTest/kotlin/com/kyopenscience/astral/app/AdaptiveLayoutTest.kt`.

**Checkpoint**: The same build adapts across screen sizes; US1/US2 still work.

---

## Phase 6: User Story 4 - Manage agents, history, and audit natively (Priority: P3)

**Goal**: Native agents/permissions, history, and audit screens driven by existing data actions/REST.

**Independent Test**: Toggle an agent + a permission, reopen a past chat, page/filter the personal audit log.

- [ ] T041 [P] [US4] Port REST shaping (`auditUrl`, `parseAuditResponse`, `RestError`) per contracts/rest-endpoints.md in `android-client/core/src/main/kotlin/com/kyopenscience/astral/core/rest/Audit.kt`.
- [ ] T042 [P] [US4] Unit tests for REST shaping (mirror the Windows `test_rest.py` cases) in `android-client/core/src/test/kotlin/com/kyopenscience/astral/core/rest/AuditTest.kt`.
- [ ] T043 [P] [US4] Authenticated REST client (OkHttp + `Bearer`) with background fetch → UI state in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/rest/RestClient.kt`.
- [ ] T044 [US4] Agents screen (`discover_agents`→`agent_list`; `enable_recommended_agents`; `set_agent_permissions`; per-tool toggles) in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/ui/AgentsScreen.kt`.
- [ ] T045 [US4] History screen (`get_history`→`history_list`; `load_chat`→`chat_loaded` replay) in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/ui/HistoryScreen.kt`.
- [ ] T046 [US4] Audit screen (GET `/api/audit`; `event_class`/`outcome`/`q` filters; cursor "load more"; outcome colour; user-scoped) in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/ui/AuditScreen.kt`.
- [ ] T047 [P] [US4] `chrome_render` acknowledge (no web embed; native notice — FR-013) in `android-client/app/src/main/kotlin/com/kyopenscience/astral/app/stream/ChromeRender.kt`.
- [ ] T048 [US4] Compose UI tests: agent toggle, history reopen, audit list + filter + paging in `android-client/app/src/androidTest/kotlin/com/kyopenscience/astral/app/SurfacesTest.kt`.

**Checkpoint**: All four stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T049 Reconnect + re-auth resilience (FR-012): disconnected state, auto-reconnect, no duplicate sends, no lost input — harden `.../app/transport/OrchestratorClient.kt` + add tests.
- [ ] T050 [P] Structured logging/observability for connect/auth/render failures (Principle X) across `.../app/`.
- [ ] T051 [P] KDoc on public `:core` + `:app` APIs (Constitution VI).
- [ ] T052 [P] Document the `astral-mobile` azp in `.env.example` and write `docs/keycloak-android-client-setup.md` (public client, PKCE S256, redirect `com.kyopenscience.astral:/oauth2redirect`, post-logout = redirect/`+`, web-origins blank).
- [ ] T053 Finalize `.github/workflows/android-ci.yml` (`:core:test` + `:app:testDebugUnitTest` + `koverVerify` ≥90% + ktlint + `lintDebug` + `:app:assembleDebug` + APK artifact; optional nightly emulator job for instrumented tests).
- [ ] T054 [P] Write `android-client/README.md` (architecture, real-Keycloak run, debug-token, tests, CI) per Constitution VI.
- [ ] T055 On-device/emulator verification of the quickstart acceptance smoke (SC-001…SC-006) — Constitution X release gate; run where the Android SDK/emulator or a device is available.
- [ ] T056 PR housekeeping: document the Android dependency set + record lead-dev approval (Principle V gate) and the Principle XI CI carve-out in the PR description.

---

## Dependencies & Execution Order

- **Setup (P1)**: T001 first; T002–T007 depend on T001 (T002–T006 are [P]).
- **Foundational (P2)**: depends on Setup. `:core` tasks T008/T009/T011/T012 [P]; their tests T010/T013 [P]. T014 (transport) depends on T008/T009; T015 (registry/canvas) depends on T011/T012; T016 (shell) depends on T014/T015. Server T017/T018 [P], independent of the Kotlin tasks. **Blocks all user stories.**
- **US1 (P3 phase)**: depends on Foundational. T019/T020/T022/T023/T026 [P]; T021 depends on T014+T019/T020; T024/T025 depend on T015/T016/T023; T027 depends on the US1 UI.
- **US2**: depends on Foundational (+ basic render from US1 helps but not required). T028/T029/T031/T032/T033/T034/T036 [P]; T030 depends on T028+T014; T035 depends on the renderers; T037 depends on the renderers + T030.
- **US3**: depends on Foundational + a chat/canvas surface (US1). T038 → T039 → T040.
- **US4**: depends on Foundational + auth (US1, for the bearer). T041/T042/T043/T047 [P]; T044/T045/T046 depend on T043 (+ T041 for audit); T048 depends on the screens.
- **Polish (P7)**: after the targeted stories.

### Parallel opportunities

- Setup: T002–T006 in parallel after T001.
- Foundational: all `:core` model/test tasks (T008–T013) and the server profile (T017/T018) in parallel; transport/registry/shell (T014–T016) follow.
- Within US2: every renderer-group task (T031–T034) + the streaming port (T028/T029) + the parity test (T036) run in parallel.
- Across stories: once Foundational is done, US1/US2/US4 can be staffed in parallel (US3 wants a US1 surface to adapt).

---

## Implementation Strategy

### MVP (User Story 1)
1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 → **STOP & validate**: sign in + chat + basic native render on a phone (SC-001). Demoable MVP.

### Incremental delivery
- + US2 (rich vocabulary + streaming) → validate (SC-002/SC-003).
- + US3 (adaptive) → validate on tablet/foldable (SC-004).
- + US4 (agents/history/audit) → validate (SC-005/SC-007).
- Polish → CI green + on-device smoke (SC-006) → release-ready.

### Notes
- Tests requested (FR-016): `:core` pure logic is fully JVM-unit-tested (no emulator); Compose UI tests cover renderers/screens; Kover gates ≥90% changed-code. Per Constitution X, final correctness needs an on-device/emulator pass (T055) — necessary beyond unit + build.
- The `:core` streaming/REST ports reuse the Windows client's verified logic + test cases to guarantee parity.
- Server delta is only T017/T018 (`android` ROTE profile) + T052 docs + T053 CI; the `astral-mobile` azp is already provisioned + allow-listed (operator) — pending only the Android redirect URI on that client.
- [P] = different files, no incomplete-task dependency. Commit after each task or logical group.
