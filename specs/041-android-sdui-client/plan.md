# Implementation Plan: Native Android Client (SDUI Target)

**Branch**: `041-android-sdui-client` | **Date**: 2026-06-30 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/041-android-sdui-client/spec.md`

## Summary

Build a native **Kotlin + Jetpack Compose** Android client as a new ROTE/webrender **SDUI target** — the Android twin of the existing native Windows client — with **no web view**. The app connects to the orchestrator over the existing WebSocket protocol, registers as an Android device, and renders the orchestrator's ROTE-adapted **structured `components`** (the non-web wire layer) as native Compose UI: the full primitive vocabulary, live push streaming rendered in place, and native chrome surfaces (agents, history, audit) driven by the existing data actions / REST endpoints. One adaptive Compose layout serves phone, tablet, and foldable. Authentication is **real** Keycloak OIDC Authorization-Code + PKCE via the dedicated public client (`astral-mobile`), already provisioned and allow-listed by the operator. Remaining server-side work is **minimal and additive**: an `android` ROTE device profile, an Android custom-scheme redirect URI on the `astral-mobile` client, and a new Android CI job. No new wire protocol, no schema changes, no new backend runtime dependencies.

## Technical Context

**Language/Version**: Kotlin 2.0.x targeting JVM 17; Android Gradle Plugin 8.x. minSdk 26 (Android 8.0), targetSdk current (35/36).
**Primary Dependencies**: Jetpack Compose (BOM) incl. Material 3 + **Material 3 Adaptive** (WindowSizeClass), AndroidX Lifecycle/ViewModel/Navigation-Compose; Kotlin Coroutines + Flow; **OkHttp** (WebSocket transport) + Okio; **kotlinx.serialization-json** (wire decode); **AppAuth-Android** + Custom Tabs (OIDC PKCE); AndroidX Security-Crypto / DataStore (encrypted token store); **Coil** (images). Charts via Compose Canvas (no extra dep) for bar/line/pie. *(All require Principle V lead-dev approval — see Constitution Check + research.md.)*
**Storage**: No database in v1. Encrypted local storage only for the OIDC refresh token (AndroidX Security/DataStore). Conversation/canvas state is in-memory + server-hydrated (history via `get_history`/`load_chat`).
**Testing**: JUnit + kotlinx-coroutines-test for **JVM unit tests** of all pure logic (protocol decode, SDUI→model mapping, streaming consumer, REST shaping) in a pure-Kotlin `:core` module; Compose UI tests (`androidx.compose.ui.test`) for key renderers/screens; **Kover** for changed-code coverage.
**Target Platform**: Android 8.0+ phones, tablets (≥7"), and foldables; all screen sizes in the handheld/large-screen family. (Car/automotive out of scope — see spec Assumptions.)
**Project Type**: Mobile app — a new native client target in `android-client/`, a sibling of `backend/` and `windows-client/`. Two Gradle modules: `:core` (pure Kotlin, JVM-tested) and `:app` (Android/Compose).
**App identity**: applicationId / namespace `com.kyopenscience.astral`; OIDC redirect `com.kyopenscience.astral:/oauth2redirect` (custom scheme via an intent filter; to be added to the `astral-mobile` client's Valid Redirect URIs by the operator).
**Performance Goals**: 60 fps scrolling on a mid-range phone; streaming updates visible within ~1 s of server emission (SC-003); large tables/transcripts virtualized (LazyColumn) so the UI never blocks.
**Constraints**: NO embedded web view (Constitution II — native render only); reuse the existing message/streaming protocol + REST endpoints unchanged; server changes additive only; offline + push notifications out of scope.
**Scale/Scope**: ~35 SDUI primitive renderers (parity with the 35-type webrender registry); 5 surfaces (chat + canvas, agents & permissions, history, audit); phone/tablet/foldable adaptivity.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design (below).*

| Principle | Verdict | Notes |
|-----------|---------|-------|
| **I. Primary Language (Python backend)** | PASS (note) | Governs **backend** code, which stays Python. The Android client is **native client** code; Kotlin is the platform's required language. This is the first Kotlin client (the Windows client is Python/PySide6) — lead-dev should acknowledge the new client surface. |
| **II. UI Delivery Architecture (SDUI)** | PASS | Additive native target. The client consumes the **astralprims-defined structured components** over the existing non-web wire (ROTE-adapted via `supported_types`); `astralprims` is unchanged and agent response-building is unchanged. Consistent with the established Windows-native precedent — native clients render the structured primitives client-side; the orchestrator delivers ROTE-adapted structured components (no HTML to native). The only orchestrator touch is an **additive `android` ROTE device profile**. |
| **III. Testing (≥90% changed-code coverage)** | PASS (new track) | A new **Android** test + coverage track: JVM unit tests for all pure logic with **Kover** ≥90% on changed Kotlin, enforced in the new CI job. The existing Python `diff-cover` gate measures Python only; the tiny Python changes (android profile + azp doc) get their own Python tests. |
| **IV. Code Quality / lint** | PASS | Kotlin lint (**ktlint** or **detekt**) + Android Lint in the CI job; Python touches pass `ruff`. |
| **V. Dependency Management** | **GATE — needs approval** | The Android client introduces a defined dependency set (Compose/AndroidX + OkHttp, kotlinx.serialization, AppAuth, Coil). These are **client-artifact** deps, NOT backend-image deps, but Principle V still requires they be documented (done in research.md) and **lead-dev approved in the PR** before merge. |
| **VI. Documentation** | PASS | KDoc on public Kotlin; client README + a `docs/keycloak-android-client-setup.md`; document the `android` ROTE profile. No new `astralprims` primitives. |
| **VII. Security** | PASS | Keycloak OIDC Authorization-Code + PKCE (RFC 8252) via a dedicated **public** client `astral-mobile` (no client secret); refresh token in encrypted storage; tokens gated by the existing `KEYCLOAK_ALLOWED_AZP` allow-list. No secrets committed. |
| **VIII. User Experience** | PASS | Renders only astralprims-defined primitives (no new ones); mirrors the established design language/theme; unknown types degrade to a labeled placeholder. |
| **IX. Database Migrations** | N/A | No schema change — the client reuses existing endpoints. |
| **X. Production Readiness** | PASS (flagged) | Principle X requires verification against a **real client target running against the live backend**. This must be done on a real device/emulator before "done"; unit tests + CI build are necessary but not sufficient. The current engineering environment cannot run an emulator, so the plan specifies an emulator/device verification step (CI emulator job and/or developer device) as a release gate. |
| **XI. Continuous Integration** | PASS | Add an **additive** Android CI job (Gradle `assembleDebug` + JVM unit tests + Kover coverage + Kotlin/Android lint). It does not alter the backend gate set; the new CI tooling is documented per the Principle XI carve-out. |

**Result**: No hard violations. One **action-required gate** (Principle V dependency approval) and one **flagged constraint** (Principle X on-device verification). Both are tracked below.

## Project Structure

### Documentation (this feature)

```text
specs/041-android-sdui-client/
├── plan.md              # This file
├── research.md          # Phase 0 — technology decisions + dependency rationale
├── data-model.md        # Phase 1 — client-side entities + wire model
├── quickstart.md        # Phase 1 — build / run / test the Android client
├── contracts/           # Phase 1 — the wire + REST + primitive contracts the client depends on
│   ├── ws-protocol.md
│   ├── rest-endpoints.md
│   └── sdui-primitives.md
├── checklists/
│   └── requirements.md   # Spec quality checklist (PASS)
└── tasks.md             # Phase 2 — /speckit-tasks (NOT created here)
```

### Source Code (repository root)

```text
android-client/                      # NEW — native Android client (sibling of backend/, windows-client/)
├── settings.gradle.kts             # includes :core and :app
├── build.gradle.kts                # root build config
├── gradle/libs.versions.toml       # version catalog (the approved dependency set)
├── core/                           # PURE KOTLIN module — no Android deps -> JVM unit tests
│   ├── src/main/kotlin/com/kyopenscience/astral/core/
│   │   ├── protocol/               # WS message models + JSON decode/encode (kotlinx.serialization)
│   │   ├── sdui/                   # structured Component model + type->renderer KEY map (no Compose)
│   │   ├── streaming/              # push-stream consumer (seq dedupe, session filter, terminal) — twin of windows streaming.py
│   │   └── rest/                   # REST request/response shaping (audit, agents) — twin of windows rest.py
│   └── src/test/kotlin/...         # JVM unit tests for ALL of the above (the FR-016 surface)
├── app/                            # ANDROID module — Compose UI + platform integration
│   ├── src/main/kotlin/com/kyopenscience/astral/app/
│   │   ├── transport/              # OkHttp WebSocket client (Flow of inbound msgs; outbound ui_event/chat)
│   │   ├── auth/                   # AppAuth OIDC PKCE + encrypted token store + dev-token path
│   │   ├── render/                 # Compose renderers: type -> @Composable (the Android renderer registry)
│   │   ├── stream/                 # binds core/streaming to the Compose canvas state
│   │   ├── ui/                     # adaptive Scaffold (chat rail + canvas); screens: chat, agents, history, audit
│   │   └── MainActivity.kt
│   ├── src/test/kotlin/...         # JVM unit tests for app-level pure helpers
│   └── src/androidTest/kotlin/...  # Compose UI tests (renderers, adaptive layout)
└── README.md

