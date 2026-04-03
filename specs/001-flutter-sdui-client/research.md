# Research: Flutter SDUI Thin Client

**Branch**: `001-flutter-sdui-client` | **Date**: 2026-04-03

## R1: Protocol Adaptation Strategy

**Decision**: Rewrite the Flutter WebSocket provider to speak the AstralBody backend protocol natively. No backend protocol changes.

**Rationale**: The backend protocol (`register_ui`, `ui_event`, `ui_render`, `ui_update`, `ui_append`) is well-defined in `backend/shared/protocol.py` and already handles device profiles via ROTE. Adapting the Flutter client is cheaper and safer than modifying the backend protocol that all agents depend on.

**Alternatives considered**:
- Backend protocol adapter layer — rejected because it adds complexity and maintenance burden to the backend, and the user specified backend should not change unless necessary.
- Bidirectional protocol negotiation — rejected as overengineered for a single-client system.

**Implementation approach**:
1. `WebSocketProvider.connect()` sends `register_ui` (not `register_capabilities`) with device info, session_id, and JWT token
2. Handle incoming `ui_render` → set full component tree state
3. Handle incoming `ui_update` → replace components in tree
4. Handle incoming `ui_append` → append to target component
5. User interactions send `ui_event` (not `ui_action`) with action/payload

---

## R2: Component Type Mapping

**Decision**: Map AstralBody backend snake_case types directly to Flutter widgets. No intermediate translation layer.

**Rationale**: The backend `primitives.py` defines 23 component types with stable schemas. Direct mapping in the `primitiveMap` is the simplest approach and avoids an unnecessary abstraction layer.

**Type mapping** (backend → Flutter widget class):

| Backend Type | Flutter Widget | Status |
|---|---|---|
| `container` | `ContainerWidget` | New |
| `text` | `TextWidget` | Adapt from TextView |
| `button` | `ButtonWidget` | Adapt |
| `input` | `InputWidget` | Adapt from InputField |
| `card` | `CardWidget` | Adapt |
| `table` | `TableWidget` | New |
| `list` | `ListWidget` | New |
| `alert` | `AlertWidget` | New |
| `progress` | `ProgressWidget` | New |
| `metric` | `MetricWidget` | New |
| `code` | `CodeWidget` | Adapt from CodeView |
| `image` | `ImageWidget` | New |
| `grid` | `GridWidget` | New |
| `tabs` | `TabsWidget` | New |
| `divider` | `DividerWidget` | New |
| `collapsible` | `CollapsibleWidget` | New |
| `bar_chart` | `BarChartWidget` | New |
| `line_chart` | `LineChartWidget` | New |
| `pie_chart` | `PieChartWidget` | New |
| `plotly_chart` | `PlotlyChartWidget` | New |
| `color_picker` | `ColorPickerWidget` | New |
| `file_upload` | `FileUploadWidget` | Adapt |
| `file_download` | `FileDownloadWidget` | New |

**Alternatives considered**:
- Intermediate ComponentModel Dart class hierarchy mirroring Python dataclasses — rejected because the dynamic renderer already works with `Map<String, dynamic>` and adding typed models adds boilerplate without benefit for a pure renderer.

---

## R3: Charting Library for Flutter

**Decision**: Use `fl_chart` for bar, line, and pie charts. Use `flutter_inappwebview` for Plotly charts on capable devices; fall back to static metric display on watch/TV.

**Rationale**: `fl_chart` is the most popular pure-Dart charting library (6k+ GitHub stars), supports bar/line/pie natively, renders at 60fps, and has no platform channel dependencies. Plotly requires a JavaScript runtime, so WebView is the only viable option on mobile/tablet; watch and TV cannot run WebViews.

**Alternatives considered**:
- `syncfusion_flutter_charts` — rejected due to commercial license requirements.
- `graphic` — rejected as less mature, smaller community.
- Custom Canvas painters — rejected as excessive development effort.
- Converting all Plotly to fl_chart on client — rejected because Plotly figures can have complex configs that don't map cleanly.

---

## R4: Keycloak OIDC in Flutter

**Decision**: Use `flutter_appauth` for native OIDC code flow, with backend BFF proxy at `/auth/token` for token exchange.

**Rationale**: `flutter_appauth` wraps the AppAuth SDK (iOS/Android native), supports PKCE, custom schemes, and is the recommended approach for mobile OIDC. The backend's existing BFF proxy (`/auth/token`) injects `client_secret` server-side, so the Flutter client never handles the secret.

