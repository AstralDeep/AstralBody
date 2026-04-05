# Research: Flutter Migration QA & Feature Parity

**Branch**: `002-flutter-migration-qa` | **Date**: 2026-04-03

## R1: Keycloak OIDC Integration in Flutter

### Context
The Flutter client's `login_page.dart` has a TODO for `flutter_appauth` OIDC integration. Currently, when `MOCK_AUTH=false`, it shows only a "Sign in with Keycloak" button that doesn't work. The spec requires both a username/password form AND an SSO button on the same login screen.

### Decision: Use `flutter_appauth` for OIDC code flow + BFF token proxy

### Rationale
- `flutter_appauth` (v8.0.1) is already in `pubspec.yaml` — no new dependency needed
- The React frontend uses `oidc-client-ts` with authorization code + PKCE flow, exchanging tokens via BFF at `/auth/token`
- The backend `auth.py` BFF proxy injects `KEYCLOAK_CLIENT_SECRET` server-side, so the Flutter client never needs the secret
- `flutter_appauth` supports `authorizeAndExchangeCode` which handles the system browser redirect + code exchange in one call

### Configuration Required
- **Keycloak Authority**: `https://iam.ai.uky.edu/realms/Astral` (from `.env` `VITE_KEYCLOAK_AUTHORITY`)
- **Client ID**: `astral-frontend` (from `.env` `VITE_KEYCLOAK_CLIENT_ID`)
- **Token Endpoint**: Override to `{BACKEND_HOST}:{BACKEND_PORT}/auth/token` (BFF proxy)
- **Scopes**: `openid profile email offline_access` (matching React)
- **Redirect URI**: Platform-specific deep link (e.g., `com.astraldeep.app://callback`)

### Alternatives Considered
- **Direct Keycloak token endpoint**: Rejected — would expose client secret to the mobile app
- **Resource Owner Password Credentials (ROPC) grant**: Rejected — deprecated by OAuth 2.1, Keycloak may not enable it for the client
- **Custom WebView auth**: Rejected — `flutter_appauth` uses system browser which is more secure (shared cookies, password managers)

### Implementation Notes
- The login page must show BOTH forms simultaneously (not toggle between them)
- Username/password form submits to `/auth/login` (mock auth endpoint) when mock auth is enabled, or could use ROPC if the Keycloak client supports it
- SSO button triggers `flutter_appauth` authorization code flow
- After successful OIDC, extract JWT claims for user profile (sub, preferred_username, realm_access.roles)
- Store tokens in `flutter_secure_storage`, restore on app restart

---

## R2: Login Screen — Dual Auth Mode

### Context
The spec (FR-001) requires the login screen to display BOTH username/password form AND SSO button. The React login (`LoginScreen.tsx`) shows this layout with glass-morphism styling. The current Flutter login toggles between mock (form) and OIDC (button only).

### Decision: Always show both auth methods regardless of MOCK_AUTH setting

### Rationale
- Users need flexibility — some prefer SSO, others have local credentials
- The React reference shows both options on a single screen
- `MOCK_AUTH` should only control whether auth validation hits the real Keycloak or a mock endpoint, not the UI layout

### Implementation Notes
- Login page layout: AstralDeep branding → username/password form → "OR" divider → "Sign in with SSO" button
- When `MOCK_AUTH=true`: password form hits `/auth/login`; SSO button triggers mock OIDC flow
- When `MOCK_AUTH=false`: password form uses ROPC if available OR shows error directing to SSO; SSO button triggers real `flutter_appauth` flow
- Test using `KEYCLOAK_TEST_USER` / `KEYCLOAK_TEST_PASSWORD` from `.env`

---

## R3: Feature Parity Gap Analysis (React vs Flutter)

### Context
Side-by-side analysis of the archived React frontend and current Flutter client to identify missing features.

### Decision: Prioritize gaps by user impact and spec requirements

### Gap Analysis

