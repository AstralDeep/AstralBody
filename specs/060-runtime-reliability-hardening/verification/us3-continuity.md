# US3 Conversation Continuity Verification

**Feature**: 060 Runtime Reliability and Release Readiness

**Branch**: `060-runtime-reliability-hardening`

**Recorded**: 2026-07-16 (America/New_York)

**Status**: current-tree service preparation and local contract evidence only;
T057 remains open

This record contains no access tokens, credentials, user payloads, or browser
session data. The checkout contained concurrent uncommitted feature work, so
none of the evidence below is represented as clean-checkout, signed-candidate,
staged, deployed-production, or distribution proof.

## Current-tree backend preparation

The local `astraldeep` service was healthy before synchronization, but two
files under test did not match the current host checkout:

| File | Host SHA-256 before sync | Container SHA-256 before sync |
|---|---|---|
| `backend/orchestrator/orchestrator.py` | `057198f43cd9a090cc21dd21f09322af4aa4abea1bbf8d913d7cacac35f0dbc7` | `5fc83070ed6393722247639dc93747081998b2043609633f701ed27cbdc46d20` |
| `backend/webrender/static/client.js` | `b5d93989c3509a09342b35b18793511d97f6c17c68ad92e246719a805bdf5892` | `9a796a259e70ad4cfdf56a7909e5f3316c58bfd9c5b114bb86c404a51f1fedc0` |

Both `/healthz` and `/readyz` returned HTTP 200 before the sync. The documented
command was then run from the repository root:

```text
make sync
```

It copied the current `backend/` source into the existing app container and
restarted only the `astraldeep` service. Afterward, both container hashes
equalled the host hashes above, `/healthz` and `/readyz` again returned HTTP
200, and Docker reported the app and PostgreSQL services healthy. The app
container start time for this bounded restart was
`2026-07-16T16:31:43.183181465Z`.

This proves that subsequent probes reached the current local tree. It does not
by itself prove client restoration, because no authenticated client snapshot
was available during the restart.

## Windows evidence attempt

The available Windows source-client environment was macOS 26.5.2 arm64,
Python 3.14.6, PySide6 6.11.1, and the offscreen Qt platform. It was not a
Windows OS or packaged Windows candidate. Neither `pwsh` nor `powershell.exe`
was available.

The environment contained no `ASTRAL_TOKEN`, no non-empty default
`.astral_token.json`, and no exported `KEYCLOAK_AUTHORITY`. An explicit
noncredential token was used for one bounded live connection probe so the
authentication posture could be observed without opening an interactive
login or reading credentials:

```text
QT_QPA_PLATFORM=offscreen .venv/bin/python \
  windows-client/tests/verify_live.py \
  --url ws://127.0.0.1:8001/ws \
  --token dev-token --token-file '' --no-agent --window 3
```

Result: exit 2 with `AUTH FAILED: reason='invalid'`. This is valid live evidence
that the current backend failed closed; it is not a conversation-continuity
pass and created no chat or semantic snapshot.

The following source-client reducer gate was rerun:

```text
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest \
  windows-client/tests/test_conversation_continuity_060.py \
  windows-client/tests/test_status_lifecycle_060.py -q
```

Result: **33 passed in 0.38 seconds**. These deterministic tests cover locator
durability, generation fencing, semantic snapshot reduction, operation
terminality, and 20 reordered five-state lifecycle sequences. They do not
exercise a live authenticated reconnect or process restart.

**Windows T057 result**: **0/20 qualifying live trials**. The blockers are the
absence of an already-authorized token/session and the absence of a Windows
host or packaged candidate. No token was extracted, no credential was
fabricated, and no user sign-in was performed.

## Web/Chrome evidence attempt

Google Chrome was installed and running. The supported Chrome-control
integration did not expose a controllable tab binding in this run, so existing
tab authentication could not be inspected or used safely. The protected
browser-release inputs were also absent: no release username/password,
non-loopback HTTPS staging URL, or lifecycle-agent identity/state list was
exported. The qualifying release runner deliberately rejects loopback HTTP and
requires those protected inputs.