**Flow**:
1. Flutter calls Keycloak authorize endpoint via `flutter_appauth` → user authenticates in system browser
2. Flutter receives authorization code
3. Flutter POSTs code to backend `/auth/token` (BFF proxy)
4. Backend appends `client_secret`, exchanges code at Keycloak
5. Backend returns JWT to Flutter
6. Flutter stores JWT in secure storage, sends in `register_ui`

**Alternatives considered**:
- `openid_client` (pure Dart) — viable but lacks native browser integration, worse UX on mobile.
- Direct Keycloak token endpoint from client — rejected because it requires exposing client_secret.
- Keep basic auth — rejected because it violates constitution principle VII (Keycloak required).

**Mock auth**: Retain `VITE_USE_MOCK_AUTH` equivalent (`MOCK_AUTH=true` env var) for local development. When enabled, skip OIDC flow and use hardcoded test credentials against `/auth/login`.

**Keycloak test auth**: For integration/E2E tests against real Keycloak, credentials are read from environment variables `KEYCLOAK_TEST_USER` and `KEYCLOAK_TEST_PASSWORD` (set in `.env`, never committed to source).

---

## R5: Apple Watch Support Strategy

**Decision**: Build a native watchOS companion app using SwiftUI that communicates with the AstralBody backend via the same WebSocket protocol. The watch app implements the watch-subset of SDUI renderers natively.

**Rationale**: Flutter does not officially support watchOS. The screen is too small (< 200px) for Flutter's rendering engine overhead. Native SwiftUI is the standard approach for watchOS development and provides the best UX for glanceable interactions.

**Watch-supported SDUI components** (per backend ROTE watch profile):
- `text` (max 120 chars)
- `metric` (key-value display)
- `alert` (info/warning/error)
- `card` (container with title)
- `button` (primary only)

**Communication**:
- Watch establishes its own WebSocket to backend
- Sends `register_ui` with `device_type: "watch"`, viewport ~200px
- Backend ROTE sends watch-adapted component trees
- Unsupported components gracefully omitted by ROTE adapter

**Alternatives considered**:
- Flutter web in WKWebView on watch — rejected due to performance and screen constraints.
- Wear OS only (skip Apple Watch) — rejected because user explicitly requested Apple Watch.
- WatchConnectivity (relay through iPhone) — considered as enhancement but direct WebSocket is simpler for MVP.

---

## R6: TV Platform Support

**Decision**: Use Flutter's existing Android TV support for Android TV. For tvOS, use Flutter with tvOS target. Both share the same codebase with a TV-specific focus management layer.

**Rationale**: Flutter supports Android TV natively, and community support for tvOS exists. The key challenge is focus-based navigation (D-pad/remote), which Flutter handles via `FocusTraversalGroup`, `FocusNode`, and `Shortcuts` widgets.

**TV adaptations**:
- `TvFocusManager` widget wraps the root and manages D-pad navigation
- All interactive widgets (`button`, `input`, `tabs`) get `FocusNode` + visual focus indicator
- Text scaled up (1.5x base), spacing increased for 10-foot viewing
- File upload/download disabled (per ROTE TV profile)
- Buttons removed on TV (per ROTE adapter — this may need discussion, as TV users do interact via remote select)

**Backend consideration**: The ROTE adapter currently removes buttons on TV (`_adapt_button` returns None for TV). This may need a minor backend change to allow primary buttons on TV since users can select with the remote. **This is the one potential backend change needed.**

**Alternatives considered**:
- Separate native TV apps (Kotlin/Swift) — rejected due to code duplication.
- Web app on TV browser — rejected due to poor TV browser support.

---

## R7: Archiving the React Frontend

**Decision**: Move `frontend/` to `frontend-archive-react/` and update the Dockerfile to remove the frontend build stage.

**Rationale**: Preserves the React code for reference while clearly marking it as archived. The Dockerfile should be updated to serve Flutter web builds (or removed if the Flutter app is distributed as native binaries only).

**Steps**:
1. `git mv frontend/ frontend-archive-react/`
2. Remove Stage 1 (frontend-builder) from Dockerfile
3. Update docker-compose.yml to remove port 5173 (or repurpose for Flutter web)
4. Remove React-specific test configuration (vitest, etc.)
5. Remove frontend/ references from CLAUDE.md