backend/rote/capabilities.py         # additive: `android` DeviceType + host-config entry (full native capability)
.github/workflows/android-ci.yml     # NEW — Gradle build + unit tests + coverage + lint (additive job)
.env.example                         # document astral-mobile azp (already allow-listed at runtime)
docs/keycloak-android-client-setup.md# NEW — realm public-client setup (mirrors the desktop doc)
```

**Structure Decision**: A new top-level `android-client/` Gradle project, split into a **pure-Kotlin `:core`** module (protocol, SDUI model, streaming, REST — all JVM-unit-testable without an emulator, satisfying FR-016) and an Android **`:app`** module (Compose renderers, transport, OIDC, adaptive UI). This mirrors the `windows-client/` separation of pure logic (`streaming.py`, `rest.py`, `chrome.py`) from the Qt UI, and keeps the bulk of the logic testable in CI without a device.

## Complexity Tracking

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|------------|--------------------------------------|
| New language/toolchain (Kotlin/Gradle) in the repo | Native Android per Constitution II ("native phone clients receive their own appropriate format") requires Kotlin + the Android SDK; there is no Python path to a native Android app | A cross-platform/web-view client violates the no-web-view native-SDUI mandate (Constitution II/VIII) and degrades UX; the Python Windows client is not portable to Android |
| New third-party dependency set (Principle V) | A native Compose app needs Compose/AndroidX + a WS client, a JSON codec, and an OIDC PKCE library | Hand-rolling WS/JSON/OIDC would be more code, less safe, and slower; these are the standard, well-supported choices. Documented in research.md; **lead-dev approval required** |
| `android` ROTE device profile added server-side | A native client renders the full vocabulary and does its own responsive layout, so it needs a full-capability profile + `supported_types` negotiation (like `windows`) — not the web-oriented `mobile`/`tablet` content constraints (which, e.g., strip code on `mobile`) | Reusing `mobile`/`tablet` would strip natively-renderable content and double-adapt layout the client already handles; tuning via `ROTE_HOST_CONFIG` env would alter web-mobile behavior too. The new profile is ~5 additive lines, no schema, mirroring the existing `windows` entry |

---

## Phase 0 / Phase 1 outputs

- Phase 0 research → [research.md](research.md)
- Phase 1 design → [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Post-design Constitution re-check**: unchanged from the table above — the design introduces no new violations. The dependency set is finalized in research.md (Principle V approval still required at PR time); the server delta remains the additive `android` ROTE profile + azp allow-list entry + CI job (no schema, no new backend runtime deps, no wire change).
