# US7 Operability Verification

**Feature**: 060 Runtime Reliability and Release Readiness

**Branch**: `060-runtime-reliability-hardening`

**Recorded**: 2026-07-16 (America/New_York)

**Status**: local contract and implementation evidence only; T102 remains open

This record contains no credentials, provider values, bundle source, or user
payloads. The checkout contained concurrent uncommitted feature work, so none
of the results below is represented as clean-checkout, signed-candidate,
deployed-production, or distribution evidence.

## Curated examples and normalized dice results

The Python 3.11 focused gate ran the example, dice, canonical status/lifecycle,
protocol, welcome, and web-client contract suites:

```text
python -m pytest \
  tests/test_curated_examples_060.py \
  tests/test_dice_roller_060.py \
  tests/test_status_lifecycle_060.py \
  tests/test_welcome.py \
  tests/test_welcome_identity.py \
  tests/test_runtime_reliability_protocol.py \
  tests/test_client_js_contract.py -q
```

Result: **105 passed in 0.90 seconds** in the `astraldeep:latest` Python
3.11 image with the checkout's `backend/` mounted for execution.
The deterministic dice case proves the exact six-d6 prompt, quantity, unit,
side count, notation, input/roll/result bounds, labels, individual rolls,
total, and structured result agree with the visible component values. Invalid
quantities and all non-d6 side counts are refused rather than clamped or
mislabelled. The other curated-example tests bind every welcome tile to its
registered tool schema or explicit composition-only disposition; they are not
live provider/tool executions.

## Canonical status and lifecycle reducers

- Backend protocol/emitter tests cover all eight operation states and exact
  terminal/retryable flags, monotonic sequences, first-terminal ownership,
  owner-scoped lifecycle publication, all five lifecycle states, and 20
  deterministic stale/reordered lifecycle sequences.
- The central orchestrator wiring and helper gate passed **33 tests in 0.47
  seconds** on Python 3.11. It covers a durably recorded generic running phase
  at the one-second trigger (therefore visible before the two-second bound) and owner-only lifecycle publication after the
  authoritative runtime transition commits.
- The web source contract has **19 passing tests**. The shipped reducer retains
  the highest operation sequence, preserves the first terminal, applies
  connection/request/chat equality fences, compares lifecycle pairs
  lexicographically, updates an open `[data-agent-id]` surface when present,
  and otherwise exposes the same label through accessible status/toast
  fallbacks. Lock-pinned ESLint passed with zero warnings.
- Android's new status/lifecycle class has **5 passing tests**, including 20
  deterministic five-state sequences, stale/equal rejection, higher-generation
  replacement, surface-only operation scope, and first-terminal retention. The
  earlier complete `:app:testDebugUnitTest` gate passed **167 tests with 0 failures,
  0 errors, and 0 skips** under the Android Studio JBR.
- Windows' strict runtime protocol and native reducer gate passed **7 tests**.
  It proves request/connection/chat scoping, sequence monotonicity,
  first-terminal retention, 20 five-state lifecycle sequences, immediate
  banner/status rendering, and in-place agent-card lifecycle projection.
- The shared AstralCore reducer passed **3 focused tests**, including 20
  reordered five-state sequences. The native application reducer passed its
  **2 focused tests** on both macOS and the booted iOS 26.5 simulator, and the
  Watch reducer passed its focused test on the booted watchOS 26.5 simulator.
  Strict Swift formatting passed for every added or changed reducer/test file.

These are deterministic reducer/contract tests, not the required 20 live
sequences on each shipping client. No physical-device or live-deployment
timing claim is made here.

## Latest cross-platform regression checkpoint (pre-protected)

The latest local regression pass retained the earlier focused evidence and added these broader
results:

| Lane | Result | Qualification boundary |
|---|---:|---|
| Backend default suite | 4,911 passed, 2 skipped, 2 deselected | Final clean test run; not a clean-checkout claim |
| Backend module suites | 725 passed, 1 warning | Local source/module execution |
| Concurrent-surface performance | 1 passed in 0.58 seconds | Local performance regression |
| Windows source suite | 582 passed, 6 platform skips | Source tests; no packaged-candidate claim |
| Web locked lane | 15 browser, 5 core conversion, 1 Node CLI conversion, and 1 Chromium conversion passed | Lock-pinned local browser/tooling evidence |
| Android prior full gate | 89 core, 180 app, and 19 connected tests passed | Prior emulator/JVM gate; not a T123 candidate rerun |
| Apple AstralCore | 146 passed after T129 | Shared protocol/reducer source gate |
| Apple iOS app | 76 passed | Booted simulator app gate |
| Apple iOS UI | 5 passed | Booted simulator UI gate |
| Apple macOS app | 76 passed | Native app source gate |
| Apple Watch | 12 passed | Booted watchOS simulator gate |

