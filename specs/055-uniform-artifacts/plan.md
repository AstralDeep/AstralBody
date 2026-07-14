# Implementation Plan: Uniform Cross-Device Artifacts & First-Turn Loading Contract

**Branch**: `055-uniform-artifacts` | **Date**: 2026-07-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/055-uniform-artifacts/spec.md`

## Summary

Fix the verified first-turn loading defects on all six client targets (retire the
skeleton-killing welcome-blanking frame; give welcome components stable `wel_`
identities that every client purges at turn start; close the Windows typed-send
skeleton gap) and evolve workspace components into a uniform artifact system:
streams bridge into persisted component identities for progressive rendering
(additive `component_id` on `ui_stream_data` + persist-on-terminal), the adaptive
designer becomes origin-independent (natives receive materialized designed
canvases post-commit), workspace edits reconcile live on natives (8 ack frames
promoted from ignored to handled), every component carries a server-stamped
`provenance` field rendered on all targets, and artifacts gain component-scoped
refine with bounded version history plus CSV/HTML export and fail-closed
snapshot share links. All decisions and their evidence: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.11 (backend, production image; local `.venv` 3.13);
ES5 vanilla JS + CSS (webrender static, no build step); Python 3.10+/PySide6
(windows-client); Kotlin 2.0.21 + Jetpack Compose (android-client); Swift/SwiftUI
(apple-clients — AstralCore/AstralApp/AstralWatch)

**Primary Dependencies**: Existing only — FastAPI, `websockets`, psycopg2, the
OpenAI-compatible client via `llm_config/client_factory.py` (component refine is
an LLM turn under the user's 054 provider config), astralprims (consumed
UNCHANGED — no new primitive types; `wel_` ids ride `Primitive.id`, `provenance`
is an orchestrator-stamped dict field), existing `audit`, `workspace`,
`stream_manager`, `ui_designer`, `phi_gate` modules, stdlib `csv`/`secrets`/
`hashlib` for export + share. **Zero new third-party runtime dependencies on any
surface** (Constitution V; zero Swift packages, Android existing libs only).

**Storage**: PostgreSQL via `shared/database.py::_init_db()` idempotent guarded
migrations. Deltas: new `component_version` table (bounded refine/restore
history, retain 5), new `share_grant` table (snapshot renditions, hashed tokens,
revocation). Rollback documented in [data-model.md](data-model.md). No changes
to `saved_components`/`workspace_layout`/`workspace_snapshot` schemas.

**Testing**: pytest inside the `astraldeep` container (full suite + new unit/
integration tests); ruff from repo root on host/CI; per-client drift guards —
backend `test_ui_protocol_manifest.py`, Windows `tests/` (offscreen Qt), Android
`ProtocolManifestTest`/`VocabularyParityTest` (Gradle), Apple
`ManifestDriftTests` (`swift test --package-path apple-clients/AstralCore`);
an all-055-flags-off suite variant proving SC-009 byte-equivalence; live
verification on every affected client per Constitution X.

**Target Platform**: Linux server (docker image) + web (evergreen browsers) +
Windows 10/11 desktop + Android + iOS/macOS/watchOS

**Project Type**: Multi-client server-driven-UI system (one backend, five client
codebases consuming one wire contract)

**Performance Goals**: Loading feedback visible ≤200 ms after send on every
target (SC-001); first-vs-Nth-query feedback variance <100 ms (SC-002); first
streamed partial visible in under half of tool runtime median (SC-003);
cross-device edit reconcile ≤2 s (SC-005); designer path adds zero latency to
flat delivery (upsert-first preserved; native designed render arrives
post-commit)

**Constraints**: Escape-by-default rendering non-negotiable; ROTE host bounds
are security bounds (interactivity stripping survives); the four workspace
identity rules + `~N` ordinal grammar preserved exactly; out-of-turn empty
`ui_render` == authoritative clear preserved (pinned client tests);
commit-on-done native canvas lifecycle preserved; watch no-re-speak preserved;
`chat_status done` remains the universal skeleton-resolution safety net;
designer fail-open (flat components first, tool output never rewritten);
PHI gate fail-closed on share; all new behavior flag-gated with off ==
byte-identical wire behavior

**Scale/Scope**: ~6 backend modules touched (orchestrator delivery/welcome/
stream_manager/workspace adjacency, webrender renderer + client.js, 2 new API
route groups), 2 new tables, 1 manifest additive field + 2 accept actions,
4 client codebases (dispositions + reducers + 2 renderer additions each),
~35 functional requirements across 5 independently-shippable user stories

## Constitution Check

*GATE: evaluated against Constitution v2.6.0 before Phase 0; re-checked after Phase 1.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Python backend | PASS | All backend work Python; client work stays in each client's sanctioned language |
| II | SDUI architecture | PASS | astralprims defines (UNCHANGED — no new primitive types; `wel_` uses existing `Primitive.id`, `provenance` is a stamped dict field); orchestrator renders (footer/badge, export HTML); ROTE adapts (provenance preserved-field rule). No SPA. Chrome untouched |
| III | 90% changed-code coverage | PLANNED | New paths (welcome ids, stream bridge, refine, export/share, designer delivery) each ship with unit + integration tests; CI diff-cover gate enforces |
| IV | Lint | PLANNED | ruff (backend), existing client lint stacks; ES5 discipline in client.js |
| V | Zero new third-party deps | PASS | Verified per-surface in research.md; stdlib only for CSV/tokens |
| VI | Documentation | PLANNED | New wire fields/actions documented in contracts/ + `ui_protocol.json` description; renderer behaviors documented per target |
| VII | Security | PASS | Refine/restore/export re-enter existing permission+audit gates; share is PHI-gated fail-closed, token-hashed, revocable, audited; no auth changes; no credential paths touched |
| VIII | UX via astralprims | PASS | All new visuals compose existing primitives/fields |
| IX | Idempotent migrations + rollback | PLANNED | 2 additive tables via `_init_db`, guarded, rollback in data-model.md, representative-dataset evidence required in PR |
| X | Production readiness / verify every client | PLANNED | Quickstart defines per-target live verification; no stubs; observability: structured logs for stripper hits, stream-bridge fallbacks, share mint/refusals |
| XI | CI gates | PLANNED | All 8 gates + the flags-off variant job; manifest edit in same PR keeps drift guards green |
| XII | Cross-client consistency | PASS (improves) | D7 REMOVES an existing XII(b) violation (layout keyed on originating client). Every wire/disposition change lands on all in-scope clients same-PR; watch divergences (verbs ignored, no refine affordance) are declared ROTE-capability carve-outs recorded in spec FR-020 |
| XIII | Docs/research integrity | N/A | Product feature |

**Initial gate: PASS** (no violations to justify — Complexity Tracking empty).
**Post-Phase-1 re-check: PASS** — design artifacts introduce no new projects,
no new dependency, no parallel definitions; the only vocabulary changes are one
additive field + two accept actions, handled via the sanctioned manifest process.

## Project Structure

### Documentation (this feature)

```text
specs/055-uniform-artifacts/
├── spec.md              # Feature specification (committed)
├── plan.md              # This file
├── research.md          # Phase 0 — 12 decisions with evidence + alternatives
├── data-model.md        # Phase 1 — entities, 2 new tables, rollback
├── quickstart.md        # Phase 1 — per-story verification walkthrough
├── contracts/
│   ├── wire-contract.md # WS frame/field/action + manifest + disposition deltas
│   └── rest-endpoints.md# Export + share HTTP contracts
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── orchestrator/
│   ├── welcome.py                 # US1: wel_ id + component_id stamped on the tree
│   ├── orchestrator.py            # US1: retire blanking SEND only (≈1497-1499,
│   │                              #      _ws_welcome bookkeeping stays); fix the
│   │                              #      all-tools-denied no-done path (≈4120);
│   │                              # US2: streaming-tool auto-subscribe at dispatch,
│   │                              #      handle_agent_end persist-on-terminal,
│   │                              #      _tag_source provenance stamp (≈4009),
│   │                              #      leak stripper extraction (≈4152, 4334);
│   │                              # US3: designer origin gate removal (≈7450),
│   │                              #      ONE coalesced post-done designed render
│   │                              #      (inline, progress-suppressed, stale-guarded,
│   │                              #      speak=False threaded incl. _push_canvas);
│   │                              # US4: component_refine/_restore handlers
│   │                              #      (beside component_action ≈7599)
│   ├── stream_manager.py          # US2: identity at subscribe (≈168, 467),
│   │                              #      component_id on frame builders (≈676, 1193),
│   │                              #      narrative boundary-buffered markdown
│   ├── workspace.py               # US4: version archive hook on force-pinned upsert
│   ├── artifact_versions.py       # NEW — component_version store (US4)
│   ├── artifact_share.py          # NEW — share_grant store + PHI-gated mint (US5)
│   └── api.py                     # US5: /api/export/*, /api/share*, /share/{token}
├── rote/
│   └── adapter.py                 # US1: fallback-ladder + grid-collapse rebuilds
│                                  #      preserve id/component_id (watch purge dep)
├── webrender/
│   ├── renderer.py                # US4: provenance footer reads stamped field;
│   │                              # US5: standalone canvas export document wrapper
│   └── static/client.js           # US1: SELECTIVE wel_ purge at sendChat +
│                                  #      components-keyed empty state; US2:
│                                  #      mergeStream reuses applyUpsert morph
│                                  #      (unwrap + Plotly purge); US4: refine
│                                  #      affordance
├── shared/
│   ├── ui_protocol.json           # additive field + 2 accept actions (same PR)
│   ├── feature_flags.py           # 6 new flags (D12 table)
│   └── database.py                # _init_db: component_version + share_grant
└── tests/                         # unit + integration + flags-off variant

