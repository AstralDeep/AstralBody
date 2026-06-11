# Phase 0 Research: Agent Catalog Overhaul, Adaptive UI Designer & Production CI

**Date**: 2026-06-11 · All file:line references verified against the working tree at branch point (`main` @ 20d5215).

## R1. Where the deterministic UI structure lives (what we're replacing)

**Finding**: Tool outputs are never composed. `handle_chat_message` flat-appends every tool result's components in dispatch order (orchestrator.py:2917-2936) into one workspace upsert batch (:2938-2942). Fixed boilerplate: `Card(title="Analysis")` on every final turn (:3159-3164, :3167-3173), `Collapsible(title="Reasoning")` when the model emits reasoning (:2851-2857), `Card(title="Summary")` on max-turns exit (:3215-3219, `_generate_tool_summary` :3645-3649), bare error `Alert`s (:4119-4124, :4309-4311). The web canvas wrapper is a fixed vertical stack (`webrender/renderer.py:628`). A stale comment at :4117-4118 references collapsible batching that no longer exists.

**Decision**: Intercept after the round's components are collected and tagged (post `_tag_source`, pre `_send_or_replace_components`) — this is the single choke point through which every rich round flows.

## R2. Designer architecture

**Decision**: New module `backend/orchestrator/ui_designer.py`; hybrid reference-leaf model; arrangement stored as overlay (`workspace_layout` table); garnish inline with deterministic `dg_<sha1(chat|layout_key|index)[:12]>` ids; materialize-then-adapt-then-render.

**Rationale**:
- The feature-028 identity model computes identity only for TOP-LEVEL components of an upsert batch (`workspace.py:resolve_identity` :76-95). Wrapping tool outputs inside a designer-authored composite would strip their identities: future single-source supersede (:180-192) would append duplicates instead of morphing, and `component_action`/pagination (orchestrator.py:5155-5257) would lose their one-(agent,tool,params)-per-row provenance. Reference leaves keep every tool component a real workspace row.
- Materializing refs into component dicts *before* `rote.adapt()` (orchestrator.py:5369) keeps ROTE and the renderer completely unaware of the designer — Constitution II chain untouched, and watch/voice degradation rules apply to the materialized tree exactly as to any component list.
- Stamping `attributes["data-component-id"]` on materialized leaves uses astralprims' existing free-form `attributes` escape hatch (merged at top level by every renderer), so the no-build client's morph logic (`client.js` `[data-component-id]` handling) works unchanged — zero client-side delta for correctness (visual refresh is separate).

**Alternatives considered**:
- *Full composition (LLM rewrites/merges outputs)* — rejected: breaks identity/provenance per above; highest hallucination surface; user explicitly chose hybrid.
- *Layout-only (no garnish)* — rejected: user chose hybrid; garnish (headline metrics, narrative) is what makes rounds feel designed rather than rearranged.
- *Storing the arrangement as a workspace component row* — rejected: it would become a supersede-eligible identity owner and re-introduce the wrapping problem.
- *Extending `ui_upsert` with layout ops* — rejected for v1: full canvas `ui_render` on designed rounds reuses an existing, ROTE-correct path (`load_chat`/`update_device`/`_reconcile_legacy_replacement` all do this); incremental layout patching is an optimization with real protocol cost.

## R3. Designer LLM contract and validation

**Finding**: The closest template is `_combine_components_llm` (orchestrator.py:1938-2124): JSON-only system prompt, temperature 0.1, markdown-fence strip + regex JSON extraction (:2066-2081), recursive `_validate_component_tree` (:2126-2158). Critically, its hand-written palette (:2087-2092) and the final-response parser whitelist (:3108-3114) are NARROWER than the authoritative renderer registry (`webrender/renderer.py:590-599`, 26 types: container, text, button, input, param_picker, card, table, list, alert, progress, metric, code, image, grid, tabs, divider, collapsible, bar_chart, line_chart, pie_chart, plotly_chart, color_picker, theme_apply, file_upload, file_download, audio); unknown types are silently rewritten to `container` (:2139-2141).

