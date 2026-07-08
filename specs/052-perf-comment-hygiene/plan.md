# Implementation Plan: System-Wide Performance Optimization + Repo-Wide Comment Hygiene

**Branch**: `052-perf-comment-hygiene` | **Date**: 2026-07-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/052-perf-comment-hygiene/spec.md`

## Summary

Two workstreams. **A — Performance**: remove the systemic latency sources verified in
Phase 0 — connect-per-query DB access and synchronous DB on the asyncio event loop
(pool + async facade + CI detector), N+1s on the hot paths (history list, chat-load
attachments, agent detail), a web asset pipeline that blocks first paint (external fonts,
unconditional 4.5MB Plotly, `no-cache` everything, 200ms connect delay), a designer that
gates web component delivery for up to 24s (upsert-first + 1-pass default), no narrative
streaming (reuse the existing `ui_stream_data` path all three clients already handle),
boot costs (~130-statement `_init_db` every start → `schema_meta` fast path; PHI lazy-load
→ background pre-warm; fixed sleeps → readiness polling), Windows pre-window blocking OIDC
(window-first + existing rebuild-with-token flow), and Android recomposition
(`@Immutable` annotations over the already-identity-preserving `Canvas.apply`).
**B — Comment hygiene** (excludes `apple-clients/` per clarification): file-purpose
headers everywhere, docstrings as the only in-code documentation, all other comments
removed except senior-dev-rationale lines and functional directives; enforced by a new
stdlib checker whose *mechanical* rules become a CI step. Delivered as two sequential PRs
(perf, then hygiene). Full decision log: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.11 (backend, production image; local `.venv` 3.13);
ES5 vanilla JS + CSS (webrender static, no build step); Python 3.10+/PySide6
(windows-client); Kotlin 2.0.x + Jetpack Compose (android-client)

**Primary Dependencies**: Existing only — FastAPI, `websockets`, psycopg2 (its bundled
`psycopg2.pool` is newly *used*, not newly *added*), the OpenAI-compatible client via
`llm_config/client_factory.py` (streaming mode of the same client), `python-jose`,
`cryptography`, astralprims (unchanged), presidio/spacy (existing, pre-warmed). Vendored
static assets added: Inter + JetBrains Mono woff2 font files (assets, not libraries).
**Zero new third-party runtime dependencies.**

**Storage**: PostgreSQL via `shared/database.py::_init_db()` idempotent guarded
migrations. Deltas: new `schema_meta` table (fast-path revision marker); one-time
`tool_overrides` per-kind backfill promoted from per-render to a guarded migration;
supporting index(es) only if post-fix measurement demands. Rollback documented in
[data-model.md](data-model.md).

**Testing**: pytest + pytest-asyncio in-image (both CI invocations) with the new
event-loop-blocking detector fixture and query-count assertions; windows-client pytest
(offscreen Qt harness, launch-timing test); android-client JVM unit tests (reducer
reference-identity) + Compose compiler stability reports; protocol drift guards in all
three stacks; new `scripts/comment_policy.py --check` CI step (mechanical rules only).

**Target Platform**: Linux server container (backend); Windows 10+ desktop (PySide6);
Android phone/tablet/foldable. `apple-clients/` untouched.

**Project Type**: Multi-target — one backend + three first-party clients (web served by
backend, Windows, Android).

**Performance Goals**: Spec SC-001..SC-011 — surfaces: indicator ≤100ms, content ≤400ms
P95 warm; first login → example cards ≤1.5s warm / ≤3.0s cold; repeat-visit static
transfer <100KB, zero external-origin pre-paint requests; zero sync DB on the event loop;
non-model turn overhead ≤1.0s P95; Windows window ≤1s; `_init_db` fast path ≤250ms; boot
≥40% faster vs. captured baseline; 20-concurrent P95 ≤2× single-user.

**Constraints**: Constitution V (no new runtime deps), IX (idempotent guarded migrations +
rollback), XI (all CI gates green), XII (cross-client consistency incl. the v2.6.0
theming/layout clauses — same font families, wire protocol unchanged or strictly additive,
parity/drift suites green); no-build ES5 web layer stays; single-instance orchestrator
stays; fail-closed auth/permissions/audit/PHI semantics unchanged; permission decisions
never cached beyond one turn.

**Scale/Scope**: Single orchestrator instance; SC-011 sets the concurrency bar
(20 simultaneous surface opens). Hygiene scope ≈837 files / ~43.7k LOC.

## Open defaults (overridable — adopted after the question dialog was declined)

- **D1 PR strategy**: two sequential PRs — perf (this branch), then hygiene
  (follow-up branch after merge). See research.md R18.
- **D2 Comment CI gate**: permanent CI check enforces only mechanically-decidable rules
  (headers present, no banners, no commented-out code, no spec markers, no directive
  loss); rationale-comment judgment stays in human review. See research.md R17.

Say the word and either default flips; tasks.md is phased to keep both easy to change.

## Constitution Check

*GATE: evaluated against constitution v2.6.0 — pre-research and re-checked post-design.*

| Principle | Verdict | Notes |
|---|---|---|
| I Python backend | PASS | All backend work is Python; client work stays in each client's existing language. |
| II SDUI architecture | PASS | astralprims untouched; render stays orchestrator-owned; ROTE adaptation unchanged; upsert-first delivery + streaming reuse existing frames; no client gains a parallel UI definition. |
| III Testing ≥90% changed-code | PASS (plan) | Perf PR ships detector, query-count, timing, reducer, and launch tests alongside code. Hygiene PR is comment/docstring-only — adds no executable lines, so diff-cover has nothing uncovered to fail. |
| IV Code quality / lint | PASS | ruff from repo root stays green both PRs; hygiene sweep must not strip `noqa` (checker guards directive loss). |
| V Dependencies | PASS | Zero new third-party runtime deps: `psycopg2.pool` ships inside psycopg2; `asyncio.to_thread` is stdlib; fonts are vendored static assets; checker is stdlib and CI-side (XI carve-out, documented in PR). |
| VI Documentation | PASS | New/changed functions get docstrings (hygiene workstream enforces the standard repo-wide); contracts/ documents the new seams. |
| VII Security | PASS | Auth stays fail-closed (JWKS warm never skips validation; IdP-down = today's behavior); permission gates and audit chain semantics unchanged; permission memo is turn-scoped only; streaming carries the same rendered content over the same authenticated socket; no secrets committed (fonts are public assets). |
| VIII UX / primitives | PASS | No new primitive types; skeleton reuses existing pattern; designed-canvas morph identity preserved. |
| IX Migrations | PASS | `schema_meta` + backfill promotion + optional index ship as guarded idempotent `_init_db` deltas with documented rollback (data-model.md); fast path never skips a pending migration (revision mismatch forces full run; source-hash test forces revision bumps). |
| X Production readiness | PASS (plan) | Every SC has a verification path (CI guard or documented manual protocol + baselines); UI changes exercised on web + Windows + Android against a live backend before completion; observability added via `perf_span`. |
| XI CI | PASS | All existing gates preserved; additions (detector fixture, query-count tests, comment `--check` step) are documented CI-side tooling; production-posture boot exit-78 smoke unchanged (start.py keeps exit-code propagation). |
| XII Cross-client consistency (v2.6.0) | PASS | Same font families self-hosted (visual language unchanged); wire protocol: zero manifest changes (streaming reuses existing frames; upsert-first uses existing frames); layout parity untouched; parity/drift suites green on all three stacks is an explicit SC. |
| XIII Docs/research integrity | N/A | Product feature; baselines/measurement reports are evidence artifacts within the feature dir. |

**Violations requiring justification**: none → Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/052-perf-comment-hygiene/
├── spec.md              # Feature specification (clarified 2026-07-08)
├── plan.md              # This file
├── research.md          # Phase 0 decisions R1–R18 + baseline mandate
├── data-model.md        # Phase 1: schema_meta, memo/caches, perf log record, comment categories
├── quickstart.md        # Phase 1: measurement protocol + verification runbook
├── contracts/
│   ├── static-asset-caching.md      # versioned-immutable /static contract
│   ├── narrative-streaming.md       # reuse of existing streaming frames (no manifest delta)
│   ├── db-async-and-detector.md     # Database async facade + event-loop detector contract
│   └── comment-policy-check.md      # checker CLI + mechanical CI rules
├── checklists/requirements.md       # Spec quality checklist (passed)
├── baselines.md                     # FR-032 captured baselines (first implementation task)
└── tasks.md                         # Phase 2 output (/speckit-tasks — next step)
```