windows-client/astral_client/
├── app.py                         # US1: _send arms skeleton, idle-hint suppression,
│                                  #      wel_ purge; US3: verb-ack handling
├── renderer.py                    # US4: provenance badge; refine affordance
└── protocol_manifest.py           # dispositions: verbs handled, new actions

android-client/ (core Wire/Canvas + app AppViewModel/renderers)
│                                  # US1: wel_ purge at send + history-skip;
│                                  # US2: stream frames as component updates;
│                                  # US3: verb acks; US4: provenance badge + refine
└── core/.../ProtocolManifest.kt   # dispositions

apple-clients/ (AstralCore Dispositions/Frames + AstralApp AppModel/ComponentView)
│                                  # mirrors Android changes; watch: wel_ purge on
│                                  # first in-turn upsert ONLY (verbs/refine stay
│                                  # out of watch scope)
└── AstralCore/.../Dispositions.swift

specs/044-native-client-parity/parity-matrix.md   # rows for every disposition change
```

**Structure Decision**: No new projects/packages beyond two small backend modules
(`artifact_versions.py`, `artifact_share.py`) that follow the existing
one-store-module pattern (`session_store.py`, `offline_grant.py`). All client
work lands inside the existing per-client structures; the shared vocabulary
changes flow through `ui_protocol.json` exactly once.

## Implementation phasing (maps to /speckit-tasks)

1. **US1 first-turn contract** (server welcome ids + blanking-frame retirement
   behind `FF_FIRST_TURN_CONTRACT`; web/Windows/Android/Apple/watch purge +
   arming fixes; pinned-contract regression tests) — independently shippable.
2. **US2 progressive artifacts** (`FF_STREAM_ARTIFACTS` bridge, persist-on-
   terminal, narrative markdown buffering, stripper extension) — independent.
3. **US3 parity** (`FF_DESIGNER_ALL_DEVICES` + verb-ack promotions ×3 clients +
   parity matrix) — depends on nothing above but touches the most clients.
4. **US4 refine + provenance** (`component_version`, refine/restore actions,
   provenance stamp + per-target badge) — provenance is independent; refine
   builds on identity pinning.
5. **US5 export/share** (`share_grant`, REST routes, PHI-gated mint) — last,
   fully independent.

Cross-cutting last: flags-off equivalence job, manifest/disposition sweep check,
per-client live verification (quickstart.md), observability review.

## Complexity Tracking

*No Constitution Check violations — table intentionally empty.*
