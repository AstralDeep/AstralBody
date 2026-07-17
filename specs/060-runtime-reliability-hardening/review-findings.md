# Non-Security System Review — Main after Feature 058

**Reviewed revision**: `c0829908608bb55f454223f5b7a7890e34f8aad7`

**Review date**: 2026-07-15

**Scope**: Runtime correctness, data integrity, client continuity, deployment packaging,
cross-client behavior, operability, testing, accessibility, and future compatibility. Per the
user's direction, security analysis and security remediation are excluded.

## Executive Assessment

Merged main passes broad source and client smoke tests, and the ordinary dice flow works on the
live web, Windows, and Android clients. It is not yet release-ready. The most serious reproduced
defects are unbounded connection work that survives disconnect, a background-task limit that is not
enforced, duplicate scheduler dispatch, and failed knowledge-synthesis units being marked complete.
Feature 058's happy-path tests pass, but its distributed host lifecycle lacks enough instance and
revision identity to handle child death, multiple hosts, stale frames, disconnects, and promotion
failure deterministically. Two visible release defects are also immediate: Android loses the active
conversation after process recreation, and a clean Windows production client opens a deployment
configuration dialog instead of using a shipped deployment profile.
The supplied App Store report adds a third release blocker: both Apple submissions were rejected
after first-login LLM credential saving became unresponsive and the reviewer could not continue.

## Findings

### Critical — connection-owned work is unbounded and outlives disconnect

