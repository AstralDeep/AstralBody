# US9 Future-Readiness Verification

**Feature**: 060 Runtime Reliability and Release Readiness
**Branch**: `060-runtime-reliability-hardening`
**Recorded**: 2026-07-16 (America/New_York)
**Status**: T112–T114 and T116–T117 complete; T115 and T118 remain open

This is local source, emulator/simulator, and contract evidence. It is not a signed-candidate,
physical-device, deployed-production, or distribution claim.

## Truthful next-major declaration

The shipping Android toolchain resolved from the tracked source as follows:

| Tool | Shipping version | Next-major target | 2026-07-16 public status |
|---|---:|---:|---|
| Android Gradle Plugin | 9.3.0 | 10 | unavailable |
| Gradle wrapper | 9.6.1 | 10 | unavailable |
| Kotlin | 2.2.10 | built-in through AGP | migrated |
| Kover | 0.9.8 | Gradle 10-compatible release | blocked upstream |

Google's [AGP roadmap](https://developer.android.com/build/releases/gradle-plugin-roadmap)
schedules AGP 10 for late 2026, and its
[built-in Kotlin migration](https://developer.android.com/build/migrate-to-built-in-kotlin)
requires removal of the global opt-outs and `kotlin-android` plugin. Gradle's official
[release notes](https://docs.gradle.org/current/release-notes.html) and
[versions feed](https://services.gradle.org/versions/all) still expose Gradle 9.6.1 as current.
The canary declaration therefore contains explicit `UNRELEASED` sentinels rather than fabricated
versions, distribution URLs, or checksums.

The default canary command exited **69** with this bounded report:

```json
{"canary_passed":false,"reason":"toolchain_unreleased","status":"unavailable","target_majors":{"agp":10,"gradle":10}}
```

The 2026-07-16 official diagnostic confirmed the same state through both supported paths:

| Path | Exit | Status | AGP 10 available | Gradle 10 available | Canary passed |
|---|---:|---|---:|---:|---:|
| Default fail-closed canary | 69 | `unavailable` | false | false | false |
| Explicit verified official-availability diagnostic | 0 | `unavailable` | false | false | false |

The generated `/tmp` report had SHA-256
`736a33926fbc5f6289a33b4d263f2109818d691d79f3b557553726418d3d9745`. The driver will reject this
declaration as stale if either official feed starts publishing major 10. An unavailable diagnostic
is deliberately not a passing canary. The current schema and stale-declaration guard run passed all
**171** guards.

The shipping source has no built-in-Kotlin/new-DSL opt-out, no `kotlin-android` plugin, no legacy
variant API use, no explicit dependency-constraint compatibility flag, and no Project-object
dependency notation. It uses type-safe `projects.core`, built-in Kotlin, and the current DSL. The
standard lint/unit/coverage/assemble gate passed:

```text
ktlintCheck :app:lintDebug :core:test :app:testDebugUnitTest
:core:koverVerify :app:koverXmlReport :core:koverXmlReport :app:assembleDebug
```

The app and core Kover XML reports were both produced. The isolated runner's 10 tests cover strict
properties, separate major-10 pins, shipping-toolchain rejection, resolved-version assertions,
warnings-as-errors, official availability, every tracked removal-blocker class, and cleanup after
success or failure.

## Remaining toolchain blocker

Gradle 9.6.1's `--warning-mode=fail` still exits **1** during Kover plugin configuration. A
deprecation trace identifies the caller as
`kotlinx.kover.gradle.plugin.appliers.PrepareKoverKt.prepare(PrepareKover.kt:29)`, which passes a
Project object as dependency notation. This is not present in AstralDeep's Gradle scripts. Kover
0.9.8 remains the latest published version on the
[official plugin portal](https://plugins.gradle.org/plugin/org.jetbrains.kotlinx.kover), while the
upstream [Gradle 10 deprecation fix](https://github.com/Kotlin/kotlinx-kover/pull/814) is not yet in
a release.

Consequently:

- T115 remains open because exact public AGP-10 and Gradle-10 pins do not exist.
- T118 remains open because no true major-10 toolchain can resolve or run, and the Kover warning
  would correctly fail the warnings-as-errors canary even after the majors publish until an upstream
  compatible plugin release is adopted.
- SC-014's next-major half is not claimed as passed.

## Automated accessibility evidence

Every scoped changed interactive control tested below had a non-empty stable name, native role,
state projection, and native keyboard/focus path. No test found an unnamed scoped control.

| Surface | Automated inspection | Result |
|---|---|---:|
| Android API 37 emulator | Compose semantics for agent/tool switches: Switch role, stable name, on/off state, click action, and requested focus | 2 passed |
| iOS 26.5 simulator | XCUITest for secure API-key field and Save: element type, label, enabled/submitting state, keyboard focus, and live status | 1 passed |
| watchOS 26.5 simulator | Watch button/status metadata consumed by the SwiftUI view: identifier, role, name, dynamic state, and focusability | 2 passed |
| Windows offscreen Qt | QAccessible interfaces for authoring checkboxes/button, lifecycle/application status, and keyboard-operable status banner | 6 passed |
| Browser/server render | Native authoring button/checkbox parsing plus application/lifecycle live-region and guarded submission semantics | 5 passed |
| Native keyboard contract | No custom floating iOS Done accessory; native immediate scroll dismissal and Android native IME path | 2 source + 2 native runtime passed |

There is no application-drawn mobile **Done** button or keyboard accessory in the tested
implementation. iOS and Android retain their native system-keyboard dismissal and IME behavior.
The iOS runtime test passed on the iPhone 17 Pro simulator with the system `Send` key inside the
keyboard frame and no external `Done` button. The Android runtime test passed on the API 37 emulator
with Gboard owning the IME, zero app `Done` nodes, and system Back dismissing the IME.

The current focused cross-client contract reruns also cover the strict seven-field admission-refusal
envelope, canonical submission-ID correlation, status projection, and the applicable accessibility
and native-keyboard regressions:

| Focused client lane | Result |
|---|---:|
| Web Playwright contracts | 15 passed |
| Windows protocol/status/accessibility contracts | 20 passed |
| Android protocol/status/IME contracts | 27 passed |
| AstralCore protocol and reducer suite | 146 passed |
| iOS status contracts | 8 passed |
| Watch status contracts | 5 passed |

These counts are focused local contract evidence, not the still-open T118 same-candidate
cross-client inspection or release matrix.

The Android emulator initially exposed the known Espresso 3.6.1 reflection failure before test
execution. The project now uses the stable AndroidX Test 1.3.0 / Espresso 3.7.0 test-only line; the
official [AndroidX Test release notes](https://developer.android.com/jetpack/androidx/releases/test)
document that 3.7.0 replaces reflective `InputManager.getInstance` access. The rerun then passed on
the already-booted API 37 emulator.

Additional regression evidence:

- Python 3.11 mounted-checkout gate: **36 passed** (canary, browser accessibility, web reducer, and
  native-keyboard contracts).
- Windows client source suite: **582 passed, 6 skipped** in 35.26 seconds; the skips remain the
  existing packaged-Windows-only artifact cases.
- Strict Swift formatting passed for every US9 Apple/Watch source and test file.
- Android lint, JVM unit tests, core Kover verification, both Kover XML reports, and APK assembly
  passed after the accessibility/test-tool updates.

These automated gates do not replace a physical TalkBack/VoiceOver session or the same-candidate
release-evidence matrix. Those remain later release-readiness work and are not represented here as
completed distribution evidence.
