# Phase 0 Research: Native Android Client (SDUI Target)

All "NEEDS CLARIFICATION" from Technical Context are resolved below. Findings are grounded in the existing codebase (`backend/rote/capabilities.py`, `backend/orchestrator/auth.py`, the shipped `windows-client/`) and established Android practice.

## D1 — UI toolkit: Jetpack Compose (Material 3 + Adaptive)

- **Decision**: Jetpack Compose with Material 3 and Material 3 Adaptive (WindowSizeClass).
- **Rationale**: Compose's declarative recomposition is a natural fit for SDUI — a component tree maps directly to `@Composable` functions, and in-place updates are just state changes keyed by `component_id` (via `key(...)`). Material 3 Adaptive gives first-class phone/tablet/foldable reflow. This is the modern Android default.
- **Alternatives**: Android Views/XML (imperative, verbose, poor fit for dynamic trees) — rejected.

## D2 — SDUI component model + renderer registry

- **Decision**: Decode the wire into a pure-Kotlin `Component(type, id, attributes: JsonObject, children: List<Component>)` in `:core/sdui`. In `:app/render`, hold a registry `Map<String, @Composable (Component, RenderScope) -> Unit>`; unknown `type` → a labeled placeholder Composable. The canvas keeps a keyed list (`component_id → Component`); `ui_upsert` ops replace/remove by id; Compose `key(component_id)` preserves identity and animation.
- **Rationale**: Direct twin of the Windows `renderer.py` `REGISTRY` + `_r_fallback` and `Canvas.apply_ops`. Keeping decode/model in `:core` makes the type→model mapping JVM-unit-testable (FR-016); only the Composable bodies need Android.
- **Alternatives**: A giant `when(type)` (less extensible than a registry); rendering from server HTML (forbidden by Constitution II) — rejected.

## D3 — Wire codec: kotlinx.serialization

- **Decision**: `kotlinx.serialization-json`. Messages decode via a typed envelope discriminated on `type`; component `attributes` stay as `JsonObject`/`JsonElement` (the wire is dynamic per primitive).
- **Rationale**: Kotlin-native, no reflection, sealed-class polymorphism for the message union, multiplatform-ready (KMP path later). Tolerant decoding (`ignoreUnknownKeys = true`, `isLenient`) matches the defensive Windows decoders.
- **Alternatives**: Moshi/Gson (reflection-based, less idiomatic) — rejected.

## D4 — Streaming consumer (port of the Windows logic)

- **Decision**: Port `windows-client/astral_client/streaming.py` to `:core/streaming` as pure Kotlin — `streamFrameToOps(frame, activeChat, seqState)` with `session_id` filter, monotonic `seq` dedupe, `terminal` final/forget, `error → alert`, rendering the structured `components` (ignoring `html`), keyed by `stream-<stream_id>`. Same for `subscribeAckOps`/`streamErrorOps`.
- **Rationale**: Identical wire contract (verified by the protocol map used to build the Windows consumer); reusing the exact logic + test cases guarantees parity and is fully JVM-testable.
- **Alternatives**: Re-derive from scratch (risk of drift) — rejected.

## D5 — Transport: OkHttp WebSocket (+ REST)

- **Decision**: OkHttp `WebSocket` + `WebSocketListener`, surfaced as a Kotlin `Flow<InboundMessage>`; OkHttp also serves the authenticated REST calls (audit, etc.). Outbound `ui_event`/`chat_message` sent on the socket.
- **Rationale**: Battle-tested, ubiquitous on Android, trivial backoff/reconnect, one HTTP stack for WS + REST. Mirrors the Windows `protocol.py` model (inbound signal stream + thread-safe send).
- **Alternatives**: Ktor client (heavier, another stack), `Java-WebSocket` (less maintained) — rejected.

## D6 — Auth: AppAuth-Android (OIDC Authorization Code + PKCE)

- **Decision**: **Real Keycloak** OIDC Authorization-Code + PKCE via AppAuth-Android + Chrome Custom Tabs (RFC 8252 external user-agent) is the **mandated** auth path (per directive — no reliance on mock/dev auth in the product). Dedicated **public** client **`astral-mobile`** (no secret) — **already provisioned and added to `KEYCLOAK_ALLOWED_AZP`** by the operator (cloned from `astral-desktop`). Because it was cloned from the desktop client, its current redirect URIs are the desktop **loopback** set; the Android flow needs a **custom-scheme/app-link** redirect added to the `astral-mobile` client — recommended `com.personalailabs.astraldeep:/oauth2redirect` (captured by an intent filter; Android cannot use loopback). Silent refresh; refresh token in encrypted storage (AndroidX Security/DataStore). A developer-token shortcut, if kept, is **debug-build-only** (`BuildConfig.DEBUG`-gated, never in release), for local mock-auth testing.
- **Rationale**: AppAuth is the reference OIDC native-app implementation; PKCE public client is the by-the-book mobile posture and matches the existing `astral-desktop` pattern + the `KEYCLOAK_ALLOWED_AZP` allow-list (`backend/orchestrator/auth.py` → `is_azp_allowed`).
- **Alternatives**: Hand-rolled OIDC (error-prone), embedded WebView login (insecure, violates the no-web-view posture) — rejected.

