# Quickstart: Native Android Client

How to build, run, and test `android-client/`. (Per Constitution X, on-device verification against the live backend is required before a change is "done" — unit tests + a CI build are necessary but not sufficient.)

## Prerequisites
- JDK 17, Android SDK (via Android Studio Ladybug+ or the command-line tools), an emulator or a device (Android 8.0+).
- A reachable orchestrator. For local dev, run it in **mock-auth** mode (`USE_MOCK_AUTH=true`, `ASTRAL_ENV=development`) so the `dev-token` is accepted.

## Build & unit-test (no device needed — the bulk of logic)
```bash
cd android-client
./gradlew :core:test            # JVM unit tests: protocol, sdui mapping, streaming, rest
./gradlew :app:testDebugUnitTest # app-level JVM unit tests
./gradlew koverVerify           # changed-code coverage >= 90%
./gradlew ktlintCheck lintDebug  # Kotlin + Android lint
./gradlew :app:assembleDebug    # -> app/build/outputs/apk/debug/app-debug.apk
```

## Run (real Keycloak — the required path)
- The `astral-mobile` **public** client is provisioned + allow-listed. Ensure its Valid Redirect URIs include the Android **custom-scheme** redirect `com.astralbody.mobile:/oauth2redirect` (Android can't use the desktop's loopback redirect). The app does OIDC Authorization-Code + PKCE via a Custom Tab against `astral-mobile` and registers as `device_type=android`. See `docs/keycloak-android-client-setup.md`.
- Install + launch: `./gradlew :app:installDebug` (emulator → host via `ASTRAL_WS_URL=wss://<host>/ws`).

## Debug-only shortcut (NOT in release builds)
- For local testing against a **mock-auth** orchestrator only, a `BuildConfig.DEBUG`-gated dev-token path may be used (`ws://10.0.2.2:8001/ws`, `dev-token`). It is compiled out of release builds — real Keycloak is the product auth (FR-002).

## Instrumented / UI tests (emulator)
```bash
./gradlew :app:connectedDebugAndroidTest   # Compose UI tests on a running emulator/device
```
- Heavier; runs locally and as an optional/nightly CI job (emulator runner), not a per-PR gate.

## CI
- `.github/workflows/android-ci.yml` runs on PRs touching `android-client/`: `:core:test` + `:app:testDebugUnitTest` + `koverVerify` + lint + `:app:assembleDebug` (uploads the debug APK artifact). The backend Principle XI gates are unchanged and independent.

## Acceptance smoke (maps to spec Success Criteria)
1. Fresh install → sign in → first native-rendered response (SC-001).
2. Trigger rich output (table/card/chart) + a streaming tool → all render natively, stream updates in place (SC-002/SC-003).
3. Run on phone + tablet/foldable (or resize) → layout adapts side-by-side ↔ stacked (SC-004).
4. Open Agents / History / Audit → native screens, audit paged + filtered, user-scoped (SC-005/SC-007).
5. Kill connectivity mid-session → disconnected state → auto-reconnect, no dup sends (SC-006).