**Decision**: The designer (and both existing validators) derive their allowed-type set from the renderer registry by import — one source of truth (FR-020). Output contract: `{"layout": [<node>...]}` where a node is either `{"type": "ref", "component_id": "..."}` or a primitive dict (containers carry `children`/`content`). Validation pipeline: JSON extraction (reuse the proven fence/regex approach) → structural validation → type validation against registry ∪ {ref} → ref existence + dedupe (first occurrence wins) → omission repair (append missing round components at the end) → garnish id stamping. Full contract in [contracts/ui-designer-llm.md](contracts/ui-designer-llm.md).

**Rationale**: every failure mode in the Edge Cases section maps to one pipeline stage; repair-append guarantees FR-018's "nothing dropped" without ever blocking on the LLM being perfect.

## R4. Designer trigger, budget, credentials, observability

**Decision**: Trigger at ≥ 2 rich top-level components in the round (constant `MIN_DESIGN_COMPONENTS = 2`); `asyncio.wait_for` with `UI_DESIGNER_TIMEOUT_SECONDS` (default 8); `FF_UI_DESIGNER` env flag default-on (same `_env_flag` pattern as the ten existing FF_*); LLM resolved via the feature-006 `client_factory` with the round's websocket (per-user creds when configured, operator default otherwise) — unlike `_combine_components_llm` which pins operator default (websocket=None), because the designer acts within a user conversation; audited under the existing `llm_call` event class; structured logs `ui_designer.invoked|designed|fallback{reason}|latency_ms`.

**Alternatives**: per-device design passes (rejected — ROTE is the single adaptation mechanism, Constitution II); designing single-component rounds (rejected — pure latency tax); queuing late designs (rejected — a late layout arriving after the user moved on is worse than the append).

## R5. Persistence, snapshots, rehydration

**Finding**: `WorkspaceManager.upsert` → `saved_components` (workspace.py:142-226); per-turn `workspace_snapshot` rows (orchestrator.py:2946-2953, workspace.py:247-268) power the read-only timeline; `load_chat` re-renders `workspace.live_components` (orchestrator.py:1358-1367); `update_device` re-renders the full workspace on profile change (:1679-1712); chat deletion cascades.

**Decision**: New `workspace_layout` table (chat_id, layout_key, position, layout JSONB, timestamps; UNIQUE(chat_id, layout_key); layout_key `ly_<turn-scoped hash>`). `render_workspace` gains a layouts parameter: arrangements render in position order with claimed components materialized in place; unclaimed components (pre-029 rounds, fallback rounds) render in their own position order as today. `workspace_snapshot` gains an additive nullable `layouts` JSONB column; timeline rendering passes historical layouts through the same materializer. Chat deletion deletes layout rows. Rollback: drop table/column — components are never owned by layouts, so dropping them degrades cleanly to today's flat canvas (documented in data-model.md).

## R6. Agent removal blast radius (verified, exhaustive)

