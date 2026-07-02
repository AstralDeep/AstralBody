# Implementation Plan: Cross-Client Native Parity Review & Remediation

**Branch**: `044-native-client-parity` | **Date**: 2026-07-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/044-native-client-parity/spec.md` + the audited
[baseline-findings.md](baseline-findings.md) (line refs re-verified at c2d57b6)

## Summary

Close every parity gap between the web shell (behavioral baseline) and the two native clients
across four planes — protocol handling, rendering fidelity, chrome/settings usability, and
feature completeness — then prove it with live three-client verification and permanent drift
guards. The remediation is **full-stack but additive**: where the root cause is the server
contract (web-only chrome error frames, cookie-bound logout, placeholder surfaces, no
machine-readable protocol registry), the fix lands server-side; where it is client behavior
(no reconnect on Windows, unconsumed top-bar model on Android, no-op theme applies, silent
frame drops, missing attachments/pagination), each client is brought to the same contract.
The organizing artifacts are the [parity matrix](parity-matrix.md) (47 frame types + 35
component types × 3 clients, no cell left unclassified) and a new committed
**UI-protocol manifest** (`backend/shared/ui_protocol.json`) that backend, Windows, and
Android test suites all assert against — making future drift a build failure rather than an
audit finding. Verification is live on all three clients (web browser, the real Windows app,
the Android emulator — both already running on the dev machine) with a legible committed
evidence bundle; the tofu-screenshot defect is diagnosed (capture-environment font failure,
per code evidence: offscreen platform + zero bundled/registered fonts) and the capture
pipeline gains a font sanity gate so illegible evidence becomes impossible by construction.

## Technical Context

**Language/Version**: Python 3.11 (backend, Docker image; local dev container); Python 3.10+ +
PySide6 ≥6.6 (Windows client, host); Kotlin 2.0.21 / JVM 17 + Jetpack Compose (Android `:core`
+ `:app`); ES5 vanilla JS/CSS (web render layer, no build step).
**Primary Dependencies**: Existing only — FastAPI, websockets, psycopg2, astralprims (**no
astralprims change needed**), `webrender` + `rote`; PySide6/QtCharts + `websockets` + stdlib
urllib (Windows); OkHttp, kotlinx.serialization, AppAuth, Coil, Compose BOM 2024.12.01
(Android). **Zero new third-party runtime dependencies; one dependency removal**
(unused `navigation-compose` on Android).
**Storage**: PostgreSQL via `shared/database.py::_init_db()` idempotent guarded migrations.
**Delta: exactly one additive nullable column** — `auth_revocation_queue.client_id TEXT`
(native-logout revocation retries; rollback documented in [data-model.md §8](data-model.md)).
**Testing**: pytest (backend, in-container; diff-cover ≥90% changed lines) + pytest
(windows-client, headless offscreen) + JUnit/Kover (`:core` ≥90%) + `:app` unit tests; **new
drift guards** (manifest ↔ code ↔ per-client classification) run per-PR on all three stacks;
live three-client scenario verification per [quickstart.md](quickstart.md).
**Target Platform**: Linux server (Docker), web browsers, Windows 10+ desktop, Android
API 26+ (emulator API 34 for verification).
**Project Type**: Server-driven-UI system — one backend, three thin clients (this feature's
whole point is keeping them thin *and* equivalent).
**Performance Goals**: reconnect + session resume ≤30 s after server availability (SC-005);
settings surface loads bounded at 10 s with retry (FR-017); theme apply visibly immediate;
turn progress always terminal (SC-006).
**Constraints**: wire changes additive/backward-compatible only (FR-025); web presentation
and behavior unchanged except explicitly-improved paths (error toast); all existing CI gates
stay green (SC-009); no new runtime deps (Constitution V); server keeps owning content/chrome
structure, clients keep owning presentation (FR-025).
**Scale/Scope**: 47 server→client frame types + 35 component types + ~30 ui_event actions × 3
clients; 6 user stories, 26 FRs; ~9 remediation workstreams over 4 codebases
(backend, windows-client, android-client, web static) + 2 CI workflows + the verification
bundle.

## Constitution Check

*GATE: evaluated pre-Phase-0; re-checked post-Phase-1 design — PASS both times.*

- **I. Primary Language (Python backend)**: PASS — backend changes are Python; client changes
  stay in their sanctioned stacks (PySide6 Python, Kotlin/Compose, ES5 JS).
- **II. UI Delivery Architecture**: PASS — remediation *strengthens* II: three more surfaces
  become `components()`-composed (server-owned) instead of native placeholders; the top-bar
  model becomes the only chrome source natives render; no client-side reimplementation is
  introduced (the deliberate agents/audit native screens are recorded dispositions, not new
  divergence). New frames/paths are renderer-layer and additive.
- **III. Testing Standards (≥90% changed-line)**: PASS — every backend change lands with
  pytest (manifest guards, logout endpoint, device-aware chrome, surface builders, canvas
  guarantee); Windows/Android changes land with their suites; diff-cover gates the Python
  side; Kotlin `:core` keeps Kover ≥90% (the ungated `:app` posture is pre-existing and
  recorded in the Defect Register — see Complexity note).
- **IV. Code Quality**: PASS — ruff repo-wide (includes windows-client), ktlint + Android
  Lint, existing JS posture for `client.js` edits.
- **V. Dependency Management**: PASS — zero new third-party runtime deps; one removal.
  PySide6 installed in the new CI job is the client's existing requirements set, not a new
  dependency.
- **VI. Documentation**: PASS — the manifest, new endpoint, chrome/theme/canvas contracts are
  documented in `contracts/`; renderer additions (Windows image/plotly) documented with the
  targets they support; FR-024 reconciles the stale docs (CLAUDE.md tkinter error, 041/042/043
  statuses, READMEs, KNOWN-ISSUES).
- **VII. Security**: PASS — Keycloak stays the sole authority; the new `POST /api/auth/logout`
  is bearer-authed, allowlist-validates `client_id` (`KEYCLOAK_ALLOWED_AZP`), only *revokes*
  credentials (never mints), inherits the web's offline-tolerant queue, and audits
  `auth.logout`. Chrome actions keep server-side `ADMIN_ONLY` enforcement regardless of what
  clients render; role-gated menu entries remain server-omitted for native channels. Refresh
  tokens transit only to the backend/IdP over TLS, exactly like the web callback flow.
- **VIII. User Experience**: PASS — all rendering stays astralprims-driven; no new primitive
  types (pager, chips, banners are client presentation of existing data; `attach_existing` is
  a Button action).
- **IX. Database Migrations**: PASS — one additive nullable column via idempotent guarded
  `_init_db`, rollback documented, tested against representative queue rows.
- **X. Production Readiness**: PASS — the spec's core is exactly X's UI clause: live
  verification on every affected client before "done" (SC-010); failure paths are first-class
  scope (error frames, timeouts, forced failures); observability added where gaps were found
  (unknown-frame logs, revocation outcome logs, `ui_designer`-style fallback logging pattern
  reused).
- **XI. Continuous Integration**: PASS — all existing gates stay; the new windows-client job
  and the guard tests are *additions* to the gate set (documented in the PR); android-ci
  unchanged structurally.
- **XII. Cross-Client Consistency**: PASS — this feature is XII's enforcement pass: one
  server-owned chrome/menu/surface definition consumed by all three clients, per-client
  divergence removed or reclassified as sanctioned web-only carve-outs (admin tools, tour,
  HTML-only chrome regions, audio/generative — each server-enforced and matrix-documented),
  and drift guards to keep it structural.

**Result: PASS. No violations → Complexity Tracking table omitted.** One transparency note:
Kotlin `:app` changed-code coverage remains outside the mechanical Principle III gate (which
is Python diff-cover) — a pre-existing project posture recorded in the Defect Register as a
deferred CI improvement, not a new exception introduced by this feature.

## Project Structure

### Documentation (this feature)

```text
specs/044-native-client-parity/
├── spec.md                  # Feature specification (clarified 2026-07-01)
├── baseline-findings.md     # Audited ground truth (input)
├── plan.md                  # This file
├── research.md              # Phase 0 — decisions R1–R18
├── data-model.md            # Phase 1 — manifest schema, state machines, the one DB delta
├── parity-matrix.md         # Seeded target dispositions → finalized with evidence (FR-001)
├── defect-register.md       # Created at implementation start from baseline + new findings
├── quickstart.md            # Run/verify/regenerate procedures (SC-007)
├── contracts/
│   ├── ui-protocol.md       # Manifest + drift guards + error shapes (R1/R2)
│   ├── session-lifecycle.md # Reconnect/expiry/native logout endpoint (R3–R5)
│   ├── chrome-parity.md     # Topbar/menu/surface lifecycle + new components() (R6–R8)
│   ├── theme-restyle.md     # Token model + per-client appliers (R9)
│   ├── canvas-and-interaction.md  # Canvas semantics, pagination, progress, markdown (R11–R14)
│   └── attachments-windows.md     # Windows attachment lifecycle (R10)
├── checklists/requirements.md
├── verification/            # Evidence bundle (created during US6): README, results.md,
│   └── {web,windows,android}/     #   legible captures per client
└── tasks.md                 # Phase 2 — /speckit-tasks output
```

### Source Code (repository root)

```text
backend/
├── shared/
│   ├── ui_protocol.json            # NEW — committed UI-protocol manifest (R1)
│   ├── protocol.py                 # (shapes documented; no breaking change)
│   └── database.py                 # _init_db: ADD auth_revocation_queue.client_id (guarded)
├── orchestrator/
│   ├── api.py                      # NEW POST /api/auth/logout (bearer + AZP allowlist)
│   ├── web_auth.py                 # _revoke_refresh_token/_revoke_or_queue gain client_id;
│   │                               #   queue retrier uses stored client_id
│   ├── orchestrator.py             # generic ui_event failure → error{code:"internal"}
│   └── chrome_events.py            # device-aware error/close paths (native chrome_surface)
├── webrender/
│   ├── chrome/surfaces/
│   │   ├── workspace_timeline.py   # ADD components(); _view/_live device-aware
│   │   ├── pulse.py                # ADD components()
│   │   └── attachments.py          # ADD components() (+ attach_existing button rows)
│   └── static/client.js            # error-frame toast (web baseline improvement)
├── verification/gallery_driver.py  # NEW — canonical 35-type gallery pusher (US6)
└── tests/                          # manifest guards, logout endpoint, device-aware chrome,
                                    #   surface builders, canvas full-render guarantee