### Source Code (repository root)

```text
backend/
├── shared/
│   ├── database.py            # pool (R1), async facade (R2), schema_meta fast path (R11), backfill migration (R4)
│   ├── perf.py                # NEW — perf_span timing helper (R16)
│   ├── jwks_cache.py          # warm/refresh entry points (R8)
│   └── ui_protocol.json       # UNCHANGED (streaming reuses existing frames)
├── orchestrator/
│   ├── orchestrator.py        # register_ui pipeline (R8), _deliver_round_components upsert-first (R9),
│   │                          #   _call_llm streaming mode (R10), load_chat bulk hydration (R4),
│   │                          #   static version map + version-aware cache headers (R7), boot warm tasks (R8/R12)
│   ├── history.py             # get_recent_chats single-query (R4)
│   ├── tool_permissions.py    # merged effective-perms query, turn-scoped memo (R4/R5)
│   ├── ui_designer.py         # DEFAULT_MAX_ROUNDS 3→1 (R9)
│   └── chrome_events.py       # perf_span instrumentation (R16)
├── webrender/
│   ├── chrome/surfaces/agents.py   # ≤3-round-trip detail render (R4)
│   ├── static/client.js            # immediate connect, modal skeleton+timeout, plotly lazy-loader (R6/R7)
│   ├── static/astral.css           # @font-face self-hosted fonts (R7)
│   ├── static/fonts/               # NEW — vendored woff2 (R7)
│   └── templates/shell.html        # per-file ?v= URLs, preload links, plotly tag removed (R7)
├── personalization/phi_gate.py     # unchanged API; warmed from startup thread (R12)
├── start.py                        # readiness polling replaces sleeps (R13)
└── tests/                          # detector fixture, query-count asserts, streaming/designer/faspath tests

scripts/comment_policy.py           # NEW — hygiene checker (R17; final home may be backend/scripts/)

windows-client/astral_client/
├── app.py                     # window-first main(), worker-thread auth via existing rebuild path,
│                              #   deferred config/workspace prompts, set_components early-exit (R14)
└── tests/                     # launch-to-window timing test on offscreen harness

android-client/
├── core/src/main/kotlin/.../sdui/Component.kt      # @Immutable (R15)
├── core/src/main/kotlin/.../protocol/Messages.kt   # @Immutable on UiState-held types (R15)
├── app/src/main/kotlin/.../ui/AppViewModel.kt      # @Immutable UiState & friends (R15)
├── app/src/main/kotlin/.../ui/theme/Theme.kt       # @Immutable ThemePalette (R15)
├── app/build.gradle.kts                            # compose compiler metrics (debug) (R15)
└── app/src/test/                                   # reference-identity reducer test (R15)

.github/workflows/ci.yml       # comment_policy --check step (PR 2); detector runs inside existing test job
```