A request to the current local web root returned HTTP 302 with
`Location: /auth/login?next=%2F`, confirming that the live server required
authentication. No browser sign-in was attempted.

The synthetic-DOM Chromium contract lane was rerun inside the repository's
digest-pinned Playwright 1.61.1 image with Corepack npm 11.16.0:

```text
PLAYWRIGHT_IMAGE="$(tr -d '\n' < tooling/web-ci/playwright-image.txt)"
docker run --rm -v "$PWD:/work" -w /work/tooling/web-ci \
  "$PLAYWRIGHT_IMAGE" sh -lc \
  'test "$(corepack npm --version)" = "11.16.0" && \
   corepack npm ci --ignore-scripts && \
   corepack npm run check:package-manager && \
   corepack npm run browser:contract'
```

Result: **15 passed in 1.4 seconds**. A supporting current-container source
gate also passed:

```text
docker exec astraldeep bash -lc \
  'cd /app/backend && python -m pytest \
   tests/test_client_js_contract.py tests/test_status_lifecycle_060.py -q'
```

Result: **42 passed in 0.32 seconds**. These are deterministic client and
protocol contracts. They are not live browser, real-Keycloak, reload, backend
restart, or lifecycle timing evidence.

**Web T057 result**: **0/20 qualifying live trials**. The blocker is the lack of
a safely usable authenticated browser session or protected staging identity in
the available automation surface. No browser storage, cookies, tokens, or
credentials were inspected.

## Android emulator evidence attempt

The available Android target was the already-booted `Pixel_7_Pro` AVD at
`emulator-5554`, running Android 17/API 37. The AstralDeep package was not
installed when this attempt began, so the emulator had no existing Android
token, account locator, or authenticated chat to resume. The current debug APK
was built and installed from this checkout; its SHA-256 was
`e93c24e6fc889629818afe17f956abec0c43aa1a62106bbd861505e78a25f3cf`.

The complete connected instrumentation gate was run with the Android Studio
JBR and the committed Gradle wrapper:

```text
cd android-client
sh ./gradlew ktlintCheck :app:connectedDebugAndroidTest \
  --no-daemon --stacktrace
```

Result: **20 passed, 0 failed, 0 skipped in a 23-second Gradle run**. Within
that gate, `ConversationContinuityInstrumentedTest` passed both connected tests.
Its 20-repeat case uses Android's real private `SharedPreferences` adapter and
constructs a fresh store for every recreation, proving all 20 synthetic
account-scoped locators reload with foreign-account isolation. This is durable
device-storage contract evidence; it does not claim that an authenticated
Activity process restored transcript and canvas from the backend.

A separate shell-driven OS process exercise installed the same APK and ran 20
consecutive cycles of:

```text
adb shell am force-stop com.personalailabs.astraldeep
adb shell am start -W \
  -n com.personalailabs.astraldeep/.app.MainActivity
```

Every cycle proved the old process absent, observed a distinct replacement PID,
confirmed `MainActivity` as the top resumed activity, and inspected the rendered
UI. Result: **20/20 cold launches passed**, with a worst `TotalTime` of **830
milliseconds**. Every launch correctly stopped at the `Sign in` / `Secured by
Keycloak` screen, so **0 authenticated chat restorations** were attempted. The
emulator could reach `10.0.2.2:8001` (`toybox nc` exit 0), and the synchronized
host backend returned HTTP 200 from `/readyz`; transport reachability was not the
blocker.

The continuity/status/IME protocol regression subset also passed **48 tests**:
18 Android conversation-continuity, 10 status/lifecycle, 3 native-IME action,
6 core manifest, and 11 core runtime-wire tests. These prove generation fences,
semantic snapshot reduction, lifecycle ordering, and native dismissal contracts
deterministically, not through a live authenticated conversation.

