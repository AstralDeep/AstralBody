# US5 Apple first-login verification

## Automated evidence

- Backend credential-operation contract: 20/20 tests passed in
  `backend/llm_config/tests/test_operation_status_060.py`. The suite covers
  single-flight admission, the exact eight-second probe and ten-second outer
  attempt bounds, corrective versus retryable outcomes, durable
  reconciliation, fenced persistence, and rejection of late success.
- AstralCore: 146/146 tests passed.
- macOS application model: 76/76 tests passed.
- iOS application model: 76/76 tests passed.
- Watch: 12/12 tests passed.
- First-login focus: 5/5 application-model tests and 3/3 REST reconciliation
  tests passed.
- iOS UI automation: 5/5 tests passed in the broad app gate before the focused
  keyboard, continuity, and repeated first-login runs recorded below;
  the generated result bundle produced valid `xccov` output.
- Strict recursive Swift formatting passed across the maintained Apple source
  trees. The workflow pins Xcode 26.6 and supported iOS/watchOS 26.5 simulator
  runtimes and keeps the UI, Watch, coverage, and aggregate gates
  non-waivable.

## Remaining release evidence

T078 remains open. The required 30 timed trials per Apple platform have not
yet been executed. In particular, the local macOS 26.5.2 UI automation runner
stalled after test launch and was interrupted; this is recorded as an
unresolved environment/runtime result, not converted into a pass. No release
claim may use this file until the complete per-platform trial distributions
are appended here.

## 2026-07-16 local rerun

The local environment was Xcode 26.6 (`17F113`) on macOS 26.5.2 (`25F84`).
The successful UI lane used an iPhone 17 Pro iOS 26.5 simulator. The host was a
MacBook Air (`Mac17,3`, Apple M5, 32 GB), not the reported 14-inch MacBook Pro
November 2024 profile required by T078 when available.

### iOS deterministic scenario matrix

The first 32-repetition diagnostic matrix found a real test/fixture defect:
**30/32 passed**, while slow-success repetitions 2 and 6 failed. The test had
included a Home/background/activate round trip in the five-second
save-to-advance measurement and the fixture left insufficient timing headroom.
The success assertion was corrected to measure Save acknowledgement directly
to form disappearance. Background/foreground responsiveness remains exercised
by the long-active watchdog scenario. Fixture phase transitions were shortened
while preserving visible active/loading feedback after one second.

The corrected final matrix passed **32/32** (four scenarios repeated eight
times) with zero failures. The result bundle is
`build/060/live-apple/first-login-ios-final-32-scenarios.xcresult`; its exported
test tree is
`build/060/live-apple/first-login-ios-final-32-tests.json`. These distributions
are full XCUITest case wall times, including app launch, element waits, typing,
and teardown; they are not provider-operation latency measurements.

| Deterministic iOS scenario | Passed | Mean | p50 | p95 / max |
|---|---:|---:|---:|---:|
| slow success, local feedback, phase, and direct advance bound | 8/8 | 11.213 s | 11.039 s | 11.841 s |
| invalid credentials remain editable and retryable | 8/8 | 8.341 s | 8.335 s | 8.383 s |
| provider unavailable remains explicit and retryable | 8/8 | 6.583 s | 6.580 s | 6.628 s |
| ten-second watchdog with background/foreground responsiveness | 8/8 | 16.373 s | 16.343 s | 16.505 s |

Within each successful slow-success repetition, the test separately requires
local submitting feedback within 250 milliseconds, a named active phase if the
operation is still active after one second, and durable form advance within
five seconds of that local acknowledgement. Each watchdog repetition requires
background/foreground responsiveness and an explicit non-loading
`Unable to confirm; reconnecting` outcome without inventing a server terminal.

This matrix launches a DEBUG-only UI fixture. It supplies canonical operation
frames to the production application reducer and views; it does not contact an
LLM provider, submit credentials, authenticate to the backend, or prove durable
server persistence. A plain, non-fixture iOS launch reached `Sign in with SSO`
and could not proceed without user authentication. Evidence:
`build/060/live-apple/ios-preflight-after-launch.png`. Consequently these 32
passes are regression evidence only and are not T078 qualifying trials.