windows-client/
├── astral_client/
│   ├── protocol.py                 # reconnect loop + backoff + bounded queue + status vocab
│   ├── protocol_manifest.py        # NEW — frame classification (guard-tested)
│   ├── app.py                      # classified routing + unknown logging; error banners;
│   │                               #   sign-in dialog; server-revoking sign-out; paperclip +
│   │                               #   chips; topbar actions + status chip; history routing;
│   │                               #   progress signals; surface timeout/retry
│   ├── rest.py                     # upload_attachment (stdlib multipart); logout call
│   ├── renderer.py                 # table pager; interactive color_picker; live theme_apply;
│   │                               #   NEW image + plotly_chart builders (31→33 types)
│   ├── theme.py                    # mutable Palette + build_stylesheet(palette)
│   └── streaming.py                # stream sequence guard (if absent)
├── tests/                          # protocol-manifest guard; reconnect/queue; attachments;
│   │                               #   pagination; theme; routing; screenshot font gate
│   └── screenshot.py               # real-platform capture + font sanity gate (tofu fix)
└── Launch-AstralBody.bat           # env guards (if not defined …)

android-client/
├── core/src/main/kotlin/.../protocol/
│   ├── ProtocolManifest.kt         # NEW — frame classification (guard-tested vs JSON)
│   └── Wire.kt                     # (decode unchanged; Unknown logged at reduce)
├── app/src/main/kotlin/.../
│   ├── ui/RootScaffold.kt          # server-driven topbar (status/pulse/timeline/settings)
│   ├── ui/AppViewModel.kt          # identity-reconciled out-of-turn renders; progress
│   │                               #   signals; unknown logging; surface timeout state;
│   │                               #   themePalette; sign-out ladder
│   ├── ui/Screens.kt               # surface timeout/retry; dead placeholder screens removed
│   ├── ui/theme/Theme.kt           # dynamic ColorScheme from themePalette
│   ├── render/Markdown.kt          # links (LinkAnnotation)
│   ├── render/renderers/Data.kt    # table pager
│   ├── render/renderers/Input.kt   # theme_apply live; interactive color_picker
│   ├── rest/AstralRest.kt          # logout call
│   └── auth/OidcAuth.kt            # revocation call (logout ladder); DevAuth removed
└── (gradle)                        # navigation-compose removed; proguard ref resolved