**Android T057 result**: **0/20 qualifying live trials**. The device began with
no installed app or reusable authenticated session. Project policy prohibits
fabricating credentials, bypassing Keycloak, extracting another client's token,
or performing the user's sign-in. Consequently the same-chat transcript/canvas
restoration, five-second bound, semantic parity, and no-welcome assertions could
not be measured. T057 remains open.

## Apple simulator evidence attempt

The available Apple environment was Xcode 26.6 (`17F113`) on macOS 26.5.2
(`25F84`), using an iPhone 17 Pro iOS 26.5 simulator and an Apple Watch Series
11 (46mm) watchOS 26.5 simulator. The host was a MacBook Air (`Mac17,3`, Apple
M5, 32 GB), not the reported 14-inch MacBook Pro November 2024 profile.

The current iOS application was launched without a test fixture against the
synchronized, healthy backend. It stopped at `Sign in with SSO`; no reusable
authorized Apple session or committed chat was present. The screen capture is
`build/060/live-apple/ios-preflight-after-launch.png`. No Keycloak sign-in,
credential fabrication, or token extraction was performed.

A bounded DEBUG-only iOS fixture then exercised the production
`ConversationResumeStore`, account-scoped locator, continuity fences,
`conversation_snapshot` reducer, and transcript/canvas views. It seeded one
fixed chat, terminated the application process, and launched a fresh process
to resume the locator 20 times. Every relaunch rendered the expected question,
attachment, structured text answer, component answer, and canvas without an
empty welcome state:

| iOS deterministic process-relaunch metric | Result |
|---|---:|
| Passed relaunches | 20/20 |
| Mean | 3.153 s |
| p50 | 3.148 s |
| p95 | 3.200 s |
| Maximum | 3.205 s |

The result bundle is
`build/060/live-apple/continuity-ios-20-relaunch.xcresult`; exported timing,
hierarchy, and screenshot attachments are under
`build/060/live-apple/continuity-ios-20-relaunch-attachments/`. These are real
application termination/relaunch cycles and production persistence/rendering
paths, but the semantic frames were canonical fixture input rather than an
authenticated backend stream. They therefore do not qualify as T057 live
restart/reconnect trials.

The Watch continuity model suite was repeated 20 times on the booted watchOS
simulator. All six tests passed in every repetition (**120/120 executions**),
covering locator storage, disconnect retention, foreign-account isolation, and
resume registration. The result bundle is
`build/060/live-apple/watch-continuity-20-repetitions.xcresult`. This is
deterministic model/storage evidence, not a paired authenticated Watch session
through the backend.

The matching macOS UI continuity attempt never initialized XCTest. Xcode
reported `The test runner failed to initialize for UI testing` with underlying
error `Authentication canceled. System authentication is running.` The result
bundle is `build/060/live-apple/continuity-macos-20-relaunch.xcresult`. No system
authentication was performed or bypassed, so there is no macOS trial result.

**Apple T057 result**: **0/20 qualifying live trials** for iOS, **0/20** for
macOS, and **0/20** for the paired Watch path. An authorized Apple session and
committed backend chat are absent; macOS automation is additionally blocked by
host system authentication. The deterministic iOS and Watch passes establish
useful persistence/reducer prerequisites but cannot satisfy the authenticated
backend restart/reconnect requirement. T057 remains open.

## T057 acceptance status

| Supported client slice | Qualifying live trials | Five-second restoration measured | Semantic transcript/canvas parity measured | Result |
|---|---:|---|---|---|
| Web/Chrome | 0/20 | No | No | blocked on authenticated controllable session |
| Windows | 0/20 | No | No | blocked on authenticated session and Windows candidate |
| Android | 0/20 | No | No | blocked on an authenticated Android chat; storage and cold-start prerequisites passed |
| iOS | 0/20 | No | No | blocked on an authenticated Apple chat; 20/20 fixture-driven process relaunches passed |
| macOS | 0/20 | No | No | blocked on authenticated chat and host system authentication |
| Watch | 0/20 | No | No | blocked on a paired authenticated session; 120/120 deterministic model executions passed |