### macOS attempt

A bounded macOS run built the application and UI test runner, but XCTest never
initialized. The first-login attempt failed before its test body with `The test
runner failed to initialize for UI testing` and underlying error `Timed out
while enabling automation mode`; its result bundle is
`build/060/live-apple/first-login-macos-attempt.xcresult`. The earlier continuity
attempt failed at the same pre-test boundary with underlying error
`Authentication canceled. System authentication is running`; that bundle is
`build/060/live-apple/continuity-macos-20-relaunch.xcresult`. System
authentication was neither performed nor bypassed. No macOS first-login trial
executed.

### Native iOS keyboard evidence

The mobile composer no longer installs an application-drawn keyboard toolbar
or floating `Done` control. Its return key uses the native `Send` submit label,
the composer resigns focus on send, and overflowing transcript/canvas scrolls
use native immediate keyboard dismissal. The focused-composer UI test passed
**1/1** and verified that the native keyboard's `Send` control lies within the
system keyboard frame, no application-drawn `Done` button exists outside that
frame, and transcript scrolling dismisses the keyboard. Evidence:

- `build/060/live-apple/keyboard-ios-native-immediate-dismiss.xcresult`
- `build/060/live-apple/keyboard-ios-native-immediate-dismiss-attachments/BE402CA0-C966-418E-922C-C0B1AAFB814D.png`
- `build/060/live-apple/keyboard-ios-native-immediate-dismiss-attachments/9D2797DA-9903-42A1-838C-43AA33211D68.txt`

### T078 status

T078 remains open. Qualifying evidence is still **0/30** on iOS, **0/30** on
macOS, and **0/30** on the paired Watch path: there is no already-authorized
provider/backend session, the current host is not the reported Mac profile,
and macOS UI automation is blocked before test initialization. The deterministic
matrix above must not be substituted for the required live per-platform trials.

## Authenticated Apple session follow-up

The repository owner subsequently authenticated the dedicated development
account on the iPhone, Mac, and Watch. The account intentionally still has no
AI-provider configuration. This allowed production authentication persistence
and relaunch behavior to be measured, but it did not supply the valid, invalid,
slow, and unavailable provider responses required by T078.

An authenticated continuity XCUITest now skips when no prepared live session
exists, performs one unmeasured preparation launch, and measures 20 subsequent
termination/relaunch cycles. It requires the mandatory `Set up your AI
provider` surface and rejects a return to Sign in.

| Platform | Result | Mean | p95 | Max |
|---|---:|---:|---:|---:|
| iPhone 17 Pro / iOS 26.5 simulator | 20/20 | 3.003 s | 3.025 s | 3.034 s |
| MacBook Air / macOS 26.5.2 | 20/20 | 1.534 s | 1.578 s | 1.587 s |

The first Mac continuity rerun reproduced the reported freeze as a 60-second
failure to terminate the existing app. Sampling found the app's main thread
idle in the normal AppKit event loop, while a stale Xcode `debugserver` parent
intercepted shutdown signals. Ending that debugger session removed the
condition; the clean 20/20 result above followed without an application code
change. This supersedes the earlier assumption that macOS UI automation itself
was necessarily stalled, but it does not turn any provider scenario into a
pass.

The booted Watch simulator also completed 20/20 authenticated process launches;
after settling, the twentieth launch showed the development-account home and
no other-user recent conversations. Watch process-launch acknowledgement had a
132.397 ms mean, 134.573 ms p95, and 146.898 ms maximum. These measurements are
session-continuity evidence, not first-login provider-validation timings.

T078 therefore remains open at **0/30 qualifying provider trials** per Apple
platform. Automation will not enter a user/provider API key or bypass the
mandatory provider gate. Once the owner configures the dedicated account, the
remaining valid/invalid/slow/unavailable matrix can run without exposing the
credential in evidence.