The two UI receive loops create an independent task for every frame
([orchestrator.py:10972](../../backend/orchestrator/orchestrator.py#L10972),
[orchestrator.py:11042](../../backend/orchestrator/orchestrator.py#L11042)). Work received before
registration waits on a per-connection event without a timeout
([orchestrator.py:1694](../../backend/orchestrator/orchestrator.py#L1694)), while disconnect cleanup
removes that event but does not retain, cancel, or drain the frame tasks
([orchestrator.py:11015](../../backend/orchestrator/orchestrator.py#L11015),
[orchestrator.py:11026](../../backend/orchestrator/orchestrator.py#L11026)).

Reproduction: 100 pre-registration frames created 100 tasks; all 100 were still pending after the
current disconnect cleanup. Besides retained memory, concurrent state-changing frames can race each
other because their ordering is no longer the socket's ordering.

Remediation direction: bounded per-connection admission, a registration deadline, explicit task
ownership, disconnect cancellation/drain, and ordering or idempotency for state changes.

### Critical — declared background capacity is not enforced

The manager declares a five-task maximum
([async_tasks.py:116](../../backend/orchestrator/async_tasks.py#L116)), but its capacity branch is a
`pass` ([async_tasks.py:171](../../backend/orchestrator/async_tasks.py#L171)) and every accepted item
starts immediately ([async_tasks.py:193](../../backend/orchestrator/async_tasks.py#L193)). It also
truncates operation identifiers to eight UUID characters
([async_tasks.py:175](../../backend/orchestrator/async_tasks.py#L175)) and does not evict completed
in-memory records.

Reproduction: all 12 submitted tasks ran concurrently despite the configured maximum of five, and
all 12 remained retained after completion. The existing 15 focused tests pass because none asserts
the concurrency ceiling.

Remediation direction: real bounded admission with fair queuing or explicit refusal, full identities,
cancellation, bounded retention, load assertions, and capacity telemetry.

### Critical — a due schedule can execute more than once

The scheduler has an in-flight set that is never populated
([loop.py:27](../../backend/scheduler/loop.py#L27)). Every tick performs the same read-only due query
([loop.py:62](../../backend/scheduler/loop.py#L62), [store.py:97](../../backend/scheduler/store.py#L97))
and submits every returned job ([loop.py:68](../../backend/scheduler/loop.py#L68)). There is no
durable occurrence claim covering repeated ticks or multiple service instances.

Reproduction: two ticks submitted the same unchanged due job twice; the in-flight guard remained
empty.

Remediation direction: durable occurrence identities, transactional claims with expiry and fencing,
retry using the same identity, idempotent visible effects, and two-instance/crash tests.

### High — feature 058 needs instance-aware lifecycle semantics

The focused BYO suites pass (62 tests), but several distributed failure paths remain ambiguous:

- Delivery is broadcast to every eligible owner host
  ([orchestrator.py:1129](../../backend/orchestrator/orchestrator.py#L1129)), while tunnel routing is
  keyed only by owner and agent and a later socket replaces the earlier socket
  ([orchestrator.py:996](../../backend/orchestrator/orchestrator.py#L996)). There is no selected-host
  lease or process generation.
- A host drops an invocation when its child is absent
  ([byo_host.py:530](../../windows-client/win_agent/byo_host.py#L530)), and child exit remains local
  to the host ([byo_host.py:604](../../windows-client/win_agent/byo_host.py#L604)). The service can
  therefore continue to describe the agent as running.
- Host disconnect removes routing
  ([orchestrator.py:1009](../../backend/orchestrator/orchestrator.py#L1009)) but does not immediately
  settle calls already waiting in the shared pending-request map
  ([orchestrator.py:8236](../../backend/orchestrator/orchestrator.py#L8236)); they wait for the normal
  timeout ([orchestrator.py:8256](../../backend/orchestrator/orchestrator.py#L8256)).
- Revision acknowledgement is correlated only by agent identity
  ([byo_host.py:202](../../windows-client/win_agent/byo_host.py#L202)). Promotion deletes the live
  directory before replacement and swallows promotion failure
  ([byo_host.py:468](../../windows-client/win_agent/byo_host.py#L468)), after which the caller stops
  the old process.
- Delete removes live routing before persisting the tombstone
  ([orchestrator.py:1145](../../backend/orchestrator/orchestrator.py#L1145)), while a delayed
  registration can later restore runtime maps and mark the row live
  ([orchestrator.py:1229](../../backend/orchestrator/orchestrator.py#L1229)).
- On process launch the Windows host starts every retained bundle
  ([byo_host.py:260](../../windows-client/win_agent/byo_host.py#L260)). If the service refuses an
  obsolete or deleted bundle, the registration timeout kills only the child
  ([byo_host.py:570](../../windows-client/win_agent/byo_host.py#L570)); the live bundle directory is
  retained, so the same refused process is attempted again on every later app launch unless an
  `agent_stop` happens to arrive.

Likely effects are duplicate hosting, last-writer routing, stale acknowledgements activating the
wrong revision, timeouts after a known host failure, loss of the last-good revision, and deleted
agents returning during an unlucky interleaving.

Remediation direction: end-to-end host/delivery/revision/process/request generations, one selected
host instance, explicit child liveness and exit, immediate instance-owned request settlement,
crash-safe promotion with a retained last-good version, and a durable tombstone before cleanup.

### High — Apple first-login credential saving blocked App Store review

The user supplied an App Store rejection covering both the macOS and iOS submissions: after the
reviewer entered and saved LLM API credentials, the app became unresponsive and the reviewer could
not proceed to the next page. The reported review environment was a 14-inch MacBook Pro (November
2024), macOS 26.5.2, with an active internet connection. An iOS review-device model was not included
in the report.

This is external review evidence rather than a local reproduction; the Windows review host cannot
execute the native Apple release candidates. Because the failure occurs in mandatory first-login
setup, it blocks distribution and leaves no usable fallback path for a new user.

Remediation direction: acknowledge Save immediately, keep the UI responsive, make the successful
path fast enough to reach the next page without ambiguity, show the current loading phase whenever
the work is not near-instantaneous, bound failure, and run the complete first-login flow on both
Apple platforms before resubmission.

### High — Android process recreation loses the active conversation

Live testing completed a rendered dice turn and showed that an ordinary socket reconnect preserved
the canvas. Force-stopping and recreating the app, however, returned the authenticated user to the
server welcome rather than the active chat. The view state starts with `activeChatId = null`
([AppViewModel.kt:72](../../android-client/app/src/main/kotlin/com/personalailabs/astraldeep/app/ui/AppViewModel.kt#L72))
and registration reads only that in-memory value
([AppViewModel.kt:212](../../android-client/app/src/main/kotlin/com/personalailabs/astraldeep/app/ui/AppViewModel.kt#L212)).
No durable or process-recreation restoration seam exists.

Reconnect hydration also exposed a transcript mismatch: the store contained assistant and user
turns, while the reconnected screen showed only one visible message. The Android decoder accepts
only string message content ([Wire.kt:330](../../android-client/core/src/main/kotlin/com/personalailabs/astraldeep/core/protocol/Wire.kt#L330)),
but stored chat hydration can include structured content
([orchestrator.py:2353](../../backend/orchestrator/orchestrator.py#L2353)). Finally, `UiRender` has no
chat or connection generation ([Messages.kt:69](../../android-client/core/src/main/kotlin/com/personalailabs/astraldeep/core/protocol/Messages.kt#L69)),
so an out-of-order render cannot always be rejected reliably.

Remediation direction: persist intended active-chat state before registering, restore it across
process recreation, preserve committed UI through atomic hydration, decode every stored content
form, scope renders to chat and connection/request generation, and test missing/reordered frames.

### Medium — personal-agent lifecycle state does not update consistently across clients

The service emits `agent_offline`, but Android classifies it as ignored
([ProtocolManifest.kt:92](../../android-client/core/src/main/kotlin/com/personalailabs/astraldeep/core/protocol/ProtocolManifest.kt#L92))
and Apple does the same
([Dispositions.swift:196](../../apple-clients/AstralCore/Sources/AstralCore/Protocol/Dispositions.swift#L196)).
The Windows host treats it as informational logging
([byo_host.py:193](../../windows-client/win_agent/byo_host.py#L193)). An owner watching the authoring
surface on a non-hosting device can therefore retain a stale running state until another full
refresh.

Remediation direction: one lifecycle vocabulary and state transition behavior across every
authoring-capable client, with push updates and drift-guard tests rather than reload-only correction.

### High — the Windows production artifact deliberately prompts for deployment setup

The clean-profile modal in the user's screenshot is the current designed behavior, not an isolated
local-settings glitch. A bare executable invokes `_prompt_config`
([app.py:3126](../../windows-client/astral_client/app.py#L3126)); resolution considers runtime values,
per-user settings, and then prompt/local defaults
([app.py:3189](../../windows-client/astral_client/app.py#L3189)). The packaged artifact bundles only
its icon ([AstralDeep.spec:69](../../windows-client/AstralDeep.spec#L69)), and the release workflow
does not inject or validate a deployment profile
([release-windows.yml:68](../../.github/workflows/release-windows.yml#L68)).

There is also a precedence defect: command-line connection arguments are parsed
([app.py:3224](../../windows-client/astral_client/app.py#L3224)) but `_resolve_config` does not use
their resolved values consistently. Agent and application settings are read through separate paths,
so the effective deployment can fragment.

Remediation direction: ship one versioned and validated production deployment profile with all
required connection values, resolve it exactly once with tested precedence, reserve the modal for
explicit generic/developer builds, and run a clean-profile packaged-artifact check before signing.

### High — merged Windows BYO code cannot ship under the current release identity

The client still declares version `0.3.0`
([__init__.py:3](../../windows-client/astral_client/__init__.py#L3)), but the existing `v0.3.0` tag
predates feature 058 and contains no BYO host. The release workflow requires the pushed tag to equal
that constant ([release-windows.yml:38](../../.github/workflows/release-windows.yml#L38)). Reusing or
mutating `v0.3.0` would make old and new artifacts share an identity and interfere with existing
equal-version update verification.

The packaged runtime is also not reproducible: a requirements file that otherwise claims exact
release pins adds `astralprims>=0.2.0`
([requirements.txt:19](../../windows-client/requirements.txt#L19)), and the host/bundle exchange has
no explicit runtime compatibility version.

Remediation direction: create a new semantic release while keeping `v0.3.0` immutable, lock the
packaged dependency set, declare a host runtime contract, and verify old-to-new upgrade behavior.

### High — failed knowledge synthesis is marked complete

The synthesis cycle fetches unsynthesized interactions synchronously
([knowledge_synthesis.py:194](../../backend/orchestrator/knowledge_synthesis.py#L194)), catches and
logs per-agent and cross-agent failures, then marks every fetched interaction synthesized
([knowledge_synthesis.py:218](../../backend/orchestrator/knowledge_synthesis.py#L218),
[knowledge_synthesis.py:230](../../backend/orchestrator/knowledge_synthesis.py#L230)). Index and
filesystem work also remains synchronous in the interactive service process
([knowledge_synthesis.py:235](../../backend/orchestrator/knowledge_synthesis.py#L235)).

Reproduction: two deliberately failed interactions were both marked synthesized.

Remediation direction: durable unit claims, success-only completion, retry/error state, atomic output
publication, and off-interactive-path storage work.

### High — authoring and publication use stale read-then-write state

Phase advancement reads the current session and later updates it unconditionally
([agent_authoring.py:541](../../backend/orchestrator/agent_authoring.py#L541),
[agent_authoring.py:581](../../backend/orchestrator/agent_authoring.py#L581)); Analyze follows the
same pattern ([agent_authoring.py:597](../../backend/orchestrator/agent_authoring.py#L597),
[agent_authoring.py:609](../../backend/orchestrator/agent_authoring.py#L609)). Draft slugs have no
data-store uniqueness constraint ([database.py:487](../../backend/shared/database.py#L487)), while
allocation checks only directories that already exist
([agent_lifecycle.py:248](../../backend/orchestrator/agent_lifecycle.py#L248)). Concurrent same-name
drafts can therefore choose the same publication location.

Remediation direction: immutable owner-scoped draft identity, expected-revision updates, idempotent
transitions, uniqueness guarantees, isolated staging, and atomic publication.

### Medium — remaining runtime work can block or race the interactive service

Agent cards are mutated on the event-loop path
([orchestrator.py:1231](../../backend/orchestrator/orchestrator.py#L1231)) while worker-thread work
iterates the same dictionary ([orchestrator.py:4253](../../backend/orchestrator/orchestrator.py#L4253)).
This produced `RuntimeError: dictionary changed size during iteration` during a live Windows
registration. Server-hosted draft lifecycle still launches synchronous subprocesses with pipes and
performs blocking termination/wait work from asynchronous methods
([agent_lifecycle.py:683](../../backend/orchestrator/agent_lifecycle.py#L683),
[agent_lifecycle.py:792](../../backend/orchestrator/agent_lifecycle.py#L792)).

Remediation direction: stable snapshots or single-owner registry access, bounded continuous process
output handling, non-blocking process supervision, and whole-process-tree cleanup.

### Medium — startup updates are not coordinated across service instances

Startup checks the schema marker and runs the full update without a global claim or post-claim
recheck ([database.py:240](../../backend/shared/database.py#L240)). Two instances can therefore both
enter the full update path. In addition, the user-agent constitution revalidation sweep is embedded
inside that full schema path ([database.py:1379](../../backend/shared/database.py#L1379)); a
constitution-only version change can be skipped when the schema marker already matches.

Remediation direction: one coordinated startup updater with a state recheck, concurrent-start and
crash-recovery tests, and lifecycle revalidation triggered by its own version rather than only by a
schema revision change.

### Medium — shipped examples can contradict the real tool contract

The welcome screen asks users to roll `6d20`
([welcome.py:57](../../backend/orchestrator/welcome.py#L57)), while the selected dice tool declares
only six-sided dice ([mcp_tools.py:81](../../backend/agents/dice_roller/mcp_tools.py#L81)). In live web
testing, the system called the six-sided tool six times and then narrated the result as a d20
distribution. This makes a successful-looking response factually inconsistent with its tool trace.

Remediation direction: validate every curated prompt against actual tool bounds and verify generated
narrative against normalized inputs and recorded outputs.

### Medium — long operations need a bounded visible progress contract

One live web curated-example turn took roughly two minutes before its final result. The adaptive
layout path now has an eight-second default per-pass budget
([ui_designer.py:47](../../backend/orchestrator/ui_designer.py#L47)), and its own runtime comment
records a previously measured 83-second frame-silent gap that motivated a progress frame
([orchestrator.py:9405](../../backend/orchestrator/orchestrator.py#L9405)). Other delegated work can
run under a 90-second timeout ([subtasks.py:57](../../backend/orchestrator/subtasks.py#L57)). A long
operation is sometimes legitimate, but each client needs prompt evidence that it is still active and
one terminal state.

Remediation direction: acknowledge or label the active phase within two seconds, preserve that
progress across clients, and guarantee one completed, failed, cancelled, or retryable terminal
outcome.

### Medium — operating guidance and apply behavior are incomplete

`docs/byo-client-agents.md` is referenced from the deployment guide, Apple README, and project
guidance but is absent. The broad `docs/*` ignore rule
([.gitignore:15](../../.gitignore#L15)) silently swallowed the promised file. The deployment guide
says to change the feature setting and restart
([production-deployment.md:79](../../docs/production-deployment.md#L79)), but the repository restart
target only restarts the existing container
([Makefile:20](../../Makefile#L20)) and therefore does not reload environment-file changes.

Remediation direction: explicitly track the guide, validate Markdown targets, provide a recreate or
reconfigure operation, and verify the effective boot value.

### Medium — deployment-like cross-client release gates are incomplete

Windows source tests run on Linux
([ci.yml:52](../../.github/workflows/ci.yml#L52)); the actual Windows packaged artifact is first built
only in the tag-driven release workflow
([release-windows.yml:68](../../.github/workflows/release-windows.yml#L68)). That misses frozen-worker,
stdio, included-dependency, bundled-profile, and clean-profile behavior before a release tag exists.
Connected Android tests are not a regular pull-request gate, and there is no regular live browser
authentication/continuity lane. Apple behavior cannot be verified on this Windows host and requires
an Apple runner.

Remediation direction: artifact-level Windows checks before signing, connected Android and real
browser flows for affected changes, Apple-native evidence on an Apple runner, and an explicit policy
for unavailable platforms.

### Future — Android's next toolchain boundary is already red-flagged

The current Android build and all 15 connected instrumentation tests pass, but the build reports
multiple compatibility settings and legacy extension points that are removed by the next major
toolchain. This is not a present regression; it is scheduled breakage if the project upgrades
without a migration canary.

Remediation direction: remove known-removal constructs while the current toolchain is still
supported and keep a next-major compatibility canary separate from the stable build.

### Medium — two Android authoring switches lack accessible names

The two switches at [Screens.kt:105](../../android-client/app/src/main/kotlin/com/personalailabs/astraldeep/app/ui/Screens.kt#L105)
and [Screens.kt:130](../../android-client/app/src/main/kotlin/com/personalailabs/astraldeep/app/ui/Screens.kt#L130)
do not expose their own labels or semantics. Screen-reader users may hear an unnamed switch or be
unable to associate it with the adjacent text.

Remediation direction: stable label/role/state/focus semantics and automated accessibility checks
for changed authoring surfaces.

## Verification Evidence

- Windows source suite: **422 passed**.
- Android connected instrumentation on Pixel 7 Pro API 36: **15 passed**.
- Focused merged BYO backend and Windows host suites: **62 passed**.
- Isolated merged-main BYO feature-enabled smoke: readiness returned HTTP 200; the native `My
  agents` surface rendered; a benign agent moved offline → running after tunneled registration and
  returned offline after host disconnect/reconnect. The isolated environment was removed afterward.
- Live web: sign-in and a rendered two-dice turn completed successfully.
- Live Windows: sign-in and a rendered three-dice turn completed successfully when deployment
  values were supplied at launch.
- Live Android: sign-in and a rendered three-dice turn completed successfully; ordinary reconnect
  retained the canvas, while process recreation reproduced active-chat loss.
- App Store review report: both Apple submissions were rejected after the first-login LLM credential
  Save flow became unresponsive; this was supplied as external evidence and not reproduced locally.
- Reproductions confirmed: 100/100 orphan pre-registration tasks, 12/12 tasks exceeding the declared
  limit, duplicate dispatch on two scheduler ticks, failed synthesis units falsely completed, and a
  concurrent agent-card iteration runtime error.
- Apple/macOS runtime E2E was not performed because this review host is Windows. Feature 059 owns the
  macOS host and an Apple runner remains required for native evidence.

## Mapping to Specification 060

- Connection, background task, and scheduler correctness: FR-001–FR-008; SC-001–SC-002.
- Personal-agent lifecycle, revision, and compatibility: FR-009–FR-018; SC-003–SC-004.
- Authoring, maintenance, startup, and shared-state concurrency: FR-019–FR-025 and FR-058–FR-059;
  SC-005, SC-009, and SC-017–SC-020.
- Conversation continuity and lifecycle parity: FR-026–FR-032; SC-006 and SC-022.
- Windows shipped deployment and release identity: FR-033–FR-040; SC-007–SC-008.
- Truthful examples, progress, documentation, accessibility: FR-041–FR-047; SC-010–SC-014.
- Artifact-level cross-client release gates and future compatibility: FR-048–FR-053; SC-012–SC-015.
- Apple first-login LLM setup and App Store review evidence: FR-054–FR-057; SC-016.
- Reproducible packaged runtime compatibility: FR-018; SC-021.