| Feature | React Status | Flutter Status | Gap | Priority |
|---------|-------------|---------------|-----|----------|
| Login (username/password) | ✓ Mock auth form | ✓ Mock auth form | None (mock mode) | — |
| Login (Keycloak OIDC) | ✓ oidc-client-ts | ✗ TODO placeholder | **CRITICAL** | P1 |
| Login (dual form) | ✓ Both shown | ✗ Toggle mode | **FIX** | P1 |
| Sidebar (chat history) | ✓ Collapsible | Partial — needs verification | Verify | P1 |
| Sidebar (agent list) | ✓ Status indicators | Partial — needs verification | Verify | P1 |
| Chat (real-time SDUI) | ✓ Full | ✓ Full | None | — |
| Chat (file upload) | ✓ Drag+click | ✓ Click (file_picker) | Missing drag-and-drop | P2 |
| Chat (voice input/STT) | ✓ PCM16 streaming | ✗ Missing | **CRITICAL** | P1 |
| Chat (voice output/TTS) | ✓ Audio playback | ✗ Missing | **CRITICAL** | P1 |
| Chat (geolocation) | ✓ Silent capture | ✗ Missing | **GAP** | P2 |
| Chat (markdown + LaTeX) | ✓ remark-math+rehype-katex | ✓ flutter_markdown (no LaTeX) | Missing LaTeX | P2 |
| Saved components (save) | ✓ Full | Partial — needs verification | Verify | P1 |
| Saved components (combine DnD) | ✓ HTML5 DnD | ✗ Missing | **GAP** | P1 |
| Saved components (condense) | ✓ Full | ✗ Missing | **GAP** | P1 |
| Agent permissions modal | ✓ 4-scope UI | ✗ Missing | **GAP** | P1 |
| Agent credentials | ✓ Store/OAuth/delete | ✗ Missing | **GAP** | P2 |
| Draft agent management | ✓ Create/resume | ✗ Missing | **GAP** | P3 |
| Theme presets | ✓ 5 themes | ✓ Backend theme | Different approach (OK) | — |
| Connection status | ✓ Indicator | ✓ OfflineIndicator | None | — |
| Auto-reconnect | ✓ Exponential backoff | ✓ Exponential backoff | None | — |
| SDUI tree cache | ✗ Not implemented | ✓ SharedPreferences | Flutter ahead | — |
| TV D-pad navigation | N/A (browser) | ✓ TvFocusManager | Flutter ahead | — |
| Watch degradation | N/A (browser) | ✓ WatchRenderer | Flutter ahead | — |
| Glass-morphism styling | ✓ Tailwind glass classes | Needs verification | Verify | P1 |

### Alternatives Considered
- **Skip voice I/O**: Rejected — FR-010 explicitly requires it; React has full implementation
- **Skip geolocation**: Could defer to P2 but FR-020 requires capability gating
- **Skip LaTeX**: Could defer — nice-to-have for academic use case

---

## R4: Voice Input/Output Implementation in Flutter

### Context
The React frontend streams PCM16 audio at 24kHz to `/api/voice/stream` for STT and plays TTS audio responses. The backend has a SPEACHES_URL (`http://128.163.202.61:4958`) for speech services.

### Decision: Use `just_audio` (already in pubspec) for TTS playback + platform audio recording for STT

### Rationale
- `just_audio` (v0.10.4) is already a dependency — supports audio playback for TTS
- For STT recording, need a recording package. `record` or `flutter_sound` are common choices
- The React implementation downsamples from 48kHz to 24kHz and streams PCM16 via WebSocket
- Flutter equivalent: capture audio → downsample → stream via WebSocket to `/api/voice/stream`

### Implementation Notes
- **STT**: New `voice_input_service.dart` — open WebSocket to `/api/voice/stream`, stream PCM16 chunks, receive transcript
- **TTS**: New `voice_output_service.dart` — receive audio URL from backend, play via `just_audio`
- **Capability gating**: Hide voice controls on TV (no microphone), show on phone/tablet
- **New dependency needed**: Audio recording package (e.g., `record` ^5.x) — must be documented per Constitution V

### Alternatives Considered
- **Browser-based Web Speech API**: Not available in native Flutter
- **Platform channels**: Too complex; existing packages handle this well
- **Skip streaming, use batch**: Worse UX — React streams for real-time transcript

---

## R5: Saved Component Workflows (Combine/Condense)

### Context
The React frontend has a `UISavedDrawer.tsx` (400+ lines) implementing drag-and-drop combining and "condense all" functionality. The Flutter client has `save_component` support via WebSocket but no combine/condense UI.

### Decision: Implement drag-and-drop combine + condense using Flutter's built-in `Draggable`/`DragTarget` widgets

### Rationale
- Flutter's `LongPressDraggable` + `DragTarget` widgets provide native DnD without additional packages
- The backend already handles `combine_components` and `condense_components` WebSocket messages
- The Flutter `WebSocketProvider` already dispatches `components_combined` and `components_condensed` server messages

### Implementation Notes
- New `saved_components_drawer.dart` widget
- Grid layout of saved component cards (responsive to form factor)
- Long-press to start drag → drop on target → send `combine_components` message
- "Condense All" button → send `condense_components` with all component IDs
- Full-screen inspect mode for individual components
- Delete button per component

### Alternatives Considered
- **Third-party DnD package**: Unnecessary — Flutter built-in is sufficient
- **Skip DnD, use selection mode**: Worse UX — React users expect drag-and-drop

---

## R6: Agent Permissions Modal

### Context
The React frontend has a comprehensive `AgentPermissionsModal.tsx` (300+ lines) with 4 scope categories (tools:read, tools:write, tools:search, tools:system), per-tool overrides, and credential management. This is entirely missing from the Flutter client.

### Decision: Implement as a bottom sheet modal with scope cards and expandable tool lists

### Rationale
- Bottom sheet is idiomatic for mobile (vs modal dialog in React web)
- Scope cards with color coding (green/amber/blue/purple) match React design
- Per-tool toggle switches for granular control
- Backend already sends agent permissions in `system_config` and accepts permission updates

### Implementation Notes
- New `agent_permissions_sheet.dart`
- 4 scope cards: read (green), write (amber), search (blue), system (purple)
- Each scope expandable to show tools with toggle switches
- Confirmation dialog for scope changes (matching React)
- Credential section for agents with `required_credentials`