**Alternatives considered**:
- Delete frontend entirely — rejected because historical reference is valuable.
- Keep frontend alongside Flutter — rejected because it creates confusion about which is active.

---

## R8: Backend Test Impact Analysis

**Decision**: Update backend tests that reference React-specific concepts. No backend test removal.

**Rationale**: The 25 backend test files primarily test backend logic (orchestrator, agents, auth, security, database). Only tests that explicitly test React frontend behavior or import frontend-specific expectations need updating.

**Backend tests analysis**:

| Test File | Impact | Action |
|---|---|---|
| `test_backend.py` | Low — tests orchestrator logic | Keep, verify WebSocket handshake tests still pass |
| `test_rest_api.py` | None — tests REST endpoints | Keep unchanged |
| `test_mock_auth.py` | Low — tests auth flow | Update if auth endpoint changes |
| `test_navigation_flow.py` | Medium — may test UI interaction patterns | Review and update for Flutter protocol |
| `test_progress_system.py` | None — tests agent progress | Keep unchanged |
| `test_tool_permissions.py` | None — tests delegation | Keep unchanged |
| `test_delegation.py` | None — tests agent delegation | Keep unchanged |
| `test_nefarious_delegation.py` | None — tests security | Keep unchanged |
| `test_file_security.py` | None — tests file isolation | Keep unchanged |
| `test_session_isolation_integration.py` | Low — tests multi-user | Keep, may need protocol update |
| `test_database.py` | None — tests PostgreSQL | Keep unchanged |
| All others | None | Keep unchanged |

---

## R9: Flutter Test Strategy Across Devices

**Decision**: Three-tier test structure: unit tests, widget tests (per primitive per device profile), and integration tests (per device form factor).

**Rationale**: Unit tests validate state management and protocol logic. Widget tests validate each SDUI primitive renders correctly given mock data, parameterized by device profile. Integration tests validate the full flow (connect → render → interact → re-render) per device.

**Test matrix**:

| Test Level | Scope | Tool | Count Estimate |
|---|---|---|---|
| Unit | WebSocket provider, auth, device profile, dynamic renderer | `flutter_test` | ~15 tests |
| Widget | Each of 23 primitives × {phone, tablet, TV} profiles | `flutter_test` | ~70 tests |
| Widget | Watch subset (5 primitives) | `flutter_test` | ~10 tests |
| Widget | Unknown component placeholder | `flutter_test` | ~3 tests |
| Integration | Phone end-to-end flow | `integration_test` | ~5 tests |
| Integration | Tablet layout adaptation | `integration_test` | ~3 tests |
| Integration | TV focus navigation | `integration_test` | ~5 tests |
| Integration | Watch glanceable rendering | `integration_test` | ~3 tests |
| Integration | WebSocket reconnect | `integration_test` | ~3 tests |

**Total**: ~115+ tests targeting 90%+ coverage.

---

## R10: Existing Flutter Code Reuse Assessment

**Decision**: Reuse the Flutter project scaffold, Provider architecture, and theme system. Rewrite WebSocket provider, auth provider, and dynamic renderer. Adapt existing primitives where possible.

**Rationale**: The `astralprojection-flutter` project has solid foundations (Provider state management, responsive themes, primitive rendering pattern) but was built against a different backend protocol. The rendering pattern (primitiveMap + DynamicRenderer) is sound and should be preserved with new type mappings.

**Reuse assessment**:

| Component | Reuse Level | Notes |
|---|---|---|
| `main.dart` | High | Keep as-is, minor config changes |
| `app.dart` | High | Add new providers (DeviceProfile) |
| `config.dart` | High | Point to AstralBody backend |
| `auth_provider.dart` | Low — rewrite | Replace basic auth with Keycloak OIDC |
| `web_socket_provider.dart` | Low — rewrite | New protocol (register_ui, ui_render) |
| `project_provider.dart` | Medium | Update API paths |
| `dynamic_renderer.dart` | Medium — rewrite map | Same pattern, new type keys + more primitives |
| `workspace_layout.dart` | Medium | Update for new protocol |
| `app_theme.dart` | High | Add TV/watch theme variants |
| `nav_bar.dart` | Medium | Responsive for TV/watch |
| Existing primitives (16) | Low-Medium | Adapt schemas, rename types |
| `login_page.dart` | Low — rewrite | Keycloak OIDC flow |