## D7 — Adaptive layout: Material 3 Adaptive + WindowSizeClass

- **Decision**: The **client** owns responsive layout. Compact width → stacked/navigable (switch between chat and canvas); Medium/Expanded → two-pane (chat rail + canvas side by side), recomputed on rotation/fold/split via `WindowSizeClass`. ROTE owns **content** adaptation (primitive substitution via `supported_types`), not layout.
- **Rationale**: Native clients do their own layout (the Windows client splits chat/canvas itself); ROTE's job is the wire-level content profile. Clean separation, no double-adaptation.
- **Alternatives**: Let ROTE drive layout for mobile (it only condenses content, not Compose layout) — rejected.

## D8 — ROTE device profile: add an additive `android` full-capability profile

- **Decision**: Add an `android` value to `DeviceType` and a `_BASE_HOST_CONFIG["android"]` entry in `backend/rote/capabilities.py` — full native capability (`supports_code/tables/charts/tabs/file_io = True`, unbounded), mirroring the existing `windows` entry. The client registers `device_type: "android"` + screen dims + `has_touch` + `supported_types`; ROTE substitutes only primitives outside `supported_types`.
- **Rationale**: A native app renders the full vocabulary and does its own responsive layout, so it must NOT inherit the web-oriented `mobile` constraints (which set `supports_code=False`, `max_grid_columns=1`, `max_table_rows=20`). `DeviceType.MOBILE`/`TABLET` already exist but are tuned for small **web** surfaces. The `windows` precedent (a full-capability native profile + `supported_types` negotiation) is the right model. The change is ~5 additive lines, no schema, no new deps; operators can still tune via `ROTE_HOST_CONFIG`.
- **Alternatives**: Reuse `mobile`/`tablet` (strips native-capable content; double-adapts layout); override via `ROTE_HOST_CONFIG` env (would also alter real web-mobile users) — rejected.

## D9 — Charts and images

- **Decision**: Render `bar_chart`/`line_chart`/`pie_chart` with **Compose Canvas** (no extra dependency) from the chart component's series; render `image` with **Coil** `AsyncImage`. `plotly_chart` (web-only) → labeled placeholder (parity with Windows; `supported_types` will exclude it so ROTE substitutes upstream).
- **Rationale**: Avoids a heavy charting dependency for v1; Coil is the standard Android image loader and lets Android do better than the Windows `image` placeholder.
- **Alternatives**: MPAndroidChart/Vico (extra deps, revisit only if Canvas proves insufficient) — deferred.

## D10 — Testing, coverage, and CI

- **Decision**: JVM unit tests (JUnit + kotlinx-coroutines-test) in `:core` cover **all** pure logic — protocol decode, SDUI model mapping, the streaming consumer, REST shaping (FR-016). Compose UI tests in `:app` cover representative renderers + the adaptive scaffold. **Kover** enforces ≥90% changed-code coverage. A new additive `.github/workflows/android-ci.yml` runs `:core:test` + `:app:assembleDebug` + `koverVerify` + ktlint/Android-Lint on PRs touching `android-client/`. An optional **emulator** job (instrumented Compose tests) runs on a schedule/nightly (heavier). Per Constitution X, final correctness is verified on a real device/emulator against the live backend before "done."
- **Rationale**: Maximizes emulator-free verification (the bulk of logic is pure), matching the Windows client's pure-logic + headless-UI split. The backend gate set (Principle XI) is untouched; the Android job is independent.
- **Alternatives**: Emulator-only testing (slow, flaky, not gating) — kept optional.

## D11 — Dependency set (Principle V — requires lead-dev approval)

These are dependencies of the **new client artifact** (`android-client/`), not the backend image. Documented here per Principle V; **approval required in the PR**.

| Dependency | Purpose | Notes |
|------------|---------|-------|
| Jetpack Compose (BOM) + Material 3 + Material 3 Adaptive | Native UI + responsive layout | AndroidX, first-party Google |
| AndroidX Lifecycle / ViewModel / Navigation-Compose | App architecture | AndroidX |
| Kotlin Coroutines + Flow | Async/stream plumbing | JetBrains first-party |
| OkHttp + Okio | WebSocket + REST transport | Square, ubiquitous |
| kotlinx.serialization-json | Wire codec | JetBrains first-party |
| AppAuth-Android + AndroidX Browser (Custom Tabs) | OIDC PKCE | OpenID Foundation reference impl |
| AndroidX Security-Crypto / DataStore | Encrypted token storage | AndroidX |
| Coil | Image loading (`image` primitive) | Widely used |
| Kover, ktlint/detekt (build-time only) | Coverage + lint | CI-only tooling (Principle XI carve-out) |

## D12 — Server-side delta (confirmed minimal + additive)

- **ROTE**: add `android` profile (D8). **Auth**: `astral-mobile` public client **created + allow-listed (operator — done)**; remaining = add an Android **custom-scheme redirect** (`com.personalailabs.astraldeep:/oauth2redirect`) to that client, and document it in `.env.example` + `docs/keycloak-android-client-setup.md`. **CI**: add `android-ci.yml`. **No** new wire protocol, **no** schema change, **no** new backend runtime dependency, **no** `astralprims` change, **no** agent-code change.
