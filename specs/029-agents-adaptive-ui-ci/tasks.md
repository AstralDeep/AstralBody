# Tasks: Agent Catalog Overhaul, Adaptive UI Designer & Production CI

**Input**: Design documents from `/specs/029-agents-adaptive-ui-ci/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: REQUIRED — Constitution III (90% changed-code coverage) and spec FR-005/FR-010/FR-016/SC-009 explicitly demand suites. Test tasks are included per story.

**Organization**: Grouped by user story; US1 (adaptive designer) is the MVP. US2/US3/US4/US5 are independently deliverable increments.

## Path Conventions

Single SDUI backend: `backend/` at repo root; feature tests in `backend/tests/` and per-module `tests/` dirs; CI at `.github/workflows/`. Everything executes inside the `astralbody` container (sync via `make sync-backend`).

---

## Phase 1: Setup

**Purpose**: Baseline verification so every later diff is attributable.

- [ ] T001 Record pre-change baseline: run both pytest invocations in the container and `ruff check .` from repo root; capture the registered agent list (ports 8003-8018 agent cards) and the exact `agent_id` strings for classify/forecaster/llm_factory and the six removal targets from the live `agent_ownership` table (needed by the T020/T034 migrations); save findings to specs/029-agents-adaptive-ui-ci/baseline.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema + single-source palette that US1 (and US2's migrations) build on.

- [ ] T002 Add `workspace_layout` table and additive `workspace_snapshot.layouts` JSONB column to `_init_db()` in backend/shared/database.py per data-model.md (idempotent IF NOT EXISTS / guarded ALTER; chat-deletion cascade hooked where saved_components rows are cleared)
- [ ] T003 [P] Export the authoritative palette from backend/webrender/renderer.py (`PRIMITIVE_RENDERERS` keys) via a small accessor (e.g. `allowed_primitive_types()`) and widen BOTH narrower validator whitelists — `_combine_components_llm` VALID_TYPES (backend/orchestrator/orchestrator.py:2087-2092) and the final-response parser whitelist (:3108-3114) — to import it (FR-020); delete the stale collapsible-batching comment at :4117-4118
- [ ] T004 [P] Schema tests: new table/column exist after boot, idempotent re-run safe, snapshot round-trips layouts, chat deletion clears layout rows — backend/tests/test_workspace_layout_schema.py

**Checkpoint**: Foundation ready — user stories can proceed (US1 next; US2-US5 may run in parallel after this point).

---

## Phase 3: User Story 1 — Adaptive interface per chat round (Priority: P1) 🎯 MVP

**Goal**: Multi-tool rounds render as designed arrangements (reference leaves + garnish), fail-open to legacy append, with identity/refresh/pagination/timeline intact and ROTE untouched.

**Independent Test**: quickstart.md "See the adaptive designer work" — designed round appears for a ≥2-component prompt; pagination/refresh morph in place; `FF_UI_DESIGNER=false` and simulated LLM failure reproduce legacy behavior exactly; timeline and chat re-open restore designed state.

- [ ] T005 [US1] Create backend/orchestrator/ui_designer.py: prompt builder (user request + per-component digests + canvas digest + imported palette + layout guidance), JSON extraction (reuse fence/regex approach from `_combine_components_llm`), validation pipeline (structure → types vs registry ∪ {ref} → ref existence/dedupe → omission repair-append), deterministic `dg_*` garnish id stamping, `materialize()` substituting refs and stamping `attributes["data-component-id"]` — full contract in contracts/ui-designer-llm.md
- [ ] T006 [US1] Layout persistence in backend/orchestrator/workspace.py: `upsert_layout(chat_id, layout_key, layout, position)`, `live_layouts(chat_id)`, claim-conflict pruning (a component_id claimed by at most one live layout), snapshot capture including layouts, timeline read path returning historical layouts
- [ ] T007 [US1] Orchestrator integration in backend/orchestrator/orchestrator.py: at the post-`_tag_source` choke point (:2917-2936) — upsert components first (identities assigned), then when `FF_UI_DESIGNER` ∧ ≥2 rich components ∧ not timeline mode, call `ui_designer.design_round` under `asyncio.wait_for(UI_DESIGNER_TIMEOUT_SECONDS, default 8)` with the feature-006 client_factory (websocket-scoped); on success persist layout + push full-canvas `ui_render` per socket (existing ROTE path); on any failure log `ui_designer.fallback{reason}` and run today's `_send_or_replace_components` flat path unchanged
- [ ] T008 [US1] Materialized canvas rendering: `render_workspace(components, layouts)` in backend/webrender/renderer.py renders arrangements in position order with claimed components in place and unclaimed components after, preserving `astral-component`/`data-component-id` wrappers; wire `load_chat` (orchestrator.py:1358-1367), `update_device` (:1679-1712), and `_reconcile_legacy_replacement` to pass live layouts
- [ ] T009 [US1] Timeline + canvas-context integration in backend/orchestrator/orchestrator.py and backend/webrender/chrome/surfaces/workspace_timeline.py: snapshots store layouts (T006), timeline view materializes historical layouts read-only; canvas-context block (:2673-2686) keeps listing every component row (layouts add/hide nothing) — verify and adjust wording only if needed
- [ ] T010 [US1] Boilerplate contextualization (FR-027) in backend/orchestrator/orchestrator.py: replace constant `Card(title="Analysis")` (:3159-3173) with contextual title (first heading of response or one-line LLM title helper; short text-only responses render as bare markdown Text); max-turns `Card(title="Summary")` (:3215-3219) gets contextual title over `_generate_tool_summary` content; "Reasoning" collapsible untouched
- [ ] T011 [P] [US1] Unit tests for ui_designer: parse/validate/repair matrix (unknown type→container, unknown ref dropped, duplicate ref first-wins, omitted components repair-appended, ERROR refusal, empty layout, garnish id determinism, materializer stamping) — backend/tests/test_ui_designer.py
- [ ] T012 [P] [US1] Persistence + rendering tests: layout upsert/claim-pruning/live_layouts; render_workspace arrangement order, unclaimed fallthrough, data-component-id preservation; snapshot/timeline layout round-trip — backend/tests/test_workspace_layout.py
- [ ] T013 [P] [US1] Integration tests: designer round end-to-end with stubbed LLM (designed render contains all round component_ids), timeout→fallback, flag-off parity, single-component round skips designer, pagination/`component_action` on a referenced component morphs in place under an arrangement — backend/tests/test_ui_designer_integration.py
- [ ] T014 [US1] Run quickstart designer scenarios in the container against the running orchestrator; verify ROTE degradation by viewport (TABLET/MOBILE widths) and logs (`ui_designer.invoked|designed|fallback`)

**Checkpoint**: US1 delivers the MVP — designed rounds, fail-open, identity intact.

---

## Phase 4: User Story 2 — Trustworthy, consolidated agent catalog (Priority: P2)

**Goal**: Six agents gone with zero dangling references; classify/forecaster/llm_factory merged into ml_services with settings carried forward; retirement guard for historical artifacts.

**Independent Test**: quickstart.md "Verify the catalog" — agent-card sweep shows the expected set; grep finds no removed-agent references; former tools answer through ml_services; old-transcript refresh yields retirement message.

- [ ] T015 [US2] Delete agent directories backend/agents/{email_tracker,grant_budgets,grants,linkedin,nefarious,nocodb}/ and out-of-dir test artifacts backend/tests/agents/grants/ and backend/tests/test_nefarious_delegation.py
- [ ] T016 [US2] Remove the LinkedIn OAuth flow from backend/orchestrator/api.py (:1021-~1260 — authorize/callback/status endpoints + linkedin_api imports) and the LINKEDIN_* credential schema examples from backend/orchestrator/models.py (:302-304); remove the LINKEDIN_* block from .env.example
- [ ] T017 [US2] Replace the `nefarious_tool_registry` fixture in backend/qual_audit/suites/conftest.py (:57-59) with a local intentionally-malicious in-suite registry and re-point test_tool_poisoning.py (TP-001 :21, TP-006 :92-96); prune the six removed entries from backend/tests/test_no_behavior_change.py (:34-43)
- [ ] T018 [P] [US2] Knowledge cleanup: delete backend/knowledge/{capabilities,techniques}/{grants,nefarious}.md; remove grants-1 routing lines from backend/knowledge/patterns/tool_patterns.md (:13,24); fix the hardcoded grants-1 stub in backend/agents/connectors/mcp_tools_runtime.py (:20); fix the NOCODB docstring example in backend/orchestrator/credential_manager.py (:101); drop stale entries from .claude/settings.local.json (:6,9)
- [ ] T019 [US2] Retirement guard (FR-004): in `component_action`/pagination re-execution (backend/orchestrator/orchestrator.py:5155-5257), when the source agent id is unregistered and in the retired set, return `Alert(variant="warning")` retirement message and record a `workspace.action_denied` audit event with reason="agent_retired"
- [ ] T020 [US2] Removed-agent row cleanup migration in backend/shared/database.py `_init_db()`: guarded DELETEs of agent_ownership/agent_scopes/tool_overrides rows for the six retired ids (exact ids from T001 baseline); audit/chats/saved_components explicitly untouched per data-model.md
- [ ] T021 [US2] Create backend/agents/ml_services/ per contracts/new-agent-tools.md: `_wrapper.py` (shared probe/retry/egress foundation), `classify_tools.py`/`forecaster_tools.py`/`llm_factory_tools.py` (ported logic, five colliding verbs service-prefixed), `mcp_tools.py` union TOOL_REGISTRY, `mcp_server.py`, `ml_services_agent.py` (agent_id ml_services-1, three optional credential bundles in card_metadata)
- [ ] T022 [US2] ml_services identity remap migration in backend/shared/database.py `_init_db()`: guarded rewrite of agent_ownership/agent_scopes/tool_overrides/chats.agent_id from the three old ids to ml_services-1 (keep-first ownership, UNION scopes/overrides) + tool_overrides tool-name remap for the ten prefixed verbs; verify credential key-name carry-forward assumption from data-model.md against credential_manager storage and remap if agent-scoped
- [ ] T023 [US2] Merge knowledge files into backend/knowledge/capabilities/ml_services.md and backend/knowledge/techniques/ml_services.md (per-service sections from the three predecessors), then delete the six originals; delete backend/agents/{classify,forecaster,llm_factory}/
- [ ] T024 [P] [US2] Relocate + adapt the three agents' test suites into backend/agents/ml_services/tests/ (registry completeness incl. prefixed names, per-bundle `_credentials_check` verdicts, schema byte-compat vs T001 baseline, wrapper retry/egress behavior)
- [ ] T025 [P] [US2] Removal regression tests: catalog excludes retired ids after boot, migrations idempotent (run twice), retirement guard returns Alert + audit row, no module under backend/ imports removed packages (AST/grep test) — backend/tests/test_agent_retirement.py
- [ ] T026 [US2] Full-suite run in container; fix any dangling references the suite or `ruff check .` surfaces; verify agent-card sweep matches the expected post-029 set

**Checkpoint**: Catalog is the post-029 set; migrations proven idempotent.

---

## Phase 5: User Story 3 — Production confidence via CI (Priority: P2)

**Goal**: The Principle XI gate set runs on every PR/push; main publishes a GHCR image; sandbox deployment path documented.

**Independent Test**: spec US3 scenarios — intentionally bad PR fails lint/test/coverage distinctly; clean main push produces a pullable tagged image; smoke proves healthz/readyz and exit-78.

- [ ] T027 [US3] Create .github/workflows/ci.yml per contracts/ci-pipeline.md: jobs lint / build (buildx + GHA cache, image artifact) / test (postgres:17-alpine service, both pytest invocations inside the built image with checkout mounted over /app/backend, `-m "not integration"`, pytest-cov → coverage.xml artifact) / coverage-gate (diff-cover --compare-branch origin/main --fail-under 90, vacuous pass on no Python changes) / smoke (healthz+readyz in dev posture; production-posture boot with placeholder secrets asserts exit code exactly 78) / secret-scan (gitleaks-action, full-history checkout) / publish (main only, needs all gates, ghcr sha-<commit> + latest, permissions packages:write); concurrency per ref
- [ ] T028 [P] [US3] Add .gitleaks.toml allowlisting the repo's intentional test placeholders (dev-token, test fixture secrets, .env.example placeholders) so the scan gates on real leaks only
- [ ] T029 [P] [US3] Update docs/production-deployment.md with the "Deploying to sandbox.ai.uky.edu" section per contracts/ci-pipeline.md (GHCR pull, compose image override, PUBLIC_BASE_URL/BACKEND_PUBLIC_URL=https://sandbox.ai.uky.edu, KEYCLOAK_AUTHORITY=https://iam.ai.uky.edu/realms/<realm>, FORWARDED_ALLOW_IPS, /ws proxy upgrade, redirect URI registration) and cross-link docs/keycloak-realm-settings.md
- [ ] T030 [US3] Validate the workflow: `actionlint`-style review pass + dry-run the test job's command sequence locally in the container (same mounts/env) to prove the in-image invocation works before the first push

**Checkpoint**: CI contract complete; first real run happens on push/PR of this branch.

---

## Phase 6: User Story 4 — Research & Knowledge agents (Priority: P3)

**Goal**: web_research and summarizer register automatically, work keyless, produce rich cited/structured output, and degrade with actionable errors.

**Independent Test**: quickstart.md "New-agent smoke prompts" with zero extra configuration.

- [ ] T031 [P] [US4] Create backend/agents/web_research/ per contracts/new-agent-tools.md: web_search (DDG HTML via shared.external_http + stdlib html.parser; optional SEARCH_API_URL/KEY bundle preferred), fetch_page (1 MB/15 s bounds, HTML→text), research_brief (search→fetch ≤5→LLM synthesis via per-session OpenAI-client pattern; cites only fetched URLs), no-fabrication failure Alerts; plus knowledge/capabilities+techniques files
- [ ] T032 [P] [US4] Create backend/agents/summarizer/ per contracts/new-agent-tools.md: summarize_url/summarize_text (Tabs TL;DR/Key points/Quotes, 24k-char cap with truncation Alert), compare_documents (Grid of Cards + differences Table); plus knowledge files
- [ ] T033 [P] [US4] Test suites backend/agents/web_research/tests/ and backend/agents/summarizer/tests/: registry/schema contract, HTML parsing fixtures, egress-gate refusal of private hosts, truncation notice, failure-path Alerts, LLM-stubbed brief/summary structure (≥90% changed-code coverage)
- [ ] T034 [US4] Register-and-run verification in the container: both agents auto-discovered under AGENT_API_KEY enforcement, smoke prompts from quickstart.md produce the contracted components, audit rows recorded

**Checkpoint**: Research & Knowledge pack live.

---

## Phase 7: User Story 5 — Visually appealing web interface (Priority: P3)

**Goal**: Cohesive modern visual system across shell, chrome, and all 26 primitives — CSS/static-asset work only, no build step, no framework.

**Independent Test**: spec US5 scenarios in a real browser; repo inspection shows no new client tooling.

- [ ] T035 [US5] Introduce a CSS custom-property token system (type scale, spacing, semantic colors incl. dark-friendly palette, elevation, radii, motion durations) in backend/webrender/static/ stylesheet(s) and apply to the shell layout in backend/webrender/templates/shell.html (top bar, panels, scrollbars, focus rings)
- [ ] T036 [US5] Restyle the 26 primitive renderers' markup hooks in backend/webrender/renderer.py (classes only — no structural/behavioral changes; tables, cards, metric tiles, charts, tabs, alerts, forms) and the chrome surfaces in backend/webrender/chrome/; add component-arrival/update transitions gated by `prefers-reduced-motion`
- [ ] T037 [P] [US5] Renderer contract tests still green + snapshot-style assertions for the class hooks (no behavioral regressions: actions, param_picker submit, pagination footer, upload/download) — extend backend/tests test files covering webrender
- [ ] T038 [US5] Browser pass at BROWSER/TABLET/MOBILE viewport widths over the quickstart scenarios; fix visual regressions; confirm reduced-motion honored

**Checkpoint**: Visual refresh complete.

---

## Phase 8: Polish & Cross-Cutting

- [ ] T039 Full verification in container: both pytest invocations green, `ruff check .` clean from repo root, migrations re-run idempotently on restart, quickstart executed top-to-bottom
- [ ] T040 [P] Docstrings/documentation sweep for all new public functions (Constitution VI); update CLAUDE.md feature-029 summary block (agent-context script) and README agent list if present
- [ ] T041 Final live verification: restart stack from a clean image build (`make up`), open http://localhost:8001/ in a real browser, execute all five user-story independent tests, capture evidence for the PR
- [ ] T042 Open PR to main with: constitution v2.1.0 note, CI-tooling declaration (ruff/pytest-cov/diff-cover/gitleaks — Constitution V/XI), destructive-migration approval note (removed-agent scope rows), and spec/plan links; confirm the CI pipeline runs green end-to-end on the PR

---

## Dependencies & Execution Order

```text
Phase 1 (T001) ─► Phase 2 (T002-T004) ─► US1 (T005-T014)  ── MVP
                                      ├► US2 (T015-T026)  [parallel with US1; T020/T022 build on T001 ids]
                                      ├► US3 (T027-T030)  [parallel; full green needs US1/US2 merged]
                                      ├► US4 (T031-T034)  [parallel]
                                      └► US5 (T035-T038)  [parallel; best after US1 so designed layouts get styled]
US1-US5 ─► Phase 8 (T039-T042)
```

- Within US1: T005-T006 [P with each other], then T007 → T008 → T009/T010; tests T011-T013 [P] after their targets; T014 last.
- Within US2: T015-T018 [P-ish, distinct files], T019-T020 after T015; T021 → T022 → T023 → T024; T025-T026 last.
- US3's coverage gate only proves itself on the PR (T042).

## Implementation Strategy

MVP = Phase 1-3 (US1). Each subsequent story is an independently shippable increment; recommended landing order matches priority (US1 → US2 → US3 → US4 → US5) but US2-US5 may interleave. Container is the single test environment (`make sync-backend` after every batch of edits).