Hard breaks that MUST be fixed in the same change as the deletions:
1. `backend/orchestrator/api.py:1075` and `:1138` import `agents.linkedin.linkedin_api`; the whole generic OAuth block (authorize/callback/status, :1021-~1260) is LinkedIn-only → delete with the agent, plus `models.py:302-304` credential schema examples.
2. `backend/tests/agents/grants/` — whole package path-loads `agents.grants.*` → delete.
3. `backend/tests/test_nefarious_delegation.py:28` imports `agents.nefarious.mcp_tools` → delete.
4. `backend/qual_audit/suites/conftest.py:57-59` `nefarious_tool_registry` fixture + uses in `test_tool_poisoning.py` (TP-001 :21, TP-006 :92-96) → replace with a local intentionally-malicious fixture registry defined inside qual_audit (the *tests* of tool-poisoning defenses stay; only their dependence on a shipped malicious agent goes).
5. `backend/tests/test_no_behavior_change.py:34-43` — prune the six entries (ImportError currently degrades to skip; entries must go so the harness stays honest).
6. Knowledge: delete `knowledge/capabilities/{grants,nefarious}.md`, `knowledge/techniques/{grants,nefarious}.md`; remove grants-1 routing from `knowledge/patterns/tool_patterns.md:13,24`.
7. `backend/agents/connectors/mcp_tools_runtime.py:20` hardcoded `{"agent_id": "grants-1"}` stub → re-point at a surviving agent.
8. Cosmetic: `credential_manager.py:101` NOCODB docstring example; `.claude/settings.local.json:6,9` stale test allowlist entries; CLAUDE.md 011 references (regenerated by agent-context script); `.env.example` LINKEDIN_* block.
9. Runtime rows: `agent_ownership`/`agent_scopes`/`tool_overrides` rows for the six ids are seeded by `start.py:51-70`, not SQL files → idempotent cleanup migration (FR-003). `MAX_AGENTS` self-adjusts (start.py:72-75). No references in seeds/, docker-compose, Makefile, Dockerfile, docs/, README.
10. Old-transcript `component_action` against a removed agent currently raises agent-not-found deep in dispatch → add explicit retirement guard with audit record (FR-004).

## R7. Consolidation design (classify + forecaster + llm_factory → ml_services)

**Finding**: Identical architecture triplet: per-user URL+API-key `card_metadata` credentials, identical `_credentials_check`, identical mcp_server retry shim (classify/mcp_server.py:18-19 == llm_factory/mcp_server.py:18-19), all on `shared.external_http`. Tool-name collision: classify ∩ forecaster = {submit_dataset, set… no — exactly: submit_dataset, start_training_job, get_job_status, get_results, delete_dataset} (5 names).

**Decision**: One agent dir `backend/agents/ml_services/` (agent id `ml_services-1`, service name "ML Services") with `_wrapper.py` (shared probe/retry/egress foundation) and three tool modules merged into one registry. The five colliding verbs are exposed twice with service prefixes (`classify_submit_dataset`…, `forecaster_submit_dataset`…); all other names unchanged (classify: set_column_types, get_ml_options, propose_training_config, get_output_log; forecaster: set_column_roles; llm_factory: list_models, chat_with_model, create_embedding, transcribe_audio; shared internal `_credentials_check` dispatches per-bundle). Migration remaps agent ids in agent_ownership/agent_scopes/tool_overrides/chats.agent_id and rewrites the ten prefixed tool names in tool_overrides. Knowledge capabilities/techniques files for the three merge into `ml_services.md` with per-service sections. Existing three test suites relocate to `agents/ml_services/tests/` and run against the merged registry.

**Alternatives**: generic `service=` parameter on shared verbs (rejected — changes input schemas, worse LLM routing); keeping three agents on one shared module (rejected — user chose full merge; three port slots and three picker entries remain).

## R8. New agents (Research & Knowledge pack)

**Decision — web_research**: tools `web_search` (keyless DuckDuckGo HTML endpoint parsed with stdlib `html.parser`; optional per-user/operator search-provider credential bundle checked first), `fetch_page` (via `shared.external_http`, 1 MB / 15 s bounds, HTML→text extraction), `research_brief` (search → fetch top N → LLM synthesis with the same per-session OpenAI-client pattern `general` already uses (general/mcp_tools.py:880-925) → Card brief + Table of cited sources + Tabs per sub-topic). Never fabricates: brief cites only fetched URLs; search failure → actionable error Alert.
**Decision — summarizer**: tools `summarize_url`, `summarize_text`, `compare_documents`; input cap with explicit truncation notice component; output Tabs (TL;DR / Key points / Notable quotes), comparison as side-by-side Grid of Cards + differences Table.
**Rationale (popularity evidence)**: research + summarization lead all three surveyed ecosystems — wshobson/agents `search-specialist` (~36.6k★ pack), ClawHub's most-installed search skill + bundled official `summarize` (OpenClaw ~190k★), Hermes Agent's built-in web search/extraction. Sources logged in the session research record.
**Alternatives**: briefing/RSS, productivity, data/finance packs — deferred by user selection; GitHub agent (189K ClawHub installs) rejected for mandatory per-user OAuth (violates plug-and-play).

