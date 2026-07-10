# Implementation Plan: Agent Catalog Overhaul, Adaptive UI Designer & Production CI

**Branch**: `029-agents-adaptive-ui-ci` | **Date**: 2026-06-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/029-agents-adaptive-ui-ci/spec.md`

## Summary

Four pillars on one branch: (1) remove six agents (email_tracker, grant_budgets, grants, linkedin, nefarious, nocodb) and their fully-mapped blast radius; (2) consolidate the three copy-paste external-service wrappers (classify, forecaster, llm_factory) into one `ml_services` agent on a shared wrapper foundation, with an idempotent migration carrying per-user scopes/overrides/credentials forward; (3) ship two plug-and-play Research & Knowledge agents (web_research, summarizer) with zero new dependencies; (4) replace the deterministic per-round UI append (orchestrator.py:2917-2936 plus fixed Analysis/Summary boilerplate) with a fail-open, feature-flagged **adaptive designer**: an LLM pass that arranges each multi-component round into a layout tree whose leaves *reference* the round's workspace components by identity (preserving refresh/pagination/supersede/provenance) and may author deterministic-id garnish — persisted in a new `workspace_layout` table, materialized server-side before ROTE adaptation and rendering. Plus a cohesive visual refresh of the no-build web render layer and a GitHub Actions pipeline (lint, full suite vs Postgres, 90% changed-code coverage, image build, boot smoke incl. exit-78 fail-closed proof, secret scan, GHCR publish on main) targeting deployment at https://sandbox.ai.uky.edu with Keycloak at https://iam.ai.uky.edu.

## Technical Context

**Language/Version**: Python 3.11+ (backend); ES5-compatible vanilla JavaScript + CSS maintained by the orchestrator render layer (`backend/webrender/static/`, no build step)
**Primary Dependencies**: Existing only — FastAPI, websockets, psycopg2, the OpenAI-compatible LLM client used by `_call_llm` (resolved through the feature-006 `llm_config.client_factory`), `shared.external_http` (egress-gated HTTP), astralprims v0.1.0 (consumed unchanged). **Zero new runtime dependencies** (Constitution V). CI-only tooling: ruff, pytest-cov, diff-cover, gitleaks action (Constitution XI carve-out, documented in PR).
**Storage**: PostgreSQL via `shared/database.py::_init_db()` idempotent startup migrations. Deltas: new `workspace_layout` table; additive `workspace_snapshot.layouts` column; one-time guarded agent-id/tool-name remap (classify/forecaster/llm_factory → ml_services); cleanup of permission rows for the six removed agent ids. Rollback documented in [data-model.md](data-model.md).
**Testing**: pytest inside the `astraldeep` container against live Postgres (default suite + module suites); new suites for ui_designer, workspace layout persistence, ml_services, web_research, summarizer, removal regression; CI runs the same suites in the built image against a postgres:17-alpine service.
**Target Platform**: Linux server container (python:3.11-slim image) behind a TLS reverse proxy at https://sandbox.ai.uky.edu; web client is the orchestrator-served no-build shell; OIDC against https://iam.ai.uky.edu.
**Project Type**: Web service (SDUI backend, orchestrator + auto-discovered agents)
**Performance Goals**: Designer adds ≤ 8 s worst-case (configurable budget, typical ≤ 3 s) only to rounds with ≥ 2 rich components; zero added latency for 0/1-component rounds; fallback path identical to today's performance.
**Constraints**: Fail-open designer (any failure → legacy append, no user-visible error); workspace identity semantics unchanged (resolve_identity/supersede/`component_action` provenance); ROTE adaptation point unchanged (adapt-then-render per socket); no SPA/frontend build (Constitution II); fail-closed production posture preserved (exit 78).
**Scale/Scope**: ~6,800 LOC removed (six agents + blast radius), ~4,900 LOC consolidated into ~2,600, two new agents (~1,400 LOC), one new orchestrator module (~600 LOC) + render/persistence touches, one CI workflow, CSS refresh. 11 agent dirs after the change (16 − 6 removed − 3 merged + 1 ml_services + 2 new).

## Constitution Check

*GATE: evaluated against constitution v2.1.0 (amended this session).*

| # | Principle | Verdict | Evidence |
|---|-----------|---------|----------|
| I | Python backend only | PASS | Designer, agents, migrations all Python; CI workflow is configuration, not backend code. |
| II | SDUI: astralprims defines → orchestrator renders → ROTE adapts | PASS | Designer composes **existing** astralprims types only; the internal `ref` node is materialized into real components *before* `rote.adapt()` and rendering, so no new primitive, no renderer contract change, no client logic. Visual refresh touches only the orchestrator render layer's own assets (permitted by II). |
| III | ≥ 90% changed-code coverage | PASS (planned) | Every new module ships a test suite; the CI gate built in this feature enforces the threshold mechanically. |
| IV | Lint enforced | PASS | ruff from repo root in CI; client.js changes kept minimal and self-consistent (no JS lint config exists in repo — noted, not introduced here). |
| V | No new third-party runtime deps | PASS | stdlib + existing clients only. CI-only tools documented per XI. |
| VI | Documentation | PASS | Docstrings on all new public functions; designer LLM contract + agent tool contracts in `contracts/`; FastAPI /docs unaffected. |
| VII | Security | PASS | New agents use `shared.external_http` (SSRF/egress gating) with size/time bounds; designer consumes only validated LLM output (same `_validate_component_tree` family, widened to the renderer registry); agent registration key enforcement applies to new agents; LinkedIn OAuth endpoints removed (attack-surface reduction); secret scan added to CI. |
| VIII | Primitives from astralprims only | PASS | Designer palette = the 26 registered renderer types; validators widened to exactly that registry — no invented types. |
| IX | Idempotent auto-migrations + rollback | PASS | All schema deltas in `_init_db()` with `IF NOT EXISTS`/guard patterns; remap/cleanup migrations guarded one-time; rollback paths in data-model.md. |
| X | Production readiness | PASS | Feature flag default-on with exact legacy behavior when off; structured designer observability; no stubs; browser-verified before done. |
| XI | CI gate set | PASS | This feature *creates* the pipeline; gate set matches XI exactly. |

**Post-design re-check (after Phase 1)**: no new violations introduced by the design; Complexity Tracking remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/029-agents-adaptive-ui-ci/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0 — decisions + alternatives (from session research)
├── data-model.md        # Phase 1 — schema deltas, migrations, rollback
├── quickstart.md        # Phase 1 — how to run/verify the feature
├── contracts/
│   ├── ui-designer-llm.md      # Designer prompt/output JSON contract + validation pipeline
│   ├── new-agent-tools.md      # web_research, summarizer, ml_services tool registries
│   └── ci-pipeline.md          # Workflow jobs, triggers, gates, image tags
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — not created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
└── workflows/
    └── ci.yml                          # NEW — Principle XI gate set + GHCR publish

backend/
├── orchestrator/
│   ├── orchestrator.py                 # MODIFIED — designer hook replaces flat append (:2917-2936);
│   │                                   #   boilerplate Analysis/Summary cards contextualized (:3159-3173, :3215-3219);
│   │                                   #   validator whitelists widened (:2087-2092, :3108-3114);
│   │                                   #   retirement error for component_action on removed agents
│   ├── ui_designer.py                  # NEW — design_round(): prompt build, LLM call, validate/repair, materialize
│   ├── workspace.py                    # MODIFIED — layout persistence (upsert_layout/live_layouts/snapshot incl. layouts)
│   ├── api.py                          # MODIFIED — LinkedIn OAuth block (:1021-1260) removed
│   └── models.py                       # MODIFIED — LinkedIn credential schema examples removed
├── webrender/
│   ├── renderer.py                     # MODIFIED — render_workspace() materializes layouts; visual classes
│   ├── templates/shell.html            # MODIFIED — visual refresh hooks
│   └── static/                         # MODIFIED — CSS token system, transitions, polish (no build step)
├── shared/
│   └── database.py                     # MODIFIED — _init_db(): workspace_layout, snapshot column,
│                                       #   ml_services remap migration, removed-agent row cleanup
├── agents/
│   ├── email_tracker/ grant_budgets/ grants/ linkedin/ nefarious/ nocodb/   # DELETED
│   ├── classify/ forecaster/ llm_factory/                                   # DELETED (merged)
│   ├── ml_services/                    # NEW — consolidated agent
│   │   ├── ml_services_agent.py
│   │   ├── mcp_server.py
│   │   ├── mcp_tools.py                # union registry (5 colliding verbs service-prefixed)
│   │   ├── _wrapper.py                 # shared external-service foundation (probe, retry, egress)
│   │   ├── classify_tools.py forecaster_tools.py llm_factory_tools.py
│   │   └── tests/
│   ├── web_research/                   # NEW — web_search, fetch_page, research_brief (+ tests/)
│   ├── summarizer/                     # NEW — summarize_url, summarize_text, compare_documents (+ tests/)
│   └── connectors/mcp_tools_runtime.py # MODIFIED — grants-1 stub registry entry replaced
├── knowledge/
│   ├── capabilities/ techniques/       # MODIFIED — grants/nefarious files deleted; classify/forecaster/
│   │                                   #   llm_factory merged into ml_services.md; new-agent files added
│   └── patterns/tool_patterns.md       # MODIFIED — grants-1 routing removed
├── qual_audit/suites/                  # MODIFIED — nefarious fixture/test usages replaced with local fixture
└── tests/                              # MODIFIED — agents/grants/ deleted; test_nefarious_delegation.py deleted;
                                        #   test_no_behavior_change.py pruned; new designer/layout/removal suites

docs/
└── production-deployment.md            # MODIFIED — GHCR pull path for sandbox.ai.uky.edu / iam.ai.uky.edu
```