.github/workflows/
├── ci.yml                          # NEW windows-client job (ubuntu + PySide6 offscreen);
│                                   #   backend manifest guards ride the test job
└── android-ci.yml                  # guards ride existing :core/:app unit jobs

CLAUDE.md                           # tkinter → PySide6 correction (FR-024)
specs/{041,042,043}-*/              # status/tasks reconciliation (FR-024)
```

**Structure Decision**: Multi-client SDUI monorepo. The **manifest + contracts are the single
source of truth**; each client is remediated *to the contract*, never to another client's
implementation (Android's transport semantics get promoted into the contract where they were
already correct). Backend changes are confined to additive frames/endpoints/surface builders;
web changes are limited to the error-toast improvement — the web remains the behavioral
baseline throughout.

## Architecture & Phasing

### Phase 0 — Research ([research.md](research.md))
Decisions R1–R18 resolved: manifest/guard architecture, error-visibility design, Windows
reconnect, expiry state machine, native logout (endpoint + queue column), server-driven
topbar, surface `components()` scope (build: timeline/pulse/attachments; deliberate:
drafts/agents/audit dispositions), surface resilience bounds, theme token contract + per-client
appliers, Windows attachments, pagination reuse, canvas convergence semantics + server
guarantee, progress-signal duty, history routing, tofu diagnosis + evidence pipeline, docs
truth list, CI additions, dependency/schema summary.

### Phase 1 — Design ([data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md), [parity-matrix.md](parity-matrix.md))
Manifest schema + classification model; connection/surface/attachment/turn state machines;
theme palette model; the single DB delta with rollback; six contracts; the seeded parity
matrix; run/verify/regenerate procedures.

### Phase 2 — Tasks (tasks.md via /speckit-tasks)
Dependency-ordered by user story; foundational (manifest + guards + transport + chrome
device-awareness) first, then US1→US6 in spec priority order; each story independently
testable with live-client verification steps embedded, per Constitution X/XII.

### Implementation order (matches spec priorities)

- **Foundational** (blocks everything): `ui_protocol.json` + backend guard tests + per-client
  classification modules & guards + CI windows job; Windows transport reconnect/queue;
  device-aware chrome error/close paths; `error{code:internal}` emission.
- **US1 (P1) — dependable chat loop**: error visibility on natives (+web toast), reconnect
  state UX, expiry sign-in affordances, native logout endpoint + client ladders + queue
  column, progress-signal handling, terminal-state invariant.
- **US2 (P1) — rendering fidelity**: canvas identity reconciliation (both natives) + server
  full-canvas guarantee test; table pagination; Windows image/plotly renderers; Android
  markdown links; stream sequence guard; gallery driver.
- **US3 (P2) — settings usability**: server-driven topbar on both natives;
  timeline/pulse/attachments `components()`; surface timeout/retry; action feedback
  round-trips (8/8 pairs incl. forced failure).
- **US4 (P2) — Windows attachments**: rest upload helper, paperclip + chips, send payload,
  rehydration, library entry.
- **US5 (P3) — theme restyle**: palette models + appliers + `user_preferences`/`theme_apply`
  handling + interactive color pickers + disclosure.
- **US6 (P3) — evidence & docs truth**: screenshot pipeline fix (font gate, real platform),
  live three-client scenario runs, bundle capture, matrix/defect-register finalization,
  041/042/043 + CLAUDE.md/README/KNOWN-ISSUES reconciliation, dead-code removal.

## Complexity Tracking

No constitution violations — table intentionally omitted (see the single transparency note in
the Constitution Check result line).