The six Windows skips are platform-bound cases: two require the candidate job's
`ASTRAL_WINDOWS_EXE`, two require a frozen Windows GUI, one requires a native HWND, and one requires
an OS clipboard unavailable in the headless source-test environment. The macOS UI host attempt was
blocked by Xcode infrastructure before a worker or test launched, so it supplies neither a passing
test count nor a product-test failure.

The T129 exact-correlation regression is included in these gates: **54 focused backend tests**
passed, and focused client reruns passed for web (15), Windows (20), Android (27), AstralCore (146),
iOS (8), and Watch (5). Those tests enforce the exact seven-field admission-refusal envelope,
canonical `submission_id` correlation, and refusal decoding/drift behavior; they do not turn the
broader platform counts into live or protected evidence.

This checkpoint does not close T057 or T102, does not execute or close T121–T128, and is not a
protected-workflow, same-candidate, signed, staged, deployed, or distribution qualification.

## Operator guide, boot-setting application, and link validation

The personal-agent guide is explicitly unignored and covers enablement,
effective-setting verification, eligible hosting modes, the exact five-state
lifecycle, recovery/failover, runtime-contract compatibility, disablement,
rollback, and non-sensitive troubleshooting. The documented `make
apply-config` contract force-recreates the app service and prints only the
normalized effective `FF_BYO_AGENTS` value; it does not print `.env`, invoke
`docker inspect`, or imply that a restart reloads Compose environment changes.

Python 3.11 executed the documentation and quickstart contract gate:

```text
python -m pytest \
  backend/tests/test_documentation_060.py \
  backend/tests/test_quickstart_commands.py -q
```

Result: **22 passed in 0.18 seconds**. The documentation module alone has
**18 passing tests**. A separate tooling-coverage run exercised all **208/208
statements (100%)** in `scripts/check_doc_links.py`. The standard-library CLI
then reported:

```text
documentation link check passed: 25 Markdown file(s)
```

The validator uses NUL-safe Git inventories, checks maintained tracked and
non-ignored candidate Markdown before commit, ignores fenced examples,
supports inline/image/reference links, verifies local files/directories and
anchors, rejects repository escape/untracked/unsupported/invalid-percent
targets, and never contacts external URLs. CI runs the same tests under
tooling-Python coverage and then invokes the CLI directly.

## Additional local checks

- Targeted Ruff over the changed US7 Python and test files: **passed**.
- Lock-pinned JavaScript ESLint over `client.js` and the web tooling: **passed**.
- Android `:app:compileDebugKotlin`: **BUILD SUCCESSFUL**.
- Android targeted and complete app unit gates: **BUILD SUCCESSFUL**.
- `git diff --check` over the US7 implementation surface: **passed**.

## Windows and web live-evidence attempt

The local backend was synchronized with `make sync` before these attempts.
The current host and container copies of `orchestrator.py` and `client.js`
matched by SHA-256 afterward, both health probes returned HTTP 200, and Docker
reported the app service healthy. Exact hashes and restart evidence are in
`verification/us3-continuity.md`.

- Windows: no `ASTRAL_TOKEN` or non-empty default token cache was available,
  and the macOS arm64 host was not a Windows packaged-candidate environment.
  The real-auth wire harness was run once with the explicit noncredential value
  `dev-token`; the backend rejected it with `AUTH FAILED: reason='invalid'`
  (exit 2). The source-client continuity/status gate passed **33 tests in 0.38
  seconds**, including 20 deterministic five-state reducer sequences. It did
  not exercise a live lifecycle transition.
- Web: the live root returned HTTP 302 to `/auth/login?next=%2F`. Chrome was
  installed and running, but no supported controllable authenticated tab was
  available, and the protected release credentials, HTTPS staging endpoint,
  and lifecycle-agent inputs were absent. The digest-pinned Chromium contract
  lane passed **15 tests in 1.4 seconds**; the supporting web-client and backend
  status/lifecycle source gate passed **42 tests in 0.32 seconds**. Neither
  result is live browser evidence.

Therefore this attempt contributes **0/20 qualifying live lifecycle sequences
for Windows and 0/20 for web**. It also does not execute every curated example
through real tools, prove a greater-than-two-second operation's visible phase
and exactly one durable terminal across reconnect, or verify the documented
configuration flow from a clean checkout. T102 remains open.

## Android emulator live-evidence attempt