**Structure Decision**: single-backend SDUI web service (existing layout). New orchestrator capability lands as a sibling module (`ui_designer.py`) following the `workspace.py` pattern; agents follow the existing plug-and-play contract (`<name>_agent.py` + `mcp_server.py` + `mcp_tools.py`); CI is repo-root `.github/workflows/`.

## Key Design Decisions (detail in research.md)

1. **Arrangement-as-overlay, never as owner.** The designed layout is a per-round tree stored in a new `workspace_layout` table. Tool components keep their `saved_components` rows, identities, and positions untouched; layout leaves are `{"type": "ref", "component_id": "..."}` nodes. Materialization substitutes live component dicts into refs at render time and stamps `attributes["data-component-id"]`, so the existing client-side morph (`[data-component-id]`) and `ui_upsert` flow keep working with **zero client changes**. Garnish components live inline in the layout JSON with deterministic `dg_*` ids.
2. **Designer runs post-round, pre-render, fail-open.** Triggered only when a round yields ≥ 2 rich top-level components (constant, documented). Uses the round's LLM credential resolution (feature-006 factory, `websocket=`), `asyncio.wait_for` budget (`UI_DESIGNER_TIMEOUT_SECONDS`, default 8), `FF_UI_DESIGNER` flag default-on. Validation: parse → type-check against the **renderer registry** (single source of truth, imported, not hand-copied) → ref existence/dedup check → repair-append of omitted components → materialize. Any failure → legacy append.
3. **Designed rounds push a full canvas `ui_render`** (the path already used by `load_chat`/`update_device`/legacy reconciliation) rather than extending `ui_upsert` with layout ops — per-socket ROTE adaptation happens exactly where it does today (orchestrator.py:5369). Non-designed rounds keep the incremental `ui_upsert` path.
4. **Tool-name collisions in the merge are resolved by service prefix.** classify and forecaster share five verb names (`submit_dataset`, `start_training_job`, `get_job_status`, `get_results`, `delete_dataset`); an MCP tool list is flat, so the merged registry prefixes exactly those ten (5×2) as `classify_*`/`forecaster_*`. All other tool names are unique and unchanged. The remap migration rewrites stored `tool_overrides` rows accordingly. (Spec FR-006 amended with this planning finding.)
5. **CI tests run inside the built image** (which already bakes spacy/presidio/SimpleITK), with the checkout bind-mounted over `/app/backend` and `DB_*` pointed at the job's postgres service — one build proves the production image AND provides the test environment. Coverage XML feeds `diff-cover --compare-branch origin/main --fail-under 90` for the changed-code gate.
6. **Boilerplate removal**: the always-"Analysis" card becomes contextual (LLM-derived round title via the existing title-summarization helper, plain markdown when short); max-turns "Summary" keeps `_generate_tool_summary` content but a contextual title; "Reasoning" collapsible unchanged; error Alerts unchanged.

## Complexity Tracking

> No constitution violations — table intentionally empty.
