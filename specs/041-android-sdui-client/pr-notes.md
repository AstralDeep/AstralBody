# PR notes — 041 native Android SDUI client

Paste these into the PR description when opening it.

## Summary

A new native **Kotlin + Jetpack Compose** Android client (`android-client/`) — a
ROTE/webrender SDUI target, the twin of the Windows client, with **no web view**.
It consumes the existing WS + REST protocol unchanged and renders the SDUI
primitive vocabulary natively (unknown types → labeled placeholder), with live
push-streaming, an adaptive phone/tablet/foldable layout, real Keycloak OIDC PKCE
auth, and the agents/history/audit surfaces.

Server delta is **additive only**: an `android` ROTE device profile
(`backend/rote/capabilities.py`), `astral-mobile` added to `KEYCLOAK_ALLOWED_AZP`
(operator `.env`), and a scoped Android CI workflow. **No new backend runtime
dependencies, no schema, no wire change.**

## Constitution V — new client dependency set (lead-dev approval required)

These are dependencies of the **new client artifact**, not the backend image.
Declared in `android-client/gradle/libs.versions.toml`:

- Kotlin 2.0.21, AGP 8.7.3, Compose BOM 2024.12.01 (Compose UI / Material3 /
  Material3-Adaptive 1.0.0), AndroidX (core-ktx, activity-compose, lifecycle,
  navigation-compose, window 1.3.0, security-crypto, datastore)
- OkHttp 4.12.0, kotlinx.serialization-json 1.7.3, kotlinx.coroutines 1.9.0
- AppAuth 0.11.1 (OIDC PKCE), Coil 2.7.0 (images)
- Test/CI: JUnit4, Compose UI test, Kover 0.8.3, ktlint 12.1.1

**Requesting lead-dev sign-off on this set** per Constitution V.

## Constitution XI — CI carve-out

`.github/workflows/android-ci.yml` is **scoped to `android-client/`** and runs
independently of the backend Principle XI gates: ktlint + Android Lint, `:core` +
`:app` JVM unit tests, Kover ≥90% on `:core` (the pure-logic module), and
`:app:assembleDebug` (uploads the debug APK). Instrumented Compose UI tests run on
a nightly/on-demand emulator job, not as a per-PR gate.

## Verification

- JVM unit tests cover the pure logic (protocol decode/encode, SDUI canvas
  reducer, streaming consumer, REST audit parsing, backoff, device caps, layout
  breakpoint, vocabulary parity).
- Built + launched + smoke-exercised on an emulator (build/launch/chat-shell
  confirmed). Per Constitution X, final sign-off is the live sign-in → render →
  stream → audit pass on a device/emulator against the deployment.