The already-booted `Pixel_7_Pro` Android 17/API 37 emulator could reach the
synchronized backend on `10.0.2.2:8001`, and the host `/readyz` probe returned
HTTP 200. The AstralDeep package was absent at pickup and therefore had no
reusable authenticated Android session. Installing the current debug APK and
launching it rendered `Sign in` and `Secured by Keycloak`; no credential was
fabricated, no token was extracted from another client, and no user login was
performed.

The latest Android-focused contract run passed **48 tests**: 18 conversation
continuity, 10 status/lifecycle, 3 native-IME action, 6 protocol-manifest, and 11
runtime-wire tests. The status/lifecycle class includes 20 deterministic
five-state sequences with stale/equal rejection, higher-generation replacement,
surface scoping, correlated refusal settlement, and first-terminal retention.
The complete connected emulator gate then passed **20/20 tests** in a 23-second
Gradle run, including real Android-preferences continuity, Compose accessibility,
and the shipping composer instrumentation.

The composer check focused the production `AdaptiveShell` text field and
observed Android's configured native IME package as
`com.google.android.inputmethod.latin`. The app-owned Compose tree contained
**zero `Done` nodes**. Android's system Back action dismissed the native IME and
left composer focus retained. There is no application-drawn mobile Done overlay
or accessory; Android owns the keyboard and its dismissal behavior.

A separate 20-cycle `am force-stop` plus cold `am start -W` exercise produced a
new PID on every cycle, resumed `MainActivity`, and rendered the Keycloak sign-in
surface every time; all 20 passed and the worst launch `TotalTime` was 830
milliseconds. This is real process-recreation and launch-stability evidence, but
not a live lifecycle sequence or authenticated continuity result.

Therefore this attempt contributes **0/20 qualifying Android live lifecycle
sequences** and no greater-than-two-second authenticated operation terminality
trial. Without an existing authorized Android session, the five server-committed
lifecycle states could not be dispatched to the owner and timed in the app.
T102 remains open.

## Evidence still required before T102 or US7 can close

1. Exercise the central lifecycle/status wiring through a live deployment and
   prove committed starting, online, updating, failed, and offline transitions
   reach only the owner. The deterministic central wiring tests above are not a
   live client dispatch claim.
2. Run 20 live five-state sequences on web, Windows, Android, iOS, macOS, and
   the shipping Watch target on the booted watchOS simulator, recording
   convergence within two seconds. Add physical Watch evidence only when the
   candidate release infrastructure explicitly supplies that device.
3. Exercise a real operation exceeding two seconds and prove a visible phase
   by the deadline plus exactly one durable terminal across reconnect/replay.
4. Execute every curated example through its real dispatch/tool path and
   compare the user narrative with the normalized result record.
5. From a clean checkout, execute the documented enable/recreate/effective-
   setting flow against a disposable deployment in both true and false
   postures. `make apply-config` was contract-tested but intentionally not run
   against the user's current service during this local implementation pass.

Until those items are appended with exact commands, platforms, timings, and
results, this file is a recoverable local handoff rather than release evidence.

## Authenticated-client follow-up and Mac freeze diagnosis

The owner later prepared the dedicated development account on web, Android,
iOS, macOS, and watchOS. The account has no AI-provider configuration, so the
web/Android/iOS/macOS clients correctly converge on the mandatory provider
gate and the Watch converges on its signed-in home. Twenty authenticated
reload/relaunch cycles passed on each of those five client surfaces; exact
timings and the shared-tab stale-principal security regression are recorded in
`verification/us3-continuity.md`.

The Mac failure was reproducible but was not an app-main-thread deadlock. The
app sampled idle in AppKit while a stale Xcode `debugserver` parent intercepted
termination. After that debugger session was ended, 20/20 authenticated Mac
relaunches passed with a 1.578-second p95 and 1.587-second maximum. This closes
the local freeze diagnosis; it does not close T102 because no live agent
lifecycle sequence or greater-than-two-second provider/tool operation could be
run behind the mandatory provider gate.

T102 remains open. The development account must be configured through the
normal provider UI before live operation/lifecycle evidence can progress, and
the Windows slice still requires a Windows host. No provider credential was
entered or extracted by automation.

## Focused command-topology correction

The documented `make test-060` lane originally executed inside the running app
container, which intentionally mounts only mutable backend data. Contract tests
that inspect tracked `/app/specs`, `/app/scripts`, workflows, and tooling could
therefore fail with missing paths even when the checkout was complete. The Make
target now launches the same `astraldeep:latest` dependency image with the full
checkout mounted read-only at `/app`, disables bytecode/cache writes, and keeps
the explicit non-empty collection guard. The corrected command collected and
passed **226/226** focused tests. This makes the documented focused command
reproducible; it does not substitute for T102's still-pending clean-checkout
apply-config and live lifecycle/operation exercises.