The bounded backend restart, fail-closed probes, and passing reducer suites are
useful prerequisites, but they do not satisfy T057. This task must remain open
until 20 authenticated trials per supported client restore the same committed
chat and ROTE-adapted canvas within five seconds, with exact timings and
semantic comparisons recorded here.

## Authenticated account-switch and relaunch rerun

After the evidence above was recorded, the repository owner prepared the
dedicated development account on the web, iPhone, Mac, and Watch, and allowed
the Android system-browser PKCE flow to use `DEV_USER`/`DEV_PASS` from the local
`.env`. No credential value, access token, cookie, provider secret, or user
payload was printed or persisted in this evidence.

The account has no AI-provider configuration and therefore stops at the
mandatory provider-setup surface on web, Android, iOS, and macOS. The Watch
restores its signed-in home. These sessions can prove principal isolation and
authentication persistence, but they cannot create the committed chat/canvas
required for T057 semantic-parity qualification.

### Cross-user history regression and fix

The owner's report that the development account displayed another account's
history reproduced a real shared-tab web defect. `client.js` selected a cached
`sessionStorage` bearer before the freshly rendered shell token. Signing out
and then signing in as a different principal in the same tab could therefore
register the WebSocket with the previous principal even though the new cookie
session was correct.

The client now gives the server-rendered shell token precedence. Clicking
`/auth/logout` immediately clears the in-memory token, cached bearer,
account-session marker, and the current account-scoped active-chat locator.
Regression coverage now:

- seeds an invalid prior-principal token in the shared tab;
- verifies the outbound `register_ui` token equals the current
  `/auth/session` token and subject;
- requires stale-token rejection on every qualifying browser load;
- asserts logout clears both token and account marker before navigation; and
- exercises a shared-tab account switch without permitting reuse of the prior
  token.

Focused results after the fix were **34 passed** in the synchronized backend
container and **38 passed, 1 skipped** in the local Python environment. The
digest-pinned Playwright ESLint gate also passed. The live Keycloak browser
run then completed 20 reload/reconnect trials with:

| Authenticated web metric | Result |
|---|---:|
| Successful reloads | 20/20 |
| Mean | 137 ms |
| p95 | 265 ms |
| Maximum | 268 ms |
| WebSocket principal equals cookie session | 20/20 |
| Seeded stale principal token rejected | 20/20 |
| Leaked account/token storage keys | 0 |
| Development-account history count | 0 |

The final mandatory provider-setup modal and canvas hashes were stable. This
is direct evidence that the reported cross-user history exposure is fixed for
the tested shared-tab path. It is not a 20-turn chat continuity pass because
the development account has no provider and no committed chat.

### Android authenticated relaunch

The Pixel 7 Pro/API 37 emulator completed the production Chrome Custom Tab,
Keycloak, and `astral-mobile` PKCE flow and returned to the native app as the
development account. The settled app showed mandatory provider setup and no
other users' recent history.

Twenty real OS cycles then ran `am force-stop` followed by a fresh Activity
start and waited for the authenticated surface:

| Android authenticated process-recreation metric | Result |
|---|---:|
| Successful relaunches | 20/20 |
| Mean | 2,659.6 ms |
| p95 | 2,710 ms |
| Maximum | 2,764 ms |
| Restored surface | mandatory provider setup |
| Authentication | persisted Keycloak PKCE session |

This advances Android from unauthenticated launch stability to authenticated
session restoration within five seconds. It still cannot establish same-chat
transcript/canvas parity until the development account has a provider and one
committed rendered turn.

### Apple authenticated relaunch

The owner prepared the development account on iOS, macOS, and watchOS. An
opt-in XCUITest first performs an unmeasured preparation launch, skips safely
when no authenticated session is prepared, and then measures 20 production app
termination/relaunch cycles while requiring the mandatory provider gate and
the absence of a Sign-in button.