---

## R7: Test Credentials & Environment Configuration

### Context
The user requires using `.env` credentials to test the full auth flow. The `.env` file contains:
```
KEYCLOAK_TEST_USER=test_user
KEYCLOAK_TEST_PASSWORD='hJ.3w}Hs)agaKmvtk6qps4)z!J~Ae!%)b^7HEBHpDhi-LM.4V@wWoqF:mYp0ZjaiK=d.VR2fJV0+M*pwK}dum890UgdMx14%s6+c'
VITE_KEYCLOAK_AUTHORITY=https://iam.ai.uky.edu/realms/Astral
VITE_KEYCLOAK_CLIENT_ID=astral-frontend
KEYCLOAK_CLIENT_SECRET=9nXTyUjjS4t5pKvLH1AQAmGJC8yBx0JK
AGENT_SERVICE_CLIENT_ID=astral-agent-service
AGENT_SERVICE_CLIENT_SECRET=yN1dTmpoWp9ocdygQ5BoNbaZu2C4jomC
```

### Decision: Pass test credentials via `--dart-define` at build time; never embed in source

### Rationale
- Constitution VII prohibits secrets in version control
- Flutter's `String.fromEnvironment()` reads compile-time `--dart-define` values
- Test scripts can read `.env` and pass values to `flutter test` / `flutter run`

### Implementation Notes
- Integration tests use: `flutter test --dart-define=KEYCLOAK_TEST_USER=test_user --dart-define=KEYCLOAK_TEST_PASSWORD=...`
- Alternatively, a test helper reads `.env` from the AstralBody repo path at runtime (for integration tests only)
- Backend `.env` is the single source of truth for all credentials
- Agent auth testing: `AGENT_SERVICE_CLIENT_ID` + `AGENT_SERVICE_CLIENT_SECRET` for RFC 8693 token exchange

---

## R8: Multi-Device Testing Strategy

### Context
The spec requires testing on: iOS phone, Android phone, iOS tablet, Android tablet, Apple TV, Android TV, Apple Watch. Physical devices may not all be available.

### Decision: Use emulators/simulators for all form factors; physical device testing where available

### Rationale
- Flutter's `DeviceProfileProvider` detects form factor from viewport width — emulators exercise the same code paths
- TV emulators (Android TV) support D-pad input simulation
- Apple Watch requires watchOS simulator (Xcode only)
- Integration tests can override `MediaQuery` to simulate any viewport size

### Test Matrix

| Device | Method | Viewport | Key Validations |
|--------|--------|----------|-----------------|
| iPhone 15 | iOS Simulator | 393×852 | Login, chat, SDUI, voice, file upload |
| Pixel 8 | Android Emulator | 412×915 | Login, chat, SDUI, voice, file upload |
| iPad Pro 12.9" | iOS Simulator | 1024×1366 | Persistent sidebar, landscape layout |
| Galaxy Tab S9 | Android Emulator | 800×1280 | Sidebar, tablet grid layout |
| Apple TV 4K | tvOS Simulator | 1920×1080 | D-pad nav, TV fonts, no file/voice |
| Android TV | Android TV Emulator | 1920×1080 | D-pad nav, TV theme |
| Apple Watch S9 | watchOS Simulator | 205×251 | Glanceable metrics, component degradation |

### Alternatives Considered
- **Physical devices only**: Not practical — Apple Watch/TV may not be available
- **Widget tests only**: Insufficient — need real rendering for visual parity
- **Golden file tests**: Good complement but not substitute for runtime testing

---

## R9: Visual Parity — Glass-Morphism & Branding

### Context
The React frontend uses Tailwind glass-morphism classes (`bg-surface/60 backdrop-blur-md border-white/10`), AstralDeep branding, and a dark navy color scheme. The Flutter client needs to match.

### Decision: Implement glass-morphism via `BackdropFilter` + semi-transparent containers in Flutter

### Rationale
- Flutter's `BackdropFilter` with `ImageFilter.blur()` provides backdrop blur
- Semi-transparent `Container` with `BoxDecoration(color: surface.withOpacity(0.6))` matches the effect
- Color scheme from React CSS variables:
  - Background: `rgb(15, 18, 33)` → `Color(0xFF0F1221)`
  - Surface: `rgb(26, 30, 46)` → `Color(0xFF1A1E2E)`
  - Primary: `rgb(99, 102, 241)` → `Color(0xFF6366F1)` (indigo)
  - Secondary: `rgb(139, 92, 246)` → `Color(0xFF8B5CF6)` (purple)
  - Text: `rgb(243, 244, 246)` → `Color(0xFFF3F4F6)`
  - Accent: `rgb(6, 182, 212)` → `Color(0xFF06B6D4)` (cyan)

### Implementation Notes
- Update `app_theme.dart` to use the exact React color values
- Create reusable `GlassCard` widget matching `.glass-card` CSS class
- Login screen: gradient background + glass card for form
- Typography: Inter (sans) + JetBrains Mono (code) — available via `google_fonts`