**Structure Decision**: No new top-level projects. All work lands in the existing
backend + two native client trees; the only new files are `shared/perf.py`,
`webrender/static/fonts/*`, `scripts/comment_policy.py`, and tests. `apple-clients/` is
not touched. Wire protocol manifest is not modified.

## Phase overview (execution order; detail in tasks.md)

- **Phase A0 — Baselines & instrumentation** (blocks everything): `shared/perf.py`,
  instrumentation points, event-loop detector fixture (report-only), capture
  `baselines.md` per quickstart protocol.
- **Phase A1 — Systemic backend**: pool (R1) → async facade + call-site migration (R2) →
  detector flips to enforcing → query consolidation (R4) → permission memo (R5).
- **Phase A2 — Web boot & assets**: fonts, per-file versioning + immutable headers,
  plotly lazy-load, connect-delay removal (R7); JWKS warm + register_ui pipeline (R8).
- **Phase A3 — Perceived chat latency**: upsert-first designer + 1-pass default (R9);
  narrative streaming (R10).
- **Phase A4 — Native clients**: Windows window-first (R14); Android annotations +
  metrics + identity test (R15).
- **Phase A5 — Boot**: `schema_meta` fast path (R11), PHI pre-warm (R12), start.py
  polling (R13).
- **Phase A6 — Verification**: SC sweep in dev reference env, 20-concurrency run,
  three-client live verification, production evidence report (SC-014), PR 1.
- **Phase B — Hygiene PR**: checker (R17) → per-area sweeps (backend, static JS/CSS,
  windows, android, scripts, tests) → directive-preservation + behavior-neutrality
  verification → CI `--check` wiring → PR 2.

## Complexity Tracking

> No Constitution Check violations — table intentionally empty.
