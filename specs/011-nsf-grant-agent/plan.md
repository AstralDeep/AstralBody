# Implementation Plan: NSF TechAccess AI-Ready America Grant Writing Agent

**Branch**: `011-nsf-grant-agent` | **Date**: 2026-05-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/011-nsf-grant-agent/spec.md`

## Summary

Add an NSF TechAccess: AI-Ready America (NSF 26-508) specialization to the existing `grants` agent in [backend/agents/grants/](../../backend/agents/grants/) so that the same agent (one entry in the agent picker, one MCP server, one A2A endpoint) can also produce LOI text, full-proposal Section 1–5 drafts, gap-checks against NSF review criteria, supplemental artifacts (Letters of Collaboration, Data Management Plan, and Mentoring Plan when budget includes postdocs/grad students), program-officer question lists, page-budget prioritization advice, and standalone deadline citations for the University of Kentucky Coordination Hub proposal — without regressing its current charter for general grant search and CAAI-alignment work. Per `/speckit.clarify`, the capability is delivered as a *merge into the existing `grants` agent* (not a new sibling agent), draft text inherits the platform's existing data-handling posture (no special retention or provider rules), partner roster / PI list / draft state inherit the existing agent's memory posture (no new persistence), the scope covers the full NSF 26-508 / TechAccess family (Hub + National Coordination Lead + AI-Ready Catalyst Award Competitions), and per-response latency inherits platform defaults. The technical approach is: (1) extend the agent's `description` and `skill_tags` to surface TechAccess capabilities, (2) add a new knowledge module `nsf_techaccess_knowledge.py` that encodes the solicitation rules, exact required section headings, the five Hub responsibilities, NSF-required metrics, the AI literacy continuum, and the Kentucky partnership architecture, (3) add new MCP tools to `mcp_tools.py` for drafting/refining/gap-checking sections and producing supplemental artifacts, and (4) ship unit + integration tests at the constitution-required coverage. No database schema changes, no new third-party dependencies, no new frontend primitives.

## Technical Context

**Language/Version**: Python 3.11+ (backend; per Constitution Principle I and existing `grants` agent module).
**Primary Dependencies**: Existing — `shared.base_agent.BaseA2AAgent`, `shared.protocol.MCPRequest/MCPResponse`, `shared.primitives` (Text, Card, Alert, Table, List_, Tabs, MetricCard), `agents.grants.mcp_server.MCPServer`, `agents.grants.mcp_tools.TOOL_REGISTRY`, `agents.grants.caai_knowledge`, the project's existing OpenAI-compatible LLM client (used by `_call_llm`). **No new third-party libraries** (Constitution Principle V).
**Storage**: N/A. No new tables, no schema changes. Cross-session memory inherits the existing `grants` agent's posture per Clarifications Q3.
**Testing**: pytest (existing). New tests live under `backend/tests/agents/grants/` alongside existing grants-agent tests; coverage measured/enforced in CI per Constitution Principle III (≥90%).
**Target Platform**: Linux server (existing AstralBody backend container, Docker / Docker Compose).
**Project Type**: Backend agent module within a multi-agent web service. Frontend impact: zero new primitive components; only the `grants` agent's `description` string changes, which surfaces in the existing agent picker UI without code changes on the React side.
**Performance Goals**: Inherit platform defaults per Clarifications Q5. No NSF-specific latency target. Agent responses stream via the existing orchestrator; long-form section drafts are expected to take whatever the underlying LLM takes.
**Constraints**: (a) MUST NOT regress existing `grants` agent behaviors for non-TechAccess sessions (per FR-001 and Clarifications Q2); (b) MUST NOT add new third-party dependencies (Constitution V) — all new code uses libraries already present; (c) MUST NOT introduce schema changes (Constitution IX is N/A here, since no DB work); (d) drafts and gap-checks MUST go through existing platform LLM client and existing data-handling posture (per Clarifications Q1); (e) MUST keep all new strings and structures readable by both the LLM (system-prompt-injectable) and humans (developer maintenance).
**Scale/Scope**: One UK proposal team, ~5–15 named users, ~2 months of active drafting (LOI June 16, 2026; full proposal July 16, 2026; internal deadline ~July 9, 2026). Estimated working volume per session: 1–10 tool calls, draft outputs ~500–4000 tokens each, occasional whole-section regenerations up to ~8000 tokens. After award decisions, the capability remains available but lower-volume.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Primary Language (Python) | ✅ Pass | All new backend code is Python 3.11+ inside the existing `backend/agents/grants/` module. |
| II. Frontend Framework (Vite + React + TS) | ✅ Pass | No frontend code changes. The existing agent picker reads `description` and `skill_tags`; updates flow without TS changes. |
| III. Testing Standards (≥90% coverage) | ✅ Pass | New unit tests cover the new knowledge module's structural integrity (every required section heading, every Hub responsibility, every NSF-required metric, every AI-Ready level, every KY partner). New integration tests cover each new MCP tool end-to-end via the existing `MCPServer.process_request` path. Existing grants-agent tests must continue to pass to demonstrate no regression. |
| IV. Code Quality (PEP 8 / ruff) | ✅ Pass | New Python modules ship with ruff-clean code and Google-style docstrings. |
| V. Dependency Management | ✅ Pass | No new third-party libraries. All new code reuses `shared.base_agent`, `shared.primitives`, `shared.protocol`, `requests` (already present), and the project's existing LLM client. |
| VI. Documentation | ✅ Pass | New tool functions have Google-style docstrings; each tool's MCP `input_schema` doubles as machine-readable contract; the FastAPI `/docs` surface picks up the agent endpoints automatically. |
| VII. Security | ✅ Pass | No new auth surfaces. Tools inherit Keycloak/RFC 8693 token posture from `BaseA2AAgent`. Inputs (free-text user prompts and pasted draft text) are passed through to the existing LLM client without new external network calls. |
| VIII. User Experience (primitive components only) | ✅ Pass | All UI output is built from existing primitives (Text, Card, Alert, List_, Tabs); no new primitives are introduced. |
| IX. Database Migrations | ✅ Pass (N/A) | No schema changes. The feature adds no tables, columns, indexes, or enums. |
| X. Production Readiness | ✅ Pass | Tools include structured logging on failure; no stubs/mocks/hard-coded values at merge time; tests cover golden path, edge cases (off-topic redirect, prohibited supplemental, missing required heading), and error conditions; configuration flows through existing env-var / settings path. UI behavior is exercised against the running backend before merge per Constitution X. |

**Gate result: PASS.** No violations. Complexity Tracking section below is empty.

## Project Structure

### Documentation (this feature)

```text
specs/011-nsf-grant-agent/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (logical entities → Python structures in nsf_techaccess_knowledge.py)
├── quickstart.md        # Phase 1 output (developer + proposal-team usage)
├── contracts/           # Phase 1 output (MCP tool contracts: input_schema + output expectations)
│   ├── draft_proposal_section.md
│   ├── draft_loi.md
│   ├── refine_section.md
│   ├── gap_check_section.md
│   ├── draft_supplemental_artifact.md
│   ├── draft_program_officer_questions.md
│   ├── prioritize_page_budget.md
│   ├── cite_deadlines.md
│   └── techaccess_scope_check.md
├── checklists/
│   └── requirements.md  # produced by /speckit.specify
└── tasks.md             # produced later by /speckit.tasks
```

### Source Code (repository root)

```text
backend/
├── agents/
│   └── grants/                          # ← merged target (Clarifications Q2)
│       ├── grants_agent.py              # MODIFIED: description + skill_tags broadened to include NSF 26-508 / TechAccess
│       ├── mcp_server.py                # UNCHANGED: routing layer is generic
│       ├── mcp_tools.py                 # MODIFIED: new TOOL_REGISTRY entries for the 9 TechAccess tools
│       ├── caai_knowledge.py            # UNCHANGED
│       └── nsf_techaccess_knowledge.py  # NEW: solicitation rules, sections, hub responsibilities, metrics, KY partners, AI literacy levels, framing rules
└── tests/
    └── agents/
        └── grants/
            ├── test_grants_agent.py             # existing (must still pass)
            ├── test_nsf_techaccess_knowledge.py # NEW: structural integrity of the knowledge module
            ├── test_techaccess_tools.py         # NEW: per-tool unit tests (input validation, refusal paths, output shape)
            └── test_techaccess_integration.py   # NEW: end-to-end via MCPServer.process_request

frontend/
└── (no changes — agent picker inherits the updated `description` automatically)
```

**Structure Decision**: Single web-service project with an existing multi-agent backend. The TechAccess capability is delivered by extending the existing `backend/agents/grants/` module: one new knowledge file, one modified tools file, one minor edit to the agent class's `description` and `skill_tags`, and three new test modules. No frontend changes. No DB changes. This matches the merge-into-existing-grants-agent decision recorded in Clarifications Q2.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

(none — all gates passed)
