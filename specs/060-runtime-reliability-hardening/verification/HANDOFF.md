# Spec 060 — live-trial handoff (what's blocked on hardware/accounts)

**Recorded**: 2026-07-16/17 (America/New_York). Branch `060-runtime-reliability-hardening`, PR #143.

All **code** deliverables for US8 + Phase-12 authoring are committed and the
release-tooling CI lane is green. What remains is **live verification** that
needs a Mac, a staging host, or one-time interactive sign-ins. This file is the
punch list.

---

## 0. coverage-gate — DEFERRED ("circle back", 2026-07-17)

The feature-029 single-lane `coverage-gate` (diff-cover on the `test` job's
`backend/coverage.xml`) is temporarily **non-blocking** (`continue-on-error:
true` in `ci.yml`). Why: the 060 feature deliberately splits coverage across
lanes (in-image `test`, host `release-tooling-tests`, perf, integration,
per-client), so a single-lane diff-cover under-measures. The honest first step
is already committed — test modules are excluded from the diff (they run in
other lanes) — which lifts it from 77% to ~82% locally (higher in CI, where all
tests pass; my local measure was suppressed by ~23 clean-postgres env
failures). The residual to reach 90% is genuine changed-product-line coverage,
dominated by the 17k-line `orchestrator.py` (~63%), plus `scheduler/api.py`
(70%), `knowledge_synthesis.py` (78%), `llm_gate.py` (75%), `history.py` (83%).
To circle back: run the honest diff locally
(`diff-cover backend/coverage.xml --compare-branch origin/main --fail-under 90
--exclude '*/tests/*' 'backend/tests/*' '*/conftest.py'`), write targeted tests
for those files' uncovered changed lines, then delete the `continue-on-error:
true` line to re-enable enforcement. The spec's cross-lane authority
(`scripts/check_changed_coverage.py`, T125) is the eventual ≥90% gate once the
readiness workflow is active.

---

## A. Staging matrix — DEFERRED ("won't set up" the staging host, 2026-07-17)

**Decision:** the dedicated persistent staging host will not be provisioned
(cert provider down + team opted out). The `release-readiness` matrix therefore
stays **INACTIVE** (`RELEASE_READINESS_ACTIVE` unset) and tasks **T111 / T125 /
T128** are deferred until an external staging host exists. A GitHub-hosted
runner alone can't host the shared endpoint across the matrix — its runners are
ephemeral and torn down between jobs, so the Windows/Android/Apple/web producer
jobs (each on a fresh runner) couldn't reach a stack deployed in `stage-deploy`.
The `stage-deploy` / `stage-cleanup` jobs now run on `ubuntu-latest` (no
self-hosted runner) and target an external host at `ASTRAL_STAGING_ENDPOINT`.
The local pre-push diagnostic (`scripts/prepare_release_evidence.py`) needs none
of this and works today.

To revisit later: stand up a persistent external Linux host with a public HTTPS
name (a Cloudflare quick tunnel on that host gives a valid cert with no cert
provider), set `ASTRAL_STAGING_ENDPOINT`, add the secrets below, and flip
`RELEASE_READINESS_ACTIVE=true`. Retained setup detail for that day:

1. **A Linux host** (Docker + Docker Compose v2, ≥4 CPU / 8 GB, outbound HTTPS to
   github.com + ghcr.io). Root or docker-group access.
2. **Register it as a repo runner** with the `astral-staging` label:
   - GitHub → repo Settings → Actions → Runners → New self-hosted runner →
     follow the shown `./config.sh --url https://github.com/AstralDeep/AstralDeep
     --token <reg-token> --labels astral-staging` then `./run.sh` (or install as
     a service). I can generate the registration token via
     `gh api -X POST repos/AstralDeep/AstralDeep/actions/runners/registration-token`
     and hand it to you if you want.
3. **A public TLS hostname** that resolves to the runner and terminates HTTPS in
   front of port `${STAGING_BIND_PORT}` (the staging stack binds
   `127.0.0.1:${STAGING_BIND_PORT}`). Any of: a UKY-issued cert + reverse proxy,
   a `*.ai.uky.edu` name, or a Cloudflare Tunnel / Tailscale Funnel. The endpoint
   must contain **no** userinfo/query/fragment and must not be loopback.
   → Give me: that hostname (e.g. `https://astral-staging.ai.uky.edu`).