## R9. CI pipeline shape

**Finding**: No `.github/` exists. ruff is not in the image; ruff.toml lives at repo root and is NOT copied into the image (lint must run on the runner from repo root). Default suite = 1265 tests (backend/tests, 2 marked `integration` need a live orchestrator); module suites = +316 tests (audit/, llm_config/, orchestrator/, onboarding/, personalization/, scheduler/, dreaming/). audit tests hard-require Postgres; 12 backend/tests files skip without it. Image bakes `en_core_web_lg` (~600 MB env) — installing the dep tree on a bare runner duplicates the Dockerfile; running tests in the built image does not. `assert_production_posture()` exits 78 on placeholder/missing secrets when `ASTRAL_ENV` ≠ development. Probes: `/healthz`, `/readyz`. Repo remote: github.com/AstralDeep (PR history) → GHCR namespace from `${{ github.repository }}`.

**Decision**: Single workflow `ci.yml`, jobs: **lint** (runner py3.11, `pip install ruff`, `ruff check .`); **build** (buildx, GHA cache, `load:` for downstream jobs); **test** (postgres:17-alpine service; run both pytest invocations inside the built image with the checkout mounted over `/app/backend`, `DB_HOST` to the service, `ASTRAL_ENV=development`, `-m "not integration"`; produce `coverage.xml` via pytest-cov); **coverage-gate** (`diff-cover coverage.xml --compare-branch origin/main --fail-under 90`, vacuous pass when no Python lines changed); **smoke** (boot image vs postgres → poll `/healthz` + `/readyz`; then boot with production posture + placeholder secrets → assert exit code 78); **secret-scan** (gitleaks action); **publish** (main only, needs all gates; ghcr.io/<repo>:sha-<commit> + :latest via docker/login + metadata actions, `permissions: packages: write`). Concurrency group per ref. Full job contract in [contracts/ci-pipeline.md](contracts/ci-pipeline.md).

**Alternatives**: installing requirements.txt on the runner (rejected — duplicates the image's heavy native deps and drifts from production); pytest in compose (rejected — services + mounted-checkout image run is simpler and cache-friendly); repo-wide coverage threshold (rejected — constitution III measures changed code; repo-wide would either block on legacy code or water down the gate).

## R10. Visual refresh scope

**Finding**: Web target = `webrender/templates/shell.html` + `webrender/static/` (no-build, ES5 client.js) + per-primitive HTML in `renderer.py` (escape-by-default via `esc()`); chrome surfaces in `webrender/chrome/`.

**Decision**: Introduce a CSS custom-property token system (type scale, spacing, semantic colors, elevation, radii, motion durations) in the static stylesheet; restyle the 26 primitive renderers' existing class hooks (adding classes where needed, never changing structure/behavior contracts); component-arrival/update transitions via CSS only, gated by `prefers-reduced-motion`; shell/chrome polish (top bar, canvas/chat panels, scrollbars, focus rings). No client.js behavior changes beyond what morphing already does. Verified per-device through ROTE profiles in the browser (viewport overrides at rote/capabilities.py:74-81 make TABLET/MOBILE testable by viewport width).

## R11. Boilerplate replacement (FR-027)

**Decision**: Final-turn narrative still goes to the chat target, but: when rich components were parsed from the final response, the chat card title derives from the response's first heading or a one-line LLM title (existing `summarize_chat_title`-style helper) instead of the constant "Analysis"; short text-only responses render as plain markdown Text without a wrapping card; max-turns exit keeps `_generate_tool_summary` content under a contextual title. Designer never re-renders reasoning (the existing "Reasoning" collapsible remains the single disclosure).
