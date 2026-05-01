# Phase 0 Research: NSF TechAccess Grant Writing Agent

**Status**: Complete. No `NEEDS CLARIFICATION` items remained from `/speckit.clarify`. The five questions resolved during clarification are summarized in [spec.md → Clarifications](spec.md#clarifications). This document captures the codebase / framework research that informs the design choices in [plan.md](plan.md).

## Decisions

### Decision 1: Merge into existing `grants` agent rather than create a new sibling agent

**Decision**: Add the NSF TechAccess specialization to the existing [backend/agents/grants/](../../backend/agents/grants/) module. No new agent module under `backend/agents/`.

**Rationale**:
- The user explicitly chose this in Clarifications Q2 ("Merge the 2 agents").
- The `grants` agent already imports its tool registry via `agents.grants.mcp_tools.TOOL_REGISTRY`, so additional tools can be appended in-place without restructuring the agent class.
- The existing `BaseA2AAgent` lifecycle (port discovery, A2A routing, MCP request handling) is inherited unchanged.
- Avoids duplicating Keycloak/RFC 8693 token wiring, agent registration, and orchestrator routing entries.

**Alternatives considered**:
- Standalone sibling module under `backend/agents/nsf_techaccess/` — rejected per user clarification.
- Composition (new agent that calls into `grants` and `grant_budgets`) — rejected; needlessly complex given the user wanted a merge.
- Replacement of the existing `grants` agent — rejected; the existing CAAI grant-search/match charter is independently valuable.

---

### Decision 2: Tool surface — nine new MCP tools

**Decision**: Add nine new tools to `agents.grants.mcp_tools.TOOL_REGISTRY`:

1. `draft_proposal_section` — drafts any of the five required full-proposal sections (and `loi_synopsis`, which delegates to `draft_loi` per Decision 8); uses the exact required heading text.
2. `draft_loi` — drafts the LOI title (must begin "Kentucky Coordination Hub:") and/or the one-page synopsis. Owns the canonical `_build_loi_synopsis(...)` helper that `draft_proposal_section` calls.
3. `refine_section` — takes pasted draft text and returns a strengthened version with tone/scope corrections.
4. `gap_check_section` — takes pasted draft text and returns a structured list of missing required sub-elements + named verdicts against NSF review criteria.
5. `draft_supplemental_artifact` — produces a permitted supplemental document (PAPPG-format Letter of Collaboration, Data Management Plan, or Mentoring Plan if budget includes postdocs/grad students). Refuses any prohibited artifact (e.g., Letter of Support).
6. `draft_program_officer_questions` — produces a structured ready-to-send list of questions for the NSF program officer, filtered against `PROGRAM_OFFICER_QUESTION_TOPICS.solicitation_resolved` so no question duplicates content already in NSF 26-508 (FR-015 / SC-012).
7. `prioritize_page_budget` — when current section drafts exceed the 15-page narrative limit, produces per-section current-vs-target allocation, names protected required sub-elements, and proposes an ordered cut list (FR-016 / SC-013).
8. `cite_deadlines` — standalone tool returning the three relevant dates (LOI 2026-06-16, full proposal 2026-07-16, internal ~2026-07-09) outside any drafting flow (FR-020 / SC-014).
9. `techaccess_scope_check` — given an arbitrary user request, classify it as in-scope (NSF 26-508 Hub / National Lead OTA / Catalyst), adjacent-but-different (the National Lead OTA or Catalyst, where rules differ), or out-of-scope. Returns a redirect message for out-of-scope requests. Used by the drafting/refining tools as a guard and exposed as a standalone tool for explicit checks.

**Rationale**:
- Each functional requirement (FR-002 through FR-018) maps to exactly one tool's behavior, keeping per-tool tests and contracts tractable.
- Six tools is small enough to be reviewed by hand but large enough that each tool has a single, testable purpose. Splitting "draft" and "refine" lets tests assert that refinement preserves user-supplied content, while drafting from scratch can hallucinate within bounds.
- A separate `techaccess_scope_check` tool isolates the redirect/decline logic so it can be unit-tested without invoking the LLM and reused as a precondition gate inside the other five tools.

**Alternatives considered**:
- One mega-tool taking a "section" parameter — rejected; collapses unrelated input/output schemas, complicates `input_schema` validation, and makes per-tool contract tests brittle.
- Many fine-grained tools (one per section) — rejected; ten+ near-identical tools inflate the tool list the LLM must reason over with no behavioral benefit.
- LLM-only approach (no tools, just system-prompt hints in the orchestrator) — rejected; the spec's success criteria (e.g., SC-001: 100% required sub-elements present first pass; SC-002: 100% NSF-required metrics named) require deterministic check-and-fill logic that lives most cleanly in tool code, not freeform prompting.

---

### Decision 3: Knowledge module shape

**Decision**: Add a new file [backend/agents/grants/nsf_techaccess_knowledge.py](../../backend/agents/grants/nsf_techaccess_knowledge.py) that exposes module-level constants (lists / dicts / dataclass-like dicts) for:

- `SOLICITATION_META` — name, ID (NSF 26-508), URL, deadlines, page limit, opportunity-family list.
- `SECTION_HEADINGS` — ordered list of the exact required Section 1–5 strings the spec mandates.
- `SECTION_REQUIREMENTS` — for each section, the list of required sub-elements (matches FR-003).
- `HUB_RESPONSIBILITIES` — the five required responsibility areas + framing rule ("convener, not direct delivery").
- `NSF_REQUIRED_METRICS` — the six metric categories called out in the spec (FR-007), each with its name and a short scoring hint.
- `EXTENDED_METRIC_LAYERS` — the reach / depth / system-change layers (FR-008).
- `AI_LITERACY_LEVELS` — Literacy / Proficiency / Fluency, with definitions matching the solicitation.
- `KY_PARTNERS` — the likely partnership architecture: UK, KCTCS, CPE, COT, UK Cooperative Extension, KY Cabinet for Economic Development, KentuckianaWorks, KY SBDC, KDE — each with a short "what they uniquely contribute" and "trusted-messenger network" descriptor (FR-009 / FR-010).
- `KY_PRIORITY_SECTORS` — healthcare, agriculture, advanced manufacturing, energy, education.
- `KY_EQUITY_LENSES` — rural vs. urban, eastern Kentucky, first-generation and adult learners, minority-owned small businesses, underserved school districts, agricultural communities.
- `LOI_RULES` — title prefix rule, no-acronyms rule, one-page-synopsis rule.
- `SUPPLEMENTAL_RULES` — allowed (LOC PAPPG, DMP, conditional Mentoring Plan); prohibited (LOS, additional narrative).
- `OPPORTUNITY_FAMILY` — three entries (Coordination Hub / National Coordination Lead / Catalyst Award Competitions) with per-opportunity rule notes (FR-001 expanded scope from Q4).
- `FRAMING_RULES` — coordinator-not-builder, sustainability-beyond-Year-3, baseline-before-progress, common-instrument-across-partners, independent-evaluation-component.
- `ADMINISTRATION_PRIORITIES` — White House AI Action Plan, America's Talent Strategy, EOs on AI literacy / removing barriers (FR-019).

**Rationale**:
- Mirrors the existing `agents.grants.caai_knowledge` pattern (also pure-Python module-level constants + a `compute_match_score` helper) so future maintainers see the same shape twice.
- Constants are easy to import into both the tool implementations and the unit tests; tests can assert structural properties (e.g., "every entry in `SECTION_REQUIREMENTS` is present in any drafted section") without invoking the LLM.
- No DB persistence — matches Clarifications Q3 (inherit existing memory posture; no new persistence).

**Alternatives considered**:
- YAML/JSON file loaded at runtime — rejected; the existing project pattern uses Python modules, and config-as-data adds I/O and parsing without a benefit at this volume.
- Database-backed knowledge — rejected; out of scope (no schema changes per Constitution IX), and unnecessary for content that changes only on solicitation amendment.
- Pulling content live from the solicitation PDF on every request — rejected; reliability risk, latency cost, and no behavioral upside compared to a versioned Python constant.

---

### Decision 4: Tool output uses existing primitive components

**Decision**: All new tools return UI via `shared.primitives.create_ui_response(...)` using only existing primitives — `Text`, `Card`, `Alert`, `List_`, `Tabs`/`TabItem`, `MetricCard`, `Table`. No new primitives are introduced.

**Rationale**:
- Constitution Principle VIII requires that new primitives be approved and documented before use; reusing existing ones avoids that gate.
- The orchestrator already understands `_ui_components` payloads from grants-agent tools (see `mcp_server.py` lines 86–113), so refusal alerts (e.g., "Letters of Support are not permitted") flow through the existing tool-error path without additional plumbing.
- Per-section drafts as `Card(title="Section N — …", content=[Text(...)])` render natively in the existing chat UI.

**Alternatives considered**:
- A new "SectionDraft" primitive — rejected on Constitution VIII grounds; nothing about a section draft requires layout/behavior the existing `Card`+`Text` cannot deliver.
- Returning raw markdown strings — rejected; the platform's chat surface uses primitive components for tool output, and bypassing them produces inconsistent UX with other agents.

---

### Decision 5: Scope-lock and refusal logic lives in code, not just the system prompt

**Decision**: The TechAccess scope check (decline non-TechAccess requests, redirect requests outside the family, refuse prohibited supplemental artifacts) is implemented in deterministic Python in `techaccess_scope_check` and reused as a precondition inside `draft_supplemental_artifact`. The LLM is also instructed via the agent description, but the refusal does not rely on the LLM.

**Rationale**:
- Spec success criteria SC-004 ("100% of off-topic requests are declined and redirected") and SC-005 ("100% of requests for prohibited supplemental artifacts are declined") demand deterministic behavior. LLM-only refusal drifts; coded guards do not.
- The merge-with-existing-`grants`-agent constraint (Q2) means the same agent must remain unconstrained for non-TechAccess work — so the guard must be selective: it engages for TechAccess sessions and is silent otherwise.
- Coded guards are unit-testable without LLM calls, which is necessary to hit the 90% coverage gate cheaply.

**Alternatives considered**:
- Pure system-prompt enforcement — rejected; non-deterministic, untestable.
- Permissions-layer enforcement (Keycloak scopes) — rejected as wrong layer; this is content scope, not authorization.

---

### Decision 6: No new third-party dependencies

**Decision**: The feature ships using only libraries already present in the project: `requests` (already used by `mcp_tools.py`), the project's existing OpenAI-compatible LLM client, `shared.primitives`, `shared.protocol`, `shared.base_agent`, and the Python standard library.

**Rationale**:
- Constitution Principle V requires lead-developer approval for any new dependency, and there is no need for one. NSF solicitation knowledge is static text. UI is rendered through existing primitives. LLM calls go through the existing client. Tests run on existing pytest.
- Avoids the supply-chain and review overhead.

**Alternatives considered**:
- Add a markdown-to-component converter library — rejected; `Card`+`Text` and the existing primitives suffice for rendering structured drafts.
- Add a JSON-Schema validation library for tool inputs — rejected; the existing MCP server passes `input_schema` to the LLM as a contract hint and the tool functions validate inputs themselves with stdlib checks, matching the existing pattern in `agents.grants.mcp_tools`.

---

### Decision 7: Tests are split into knowledge / unit / integration

**Decision**: Three new pytest modules:

- `test_nsf_techaccess_knowledge.py` — structural assertions on the knowledge module (every required Section 1–5 heading is present and exact-string; every Hub responsibility present; every NSF-required metric present; every AI literacy level present; every KY partner has a non-empty contribution descriptor; LOI title rule is encoded; supplemental allowlist matches the spec).
- `test_techaccess_tools.py` — per-tool unit tests with mocked LLM where a tool calls the model: assert refusal paths (off-topic, prohibited supplemental, wrong solicitation), input validation, and that drafts always include the required heading + the required sub-elements (the tool can post-process and inject required content rather than relying solely on the LLM).
- `test_techaccess_integration.py` — round-trip via `MCPServer.process_request` for each of the six tools, asserting `_ui_components` are well-formed and `Alert(variant="error")` is emitted for refusal cases (so the orchestrator surfaces them as tool errors, matching `mcp_server.py` lines 86–106).

**Rationale**:
- Splits machine-checkable invariants (knowledge module) from LLM-dependent behavior (tools) so the bulk of coverage is fast and deterministic.
- Mirrors the existing `backend/tests/agents/` layout.
- Hits Constitution Principle III (≥90%) without hammering the LLM in CI.

**Alternatives considered**:
- One large end-to-end test file — rejected; harder to debug, slower CI, encourages skipping the structural invariants.

### Decision 8: Canonical synopsis path (resolves D1 from /speckit.analyze)

**Decision**: `draft_proposal_section(section_key="loi_synopsis")` MUST delegate to `draft_loi(produce="synopsis", ...)`. Both call into a single private helper `_build_loi_synopsis(...)` defined at module scope in `mcp_tools.py`. There is exactly one synopsis builder; no behavior diverges between the two entry points.

**Rationale**: The two paths emerged organically (one is "draft any section", one is "draft the LOI"), and the user can reasonably reach the synopsis from either. Letting them diverge would mean two outputs the team would have to compare. Collapsing them through a shared helper preserves both call paths while guaranteeing parity.

**Alternatives considered**: Keep them separate and assert parity in tests (rejected — drift risk over time); remove `loi_synopsis` from `draft_proposal_section`'s `section_key` enum (rejected — surprising for users who think of the LOI synopsis as "section zero").

---

### Decision 9: Acronym disallow-list location (resolves A2 from /speckit.analyze)

**Decision**: The LOI title acronym disallow-list lives in `nsf_techaccess_knowledge.py` as `LOI_RULES["forbidden_acronyms"]: list[str]`. `draft_loi` reads it from there. No copy lives in `mcp_tools.py`.

**Rationale**: All LOI metadata (title prefix, no-acronyms rule, synopsis page limit) belongs together. Co-location makes the test surface cleaner and the rule easier to amend if NSF clarifies the acronym scope.

**Alternatives considered**: Inline in `mcp_tools.py` (rejected — splits LOI rules across two files); compute from a heuristic regex (rejected — too brittle; explicit list is what the spec mandates).

---

### Decision 10: New entities (resolves G3 / G4 / G1 / G2 from /speckit.analyze)

**Decision**: Four additions to the knowledge module:

- A new `KY_PARTNERS` entry `uk_caai` (UK Center for Applied AI) representing the AI research lab named in the spec's Kentucky Context. Carries the independent-evaluation role explicitly (G3).
- `PROGRAM_OFFICER_QUESTION_TOPICS` (G1) with a `solicitation_resolved` boolean per topic so `draft_program_officer_questions` can filter deterministically.
- `PAGE_BUDGET` (G2) mirroring `SECTIONS` with `target_share` / `target_pages` / `protected_subelement_keys`.
- `DEADLINES` (G4) carrying the three ISO dates and submission paths used by `cite_deadlines`.

**Rationale**: Each addition is the minimum data shape required to deterministically test the corresponding new tool.

---

## Open questions

None. All earlier `NEEDS CLARIFICATION` items were resolved in `/speckit.clarify`, and all gaps surfaced in `/speckit.analyze` are addressed in Decisions 8–10 above. If additional questions arise during implementation, they will be raised at `/speckit.tasks` time, not deferred to merge.