4. **Repository secrets** I will set once you provide the values (via `gh secret
   set`, or you set them in Settings → Secrets → Actions):
   - `ASTRAL_STAGING_ENDPOINT` = the public HTTPS URL from step 3
   - `ASTRAL_STAGING_PROBE_TOKEN` = a bearer token the probe uses for
     `GET /api/dashboard` on the staged instance
   - `STAGING_POSTGRES_IMAGE`, `STAGING_KEYCLOAK_IMAGE`,
     `STAGING_SCHEMA_BASELINE_IMAGE` = **digest-pinned** images
     (`host/repo@sha256:…`); the schema-baseline is a 057.001 image
   - `STAGING_RUNTIME_ENV_FILE` = absolute path on the runner to a `chmod 600`
     env file with the staged app's runtime config (LLM/system creds, Keycloak
     internal URL, etc.)
   - `STAGING_DB_USER/PASSWORD/NAME`, `STAGING_KEYCLOAK_DB_USER/PASSWORD/NAME`,
     `STAGING_KEYCLOAK_ADMIN_USER/PASSWORD`, `STAGING_BIND_PORT`
   - `ASTRAL_WINDOWS_SMOKE_TOKEN`, `ASTRAL_RELEASE_USERNAME`,
     `ASTRAL_RELEASE_PASSWORD` (a staging user pre-provisioned with an LLM
     config so the 054 first-run gate doesn't block the workspace),
     `ASTRAL_STAGING_ACCESS_TOKEN` (Android short-lived login token)
5. **Keycloak**: the staging realm import fixture is committed
   (`backend/tests/fixtures/runtime_reliability_060/staging/keycloak-realm.json`,
   PKCE, no secrets); only the runtime users/passwords come from the secrets
   above. If UKY IAM is the realm instead of the bundled Keycloak, give me the
   realm/issuer URL and I'll wire the staging compose to point at it.

**Minimum to get started:** the runner host + the public HTTPS hostname. I can
generate the runner registration token and set every secret from values you
paste. Once the runner is up and `ASTRAL_STAGING_ENDPOINT` is set, I flip
`RELEASE_READINESS_ACTIVE=true` (checkpoint 2) and dispatch the first readiness
run.

---

## B. Mac tasks (Apple — you pick these up)

> **2026-07-17 status — items 1–3 DONE on the Mac.** (1) The producers are
> swift-formatted and the strict recursive lint is clean. (2) Both producers
> compile-verify (`build-for-testing` green for AstralAppUITests on the
> iOS 26.5 sim and AstralWatchTests on the watchOS 26.5 sim). (3) The macOS
> first-login "status text never transitions" bug is ROOT-CAUSED AND FIXED:
> `.accessibilityElement(children: .ignore)` mints a generic AXGroup even on a
> Text, and macOS AXGroups drop AXValue — every phase read as an empty value.
> The contract now lives directly on the status Text (a real AXStaticText);
> macOS first-login is 4/4 locally. Two sibling instances of the same
> platform-semantics class were also fixed: the continuity semantic matcher
> now accepts label OR value (macOS puts static-text content in the VALUE),
> unblocking the first-ever macOS deterministic relaunch result (20/20, mean
> 1.64 s), and the system-IME composer contract is explicitly skipped on
> macOS. Deterministic portions of items 4–5 are recorded in
> `us3-continuity.md` / `us5-apple-first-login.md`; the live-authenticated
> portions still need the provider-configured account below.

Xcode 26.6 (build 17F113), iOS/watchOS 26.5 runtimes. From repo root:

1. **swift-format the new producer files** (blocks the `swift-format` required
   gate; I authored them on Windows and cannot run swift-format):
   ```
   xcrun swift-format format -i --recursive --configuration apple-clients/.swift-format \
     apple-clients/AstralApp/AstralAppUITests/ReleaseEvidenceUITests.swift \
     apple-clients/AstralWatchTests/ReleaseEvidenceTests.swift
   git add -A && git commit -m "style(060): swift-format release-evidence producers"
   ```
   Then re-run the lint to confirm clean:
   `xcrun swift-format lint --strict --recursive --configuration apple-clients/.swift-format apple-clients/AstralCore apple-clients/AstralApp apple-clients/AstralWatch`
2. **Compile-verify the new producers** (authored blind on Windows — never
   compiled): build the `AstralAppUITests` and `AstralWatchTests` targets and
   fix any compile errors in `ReleaseEvidenceUITests.swift` /
   `ReleaseEvidenceTests.swift` (watch for: `XCTAttachment` availability on the
   watchOS test bundle, `ASWebAuthenticationSession` element access on macOS,
   springboard consent-alert handling). The files auto-join their targets via
   the synchronized-group mechanism (no pbxproj edit was needed).
3. **Debug macOS `LLMFirstLoginUITests`** — the real open bug. On GitHub
   `macos-26` runners the status text never transitions (all of "Check your
   provider credentials", "Provider unavailable", "Unable to confirm;
   reconnecting" absent; the 10s watchdog measured 12.4s > the 11.5s ceiling).
   iOS only misses the 250 ms ack window under VM latency; **macOS looks like a
   real fixture/app-side bug** — the us5 record only ever showed iOS UI
   automation passing, so macOS UI automation may never have passed. Reproduce
   with `-only-testing:AstralAppUITests/LLMFirstLoginUITests -destination
   'platform=macOS'` and trace the `--astral-ui-test-first-login` fixture states
   on macOS.
4. **T078** — 30 first-login trials on iOS *and* macOS, record timing
   distributions in `verification/us5-apple-first-login.md`.
5. **T057 / T102 / T124 Apple portions** — 20 continuity trials per Apple client,
   lifecycle sequences, and the final Apple validation lanes; record in the
   `us3-continuity.md`, `us7-operability.md`, and `final-apple.md` records.

Note: the two watchOS/AstralCore apple-ci **infra** failures (simulator device,
codecov upload) were fixed in `.github/workflows/apple-ci.yml` (deterministic
`astral-watch-060` device by UDID; staged codecov path) — verify they pass on
the next apple-ci run; they are not Swift-code issues.

---

## C. Windows host — reached its ceiling here

- Source suite + deployment-profile logic: **green** (108 profile/integrity
  tests; full `windows-client/tests` suite run locally).
- The **0.4.0 frozen EXE cannot be built on this host**: it needs Python 3.11
  (host has 3.10/3.8 only), and per the spec the release EXE is **built once in
  CI** by `build-windows-candidate.yml` and consumed unmodified by the readiness
  matrix + bridge/publisher. Local rebuilds are explicitly out of the trust
  path. So T069's fresh-EXE proof runs on the CI Windows runner, not here.
- One-time sign-in still pending for any Windows *client* live trial (the app
  had no stored session).

---

## D. One-time interactive sign-ins (for local live trials)

- **Web (T057/T102 web)**: the Chrome extension is connected, but driving a live
  chat turn via browser automation was unreliable here — the WS authenticates
  and `ws.chat_message` dispatches (audit confirms `ws_register` /
  `session_resumed` / `chat_message` all *success* for the real GLM-configured
  user `58e0d4ff…`), but form submits didn't consistently transmit and the one
  turn that dispatched produced no completion within minutes. Best driven by a
  human with a fresh interactive session, or re-run once the staging endpoint is
  the target. The stack itself is proven (the two day-old chats render).
- **Android**: the debug APK is built and installed on the running emulator
  (`emulator-5554`); it needs one Keycloak login to be usable for continuity
  trials.
