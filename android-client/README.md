# AstralBody — Native Android Client

A native **Kotlin + Jetpack Compose** Android app that renders the AstralBody
orchestrator's **server-driven UI (SDUI)** as native Compose widgets — **no web
view**. It is the Android twin of the native Windows client: a real
ROTE/webrender *target* that consumes the structured `components` the
orchestrator places on every `ui_render` / `ui_upsert` / `ui_stream_data` (the
non-web wire layer) and draws native UI for the SDUI primitive vocabulary, with
unknown types degrading to a labeled placeholder. Phones, tablets, and foldables
are served by one adaptive layout.

Spec: [`specs/041-android-sdui-client/`](../specs/041-android-sdui-client/).

## Modules

```
android-client/
├── core/   # PURE Kotlin (no Android) — JVM-unit-tested:
│           #   protocol/ (WS message models + JSON), sdui/ (Component + canvas),
│           #   streaming/ (push consumer), rest/ (audit REST shaping)
└── app/    # Android/Compose:
            #   transport/ (OkHttp WS), auth/ (AppAuth OIDC PKCE), render/
            #   (type→@Composable registry), stream/, ui/ (adaptive scaffold +
            #   chat/agents/history/audit screens)
```

The pure logic lives in `:core` so it is testable on the JVM without an emulator
(the bulk of the verification surface). `:core` ports the *verified* logic of the
Windows client (`windows-client/astral_client/streaming.py`, `rest.py`).

## Prerequisites

- JDK 17, Android SDK (Android Studio Ladybug+), an emulator or device (Android 8.0+ / API 26).
- **First-time setup**: open `android-client/` in Android Studio (or run
  `gradle wrapper`) to generate the Gradle wrapper (`gradlew` + the wrapper jar),
  which isn't committed. CI builds via `gradle/actions/setup-gradle` and doesn't
  need the wrapper.

## Build & test (no device — the bulk of logic)

```bash
gradle :core:test                 # JVM unit tests: protocol, sdui, streaming, rest
gradle :app:testDebugUnitTest     # app-level JVM unit tests
gradle :core:koverVerify          # changed-code/module coverage ≥ 90%
gradle ktlintCheck :app:lintDebug # Kotlin + Android lint
gradle :app:assembleDebug         # → app/build/outputs/apk/debug/app-debug.apk
```

(Once the wrapper is generated, prefer `./gradlew …`.)

## Run

**Real Keycloak (the product auth).** The `astral-mobile` public client is
provisioned and allow-listed (`KEYCLOAK_ALLOWED_AZP`). Its Valid Redirect URIs
include the Android scheme `com.kyopenscience.astral:/oauth2redirect` (matching
the app's `appAuthRedirectScheme` manifest placeholder). Point the app at the
orchestrator (`wss://<host>/ws`) and sign in via the system browser (OIDC
Authorization-Code + PKCE), registering as `device_type=android`. See
[`docs/keycloak-android-client-setup.md`](../docs/keycloak-android-client-setup.md).

**Debug-only shortcut** (NOT in release builds): a `BuildConfig.DEBUG`-gated
dev-token path may be used against a mock-auth orchestrator for local testing.

## Instrumented / UI tests (emulator)

```bash
gradle :app:connectedDebugAndroidTest   # Compose UI tests on a running emulator/device
```

## CI

[`.github/workflows/android-ci.yml`](../.github/workflows/android-ci.yml) runs on
PRs touching `android-client/`: ktlint + Android Lint, `:core` + `:app` JVM unit
tests, Kover coverage, and `:app:assembleDebug` (uploads the debug APK). The
backend Principle XI gates are unchanged and independent.

## Notes

- **No web view.** Every surface is native Compose; chrome that the web shell
  receives as HTML (`chrome_render`) is acknowledged, not embedded — native
  screens (Agents/History/Audit) are driven by the existing data actions/REST.
- **Dependencies** (Compose/AndroidX, OkHttp, kotlinx.serialization, AppAuth,
  Coil) are declared in `gradle/libs.versions.toml` and require Constitution V
  lead-dev approval in the PR.
- Per Constitution X, final correctness is verified on a real device/emulator
  against the live backend — unit tests + the CI build are necessary but not
  sufficient.
