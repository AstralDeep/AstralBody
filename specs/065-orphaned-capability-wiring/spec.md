# Feature Specification: Orphaned 033-Capability Wiring Triage

**Feature Branch**: `065-orphaned-capability-wiring`
**Created**: 2026-06-17
**Status**: RESOLVED — all 19 modules + companions wired into the runtime (decision: wire all)
**Input**: Code review of all work from spec 033 onward. The final "Batch 1–6" wave (PR #80) plus a few earlier branches landed 19 capability modules that were fully built and unit-tested but **never imported by production code**. This spec inventories each one so a human can decide, per module: **delete** (preserved in git history, re-add when the feature is real) or **keep + wire** into the running product.

## Resolution (2026-06-17) — all wired

Per the decision to "wire it all up", every orphaned module and companion below was integrated into the live runtime, each **behind a feature flag (default OFF/safe), fail-open, with real integration tests** (drive the actual path + assert behavior, plus a flag-OFF no-op assertion). Default product behavior is unchanged until a flag is flipped. Flags are documented in `.env.example`. Validated: **3,625 tests pass, ruff clean.**

| Module | Wired into | Flag |
|---|---|---|
| supervisor (C-S5) | `execute_single_tool` intent gate + drafted-answer review (`turn_hooks`) | `FF_RUNTIME_SUPERVISOR` |
| hitl (C-S11) | `execute_single_tool` confirmation gate | `FF_HITL_HIGHRISK` |
| flow_patterns (C-S1) | chat-loop per-turn tool budget (`turn_hooks`) | `FF_FLOW_PATTERNS` |
| ledger (C-N7) | chat-loop task ledger (`turn_hooks`) | `FF_DUAL_LEDGER` |
| asi_coverage (C-S12) | chat-loop plan-deviation (`turn_hooks`) | `FF_ASI_COVERAGE` |
| skill_memory (C-N10) | chat-loop recipe match/induce (`turn_hooks`, per-user store) | `FF_SKILL_MEMORY` |
| moa (C-N9) | final-answer candidate panel + aggregate (`turn_hooks`) | `FF_MOA_DEBATE` |
| fanout (C-N8) | parallel-dispatch batching (`turn_hooks`) | `FF_ASYNC_FANOUT` |
| mas_defense (C-S14) | scan agent outputs in the loop (`turn_hooks`) | `FF_MAS_DEFENSE` |
| living_memory (C-M6/7/8) | `MemoryTools` read/write + repository seams | `FF_MEMORY_TEMPORAL/FORGETTING/PERSONA` |
| project_scope (C-U9) | `memory_item.project_id` + repo/tools filter | `FF_PROJECT_MEMORY` |
| sleeptime (C-N11) | dreaming sweep idle precompute | `FF_SLEEPTIME_COMPUTE` |
| pulse (C-U8) | `pulse` chrome surface + topbar icon | `FF_PULSE_DIGEST` |
| objectives (C-D3) | UI-designer ranking bias | `FF_ADAPTIVE_OBJECTIVES` |
| lod (C-D10) | ROTE `adapt` level-of-detail pre-pass | `FF_LOD_LADDER` |
| a11y_audit (C-D9) | UI-designer lint stage | `FF_UI_DESIGNER_A11Y` |
| draft_archive (C-N4) | agentic-creation codegen + self-test skip | `FF_DRAFT_ARCHIVE` |
| agent_eval (C-N5) | feedback quality job trajectory scoring | `FF_AGENT_EVAL` |
| voice/aom (C-D4/D5) | `target_for_profile` render-target dispatch | `FF_NATIVE_TARGETS` |
| transaction_token.mint (C-S8) | `mint_action_token` + `authorize_action` ui_event | (uses `TXN_TOKEN_KEY`) |
| model_router on-device (C-D6) | `_last_route_ondevice` surfaced in `_call_llm` | `FF_MODEL_ROUTER` |
| repository seams | now driven by living_memory | — |

The original per-module triage tables below are retained as the design record.

---

## Overview

Features 044–063 each merged one 033 capability and wired it into the runtime — those are live and excluded here. The problem is the modules below: each defines an `*_enabled()` flag and a complete, tested implementation, but **no orchestrator / agent / render code imports a single symbol from them**. They are imported only by their own test file. So with the flag on or off, the running product behaves identically — the integration the docstrings promise ("integration lives in the orchestrator behind FF_…", "the actual execution lives in the dreaming sweep", "so the UI designer can rank…") was never written.

This is dead scaffolding, not broken code: the implementations are high-quality, pure, and dependency-free. The decision is product/roadmap, not correctness — hence this triage doc rather than a unilateral delete.

### Scope of the dead weight

| Cluster | Modules | Prod LOC | Test LOC |
|---|---|---|---|
| Self-improving multi-agent | 10 | 2,139 | 2,095 |
| Living-memory extensions | 5 | 908 | 807 |
| ROTE / render extensions | 4 | 964 | 1,101 |
| **Total** | **19** | **4,011** | **3,825** |

### How to triage (please edit this file)

For each module below, set its **Decision** line to one of:

- `delete` — remove the module + its test (git history keeps it; re-introduce when the feature has a real driver).
- `wire` — keep it and integrate it into the runtime. I'll then build the integration in a follow-up (the multi-agent and security modules need design + security review first).

Mark each one, add a note if useful, and I'll execute the deletes immediately and schedule the wires. Verification evidence (sole importer per module) is in the appendix.

---

## Cluster A — Self-improving multi-agent orchestration

These ten form one designed subsystem: their own docstrings cross-reference each other by capability ID (debate → fan-out → dual-ledger → trajectory-eval on the capability side; flow-patterns → supervisor → HITL → MAS-defense → ASI-coverage on the security side). **None of the nine `FF_*` flags is read by any production code.** Wiring any of these changes agent-execution semantics and is security-sensitive; `mas_defense` only has a purpose once the *other* multi-agent flows exist. Recommend **delete** unless there is a concrete near-term multi-agent product driver.

| Module | LOC | Cap | What it does | Intended (unbuilt) hook | Wire effort/risk |
|---|---|---|---|---|---|
| `orchestrator/moa.py` | 212 | C-N9 | Mixture-of-Agents debate + answer aggregation | chat answer path, `FF_MOA_DEBATE` | High / High |
| `orchestrator/fanout.py` | 149 | C-N8 | Decompose a task → parallel fresh-context sub-agents | orchestrator task layer, `FF_ASYNC_FANOUT` | High / High |
| `orchestrator/ledger.py` | 190 | C-N7 | Dual task/progress ledger for replan & self-correction | multi-step chat loop, `FF_DUAL_LEDGER` | High / High |
| `orchestrator/draft_archive.py` | 338 | C-N4 | Evolutionary archive of past drafts + surrogate scorer to skip self-tests | agentic-creation codegen, `FF_DRAFT_ARCHIVE` | Med / Med |
| `orchestrator/agent_eval.py` | 142 | C-N5 | Trajectory-evaluation metrics + pass^k | offline eval / daily quality job (no flag) | Med / Low |
| `orchestrator/supervisor.py` | 276 | C-S5 | Intent-alignment ingress/egress scan around tools | `execute_single_tool`, `FF_RUNTIME_SUPERVISOR` | High / High |
| `orchestrator/flow_patterns.py` | 258 | C-S1 | Classify turn flow → constrain tool budget/routing | chat loop, `FF_FLOW_PATTERNS` | Med / High |
| `orchestrator/hitl.py` | 201 | C-S11 | Human confirmation for high-risk actions | `execute_single_tool` pre-dispatch, `FF_HITL_HIGHRISK` | Med / High |
| `orchestrator/mas_defense.py` | 128 | C-S14 | Sign/verify inter-agent messages + scan | inter-agent messaging (needs A-flows), `FF_MAS_DEFENSE` | Med / High |
| `orchestrator/asi_coverage.py` | 245 | C-S12 | Plan-deviation detection + OWASP-ASI coverage table | deviation → chat loop; Part B is static doc-as-code | Med / Med |

**Notes for triage**
- `agent_eval.py` is mislabeled `Feature 035` in its header (branch drift) and its `score_trajectory` docstring says "six metrics" but returns five. It is also the cheapest to wire (offline eval into the existing daily quality job) and the lowest risk — the one Cluster-A module worth considering for **wire**.
- `asi_coverage.py` Part B (`ASI_RISKS`/`COVERAGE`/`coverage_ratio`/`uncovered_risks`) is a hardcoded OWASP→capability table: `coverage_ratio()` can only ever return `1.0` and `uncovered_risks()` only ever `[]`. It is documentation encoded as code; if kept, belongs in a `.md`, not a module.

**Decision (Cluster A):**
- `moa.py` — ☐ delete ☐ wire — ____
- `fanout.py` — ☐ delete ☐ wire — ____
- `ledger.py` — ☐ delete ☐ wire — ____
- `draft_archive.py` — ☐ delete ☐ wire — ____
- `agent_eval.py` — ☐ delete ☐ wire — ____
- `supervisor.py` — ☐ delete ☐ wire — ____
- `flow_patterns.py` — ☐ delete ☐ wire — ____
- `hitl.py` — ☐ delete ☐ wire — ____
- `mas_defense.py` — ☐ delete ☐ wire — ____
- `asi_coverage.py` — ☐ delete ☐ wire — ____

---

## Cluster B — Living-memory extensions

The shipped memory path (reconcile/guard/multi-signal scoring/linking/PageRank) is live and excluded here. These five extend it with mechanics that have no caller. Wiring most of them touches memory correctness, the dreaming sweep, schema, and (for `pulse`) a new chrome surface. Recommend **delete** for now; revisit when the memory roadmap actually calls for forgetting / persona / projects / digests.

| Module | LOC | Cap | What it does | Intended (unbuilt) hook | Wire effort/risk |
|---|---|---|---|---|---|
| `personalization/living_memory.py` | 234 | C-M6–M9 | Temporal validity, principled forgetting, evolving persona, provenance/unlearning | `memory_tools` read/write + dreaming sweep; needs the 4 `repository.py` seams (see Cluster D-companions) | Med-High / High |
| `dreaming/sleeptime.py` | 297 | C-N11 | Idle-time anticipatory precompute (predict next questions) | dreaming sweep calls it during idle | Med-High / Med |
| `orchestrator/skill_memory.py` | 160 | C-N10 | Induce reusable "recipes" from successful tool sequences + match | chat loop, `FF_SKILL_MEMORY` | Med / Med |
| `dreaming/pulse.py` | 136 | C-U8 | "Morning digest" + conversational scheduling from the sweep | a Pulse chrome surface + sweep hook (neither exists) | Med / Med |
| `personalization/project_scope.py` | 81 | C-U9 | Project-scoped memory partitioning | a `project_id` column + filter in `memory_tools`/`repository` (not added) | Med / Med |

**Decision (Cluster B):**
- `living_memory.py` — ☐ delete ☐ wire — ____
- `sleeptime.py` — ☐ delete ☐ wire — ____
- `skill_memory.py` — ☐ delete ☐ wire — ____
- `pulse.py` — ☐ delete ☐ wire — ____
- `project_scope.py` — ☐ delete ☐ wire — ____

---

## Cluster C — ROTE / render extensions

Two are fully orphaned; two are *registered* renderers that are unreachable because **every production `render_for_target(...)` call passes the literal `"web"`** (`orchestrator.py:1945,6956`, `stream_manager.py:1189`) — the `voice`/`aom` targets are never dispatched. `voice` is additionally redundant: the live VOICE path already collapses components to text in `rote/adapter.py`. `aom` has no AOM client to consume it.

| Module | LOC | Cap | What it does | Intended (unbuilt) hook | Wire effort/risk |
|---|---|---|---|---|---|
| `rote/objectives.py` | 376 | C-D3 | Score candidate UI arrangements by device-fit objectives | `ui_designer` ranking (never imports it) | Low-Med / Low |
| `rote/lod.py` | 221 | C-D10 | Level-of-detail content ladder per device | `rote/adapter`, `FF_LOD_LADDER` | Low-Med / Low |
| `webrender/aom.py` | 232 | C-D5 | Accessibility-Object-Model render target | a `render_for_target("aom")` dispatch + an AOM consumer | Low / Low (but no consumer) |
| `webrender/voice.py` | 135 | C-D4 | VOICE-target SSML renderer | `render_for_target("voice")` for voice devices | Low / Low (redundant w/ adapter text-collapse) |

**Decision (Cluster C):**
- `objectives.py` — ☐ delete ☐ wire — ____
- `lod.py` — ☐ delete ☐ wire — ____
- `aom.py` — ☐ delete ☐ wire — ____
- `voice.py` — ☐ delete ☐ wire — ____

---

## Cluster D — Companion dead code inside otherwise-wired files

These are not whole modules but dead symbols that exist **only** to support a Cluster A/B/C capability. Their fate follows their companion's decision; listed so a `delete` decision also removes its tail and a `wire` decision keeps it.

| Symbol | File | Companion | If companion deleted |
|---|---|---|---|
| `set_validity`, `record_recall`, `get_persona`, `set_persona` | `personalization/repository.py` | `living_memory.py` (C-M6/7/8) | delete the 4 methods |
| `mint()` + the authorize half of `verify()` | `orchestrator/transaction_token.py` | the `require_token` policy effect (C-S8) — see note | see note |
| `can_use_ondevice`, `_has_browser_ai`, `RouteDecision.ondevice` | `orchestrator/model_router.py` | on-device routing lane (C-D6) — computed then ignored | delete the on-device lane |
| `a11y_audit()` | `webrender/a11y.py` | an a11y CI/designer gate (C-D9) — landmark roles ARE wired | delete `a11y_audit` (or wire as CI gate) |

**Note on `transaction_token` — this one is a live bug, not just dead code.** The verify/consume half *is* wired into the policy engine (`orchestrator.py:4932`), but `mint()` has **no production caller**, so a `require_token` policy rule can only ever **DENY** — there is no path to issue a valid token. This is fail-closed (safe) but means the "authorize this exact call" capability is non-functional, contradicting the module's own docstring. **Decision needed:** ☐ build the confirm/mint path (makes `require_token` usable) ☐ leave as deny-only and document it ☐ remove `require_token` support entirely.

**Also flagged (I will clean these directly — no decision needed):** `taint.TaintTracker.known()` and `rote/fallback.ladder_for()` are dead helpers in wired modules with no future hook; `ui_designer.py` `archetype_bonus(ref_types=…)` and `score_arrangement/should_adopt(allowed_types=…)` are dead parameters ("accepted for forward-compatibility; unused today"). `policy._SEED_RULES` is empty, so the (default-on) policy engine enforces nothing until `POLICY_RULES` is configured — intended, but worth a one-line doc.

---

## Verification method

Each module was confirmed orphaned by three independent passes plus a per-cluster deep review:
1. Whole-tree import grep excluding `**/tests/**` and `test_*` → zero hits.
2. `importlib` / `__import__` / `import_module` dynamic-import grep → zero hits.
3. Distinctive public-symbol grep (every public function/class name) in non-test code → zero real hits.
4. Entry-point/scheduler check (`start.py`, `scheduler/runner.py`, `dreaming/*`, `__init__.py` re-exports) → none reference these modules.

## Appendix — sole importer per module (evidence)

```
moa.py            tests/test_moa.py:8           supervisor.py    tests/test_supervisor.py:21
fanout.py         tests/test_fanout.py:8        flow_patterns.py tests/test_flow_patterns.py:19
hitl.py           tests/test_hitl.py:20         ledger.py        tests/test_ledger.py:8
mas_defense.py    tests/test_mas_defense.py:13  agent_eval.py    tests/test_agent_eval.py:18
asi_coverage.py   tests/test_asi_coverage.py:20 draft_archive.py tests/test_draft_archive.py:8
skill_memory.py   tests/test_skill_memory.py:12 living_memory.py personalization/tests/test_living_memory.py:13
project_scope.py  personalization/tests/test_project_scope.py:11
pulse.py          tests/test_pulse.py:13        sleeptime.py     tests/test_sleeptime.py:8
lod.py            tests/test_lod.py:19          objectives.py    tests/test_objectives.py:19
voice.py          registry.py (TARGET_RENDERERS["voice"], never dispatched) + tests/webrender/test_voice_renderer.py
aom.py            registry.py (TARGET_RENDERERS["aom"], never dispatched) + tests/webrender/test_aom.py
```

## Out of scope (handled separately, no decision needed)

Extraneous-comment cleanup (spec-ID/`Wave-N`/`Feature 0xx` narration, academic citations, decorative banners, "no new dependency" marketing, restate-the-obvious lines) across the **genuinely-wired** 033 files is being done directly as part of this review and is not part of this triage.