The iPhone 17 Pro/iOS 26.5 simulator passed:

| iOS authenticated process-recreation metric | Result |
|---|---:|
| Successful relaunches | 20/20 |
| Mean | 3.003 s |
| p50 | 3.000 s |
| p95 | 3.025 s |
| Maximum | 3.034 s |
| Restored surface | mandatory provider setup |

The macOS attempt first reproduced the owner's apparent freeze. XCTest spent
60 seconds trying to terminate PID 84645. A three-second process sample showed
the AstralDeep main thread idle in the normal AppKit event loop; the process
was parented by a stale Xcode `debugserver`, which intercepted termination
signals. Ending that stale debugger session cleared the condition. The same
authenticated test then passed on the MacBook Air/macOS 26.5.2 host:

| macOS authenticated app-restart metric | Result |
|---|---:|
| Successful relaunches | 20/20 |
| Mean | 1.534 s |
| p50 | 1.538 s |
| p95 | 1.578 s |
| Maximum | 1.587 s |
| Restored surface | mandatory provider setup |

The booted Apple Watch Series 11/watchOS 26.5 simulator then completed 20
`simctl terminate`/`launch` cycles:

| Watch authenticated process-recreation metric | Result |
|---|---:|
| Successful process launches | 20/20 |
| Mean process-launch acknowledgement | 132.397 ms |
| p95 | 134.573 ms |
| Maximum | 146.898 ms |
| Settled twentieth surface | signed-in development-account home |
| Other-user recents visible | 0 |

The settled twentieth Watch screenshot displayed `New conversation`, the
development-account identity, and `Sign out`; it did not display another
account's conversation history. The Watch timing measures process-launch
acknowledgement, with a separate settled-surface inspection, so it is not
represented as end-to-end semantic restoration latency.

### Updated T057 acceptance status

| Supported client slice | Authenticated session relaunch/reload | Under five seconds | Same committed chat/canvas parity | Current result |
|---|---:|---:|---:|---|
| Web/Chrome | 20/20 | Yes | No | principal isolation fixed; provider/chat still required |
| Windows | 0/20 | No | No | Windows host and authenticated candidate still required |
| Android | 20/20 | Yes | No | authenticated provider gate restored |
| iOS | 20/20 | Yes | No | authenticated provider gate restored |
| macOS | 20/20 | Yes | No | stale debugger diagnosed; clean relaunches passed |
| Watch | 20/20 | launch acknowledgement only | No | signed-in owner-scoped home restored |

T057 remains open. Its remaining non-Windows blocker is deliberate: the owner
must configure an AI provider for the development account through the product
UI before a real turn can be committed. The remaining Windows slice also needs
a Windows host/candidate. No provider credential was typed by automation and
the mandatory gate was not bypassed.

### Durable Apple sign-out follow-up

The cross-account report prompted a second audit of native logout ordering.
Android and Windows already clear their local credential and account-scoped
conversation locator before best-effort network revocation. iOS, macOS, and
watchOS instead awaited `/api/auth/logout` before deleting the Keychain item.
If the app was killed, suspended, or stuck in that network wait, the next launch
could restore the prior account even though the user had selected Sign out.

`AppModel.signOut` and `WatchModel.signOut` now snapshot only the old access and
refresh values needed for revocation, synchronously cancel session tasks, wipe
Keychain, clear the account locator and all in-memory history, and expose the
signed-out UI before their first `await`. Socket shutdown and remote revocation
then use the captured old session and cannot make it durable again. A source
contract enforces that ordering on both implementations.

Validation after the change:

- backend/native-auth and history-isolation slice: **57 passed**;
- iOS simulator build: passed;
- macOS arm64 build: passed;
- watchOS simulator build: passed;
- strict recursive Swift format: passed;
- AstralCore: **146 passed**.

This removes the Apple local-token resurrection race. T057 remains open for
provider-backed same-chat semantic parity and the Windows live slice described
above.
