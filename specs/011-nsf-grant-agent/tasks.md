---

description: "Task list for implementing the NSF TechAccess AI-Ready America grant-writing capability inside the existing `grants` agent"
---

# Tasks: NSF TechAccess AI-Ready America Grant Writing Agent

**Input**: Design documents from `/specs/011-nsf-grant-agent/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Tests are NOT optional for this feature. AstralBody Constitution Principle III mandates ≥90% coverage on all new code, and Principle X requires golden-path, edge-case, and error-path coverage. Test tasks below are therefore part of each phase's definition of done.

**Organization**: Tasks are grouped by user story so each story can be implemented and merged independently. The merge target is the existing `grants` agent (per Clarifications Q2), so all source-code changes touch [backend/agents/grants/](../../backend/agents/grants/) and [backend/tests/agents/grants/](../../backend/tests/agents/grants/).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Maps the task to a user story from spec.md (US1, US2, US3); omitted in Setup/Foundational/Polish phases
- File paths are absolute relative to the repo root

## Path Conventions

- Backend agent code: `backend/agents/grants/`
- Backend tests: `backend/tests/agents/grants/`
- No frontend code path is touched by this feature

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the existing test/lint scaffolding will accept the new files without ceremony.

- [X] T001 Confirm pytest discovers the new test directory by running `pytest backend/tests/agents/grants/ --collect-only` and verifying existing grants tests still collect cleanly (no schema work required — Constitution IX is N/A for this feature).
- [X] T002 [P] Run `ruff check backend/agents/grants/` and record the baseline; the new files added in later phases must keep this clean (Constitution IV).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Ship the knowledge module, the scope-lock tool, and the agent-description update that ALL three user stories depend on.

**⚠️ CRITICAL**: No user story work begins until this phase is complete.

- [X] T003 Create the knowledge module at `backend/agents/grants/nsf_techaccess_knowledge.py` exposing the module-level constants enumerated in [data-model.md](data-model.md) — `SOLICITATION_META`, `OPPORTUNITY_FAMILY`, `SECTIONS`, `SECTION_HEADINGS`, `SECTION_REQUIREMENTS`, `HUB_RESPONSIBILITIES`, `NSF_REQUIRED_METRICS`, `EXTENDED_METRIC_LAYERS`, `ALL_METRICS`, `KY_PARTNERS` (MUST include the `uk_caai` entry whose `unique_contribution` references the independent-evaluation role per Decision 10 / G3), `KY_PRIORITY_SECTORS`, `KY_EQUITY_LENSES`, `AI_LITERACY_LEVELS`, `LOI_RULES` (MUST include `forbidden_acronyms: list[str]` per Decision 9 / A2), `SUPPLEMENTAL_RULES`, `FRAMING_RULES`, `ADMINISTRATION_PRIORITIES`, `ADMINISTRATION_PRIORITY_PHRASES`, `PROGRAM_OFFICER_QUESTION_TOPICS`, `PAGE_BUDGET`, `DEADLINES`. Include Google-style docstrings and follow the pattern of the sibling `caai_knowledge.py` module.
- [X] T004 [P] Write structural unit tests in `backend/tests/agents/grants/test_nsf_techaccess_knowledge.py` asserting: every required Section 1–5 heading is exact-string present in `SECTION_HEADINGS`; `SECTION_REQUIREMENTS` covers FR-003 sub-elements for each section; all five Hub responsibilities are present in `HUB_RESPONSIBILITIES`; all six NSF-required metrics are present in `NSF_REQUIRED_METRICS`; reach/depth/system-change layers are present in `EXTENDED_METRIC_LAYERS`; `AI_LITERACY_LEVELS` contains the three solicitation-defined levels; every entry in `KY_PARTNERS` has a non-empty `unique_contribution`; `KY_PARTNERS` contains a `uk_caai` entry whose `unique_contribution` mentions "independent evaluation"; `LOI_RULES["title_prefix"]` equals `"Kentucky Coordination Hub:"`; `LOI_RULES["forbidden_acronyms"]` is a non-empty list including at least `"NSF"`, `"AI"`, `"UK"`, `"KCTCS"`, `"CPE"`, `"COT"`, `"KY"`, `"KDE"`, `"SBDC"`, `"WIOA"`; `SUPPLEMENTAL_RULES` marks `letter_of_support` and `additional_narrative` as `is_allowed=False`; `OPPORTUNITY_FAMILY` contains exactly the three keys `hub`, `national_lead`, `catalyst`; `DEADLINES` contains keys `loi`/`full_proposal`/`internal` with ISO dates `2026-06-16`/`2026-07-16`/`2026-07-09`; `PAGE_BUDGET` keys mirror `SECTIONS` and `target_share` values sum to ≤ 1.0; `PROGRAM_OFFICER_QUESTION_TOPICS` is non-empty and at least one entry has `solicitation_resolved=False`.
- [X] T005 Implement `techaccess_scope_check` in `backend/agents/grants/mcp_tools.py` per [contracts/techaccess_scope_check.md](contracts/techaccess_scope_check.md): deterministic substring matcher first (Hub / National Lead OTA / Catalyst / out-of-family), LLM fallback only on ambiguous input, output via `create_ui_response(...)` with the four canonical classifications. Register the tool in `TOOL_REGISTRY` with the input schema from the contract. Use the existing `logger = logging.getLogger("GrantsTools")`.
- [X] T006 [P] Add unit tests for `techaccess_scope_check` to a new file `backend/tests/agents/grants/test_techaccess_tools.py` covering all four classifications with golden inputs (Hub-keyworded request → primary; "National Coordination Lead OTA" → sibling; "Catalyst" → sibling; "summarize this paper" → out_of_family); assert that the deterministic branch logs at INFO level; assert empty input yields the canonical error Alert.
- [X] T007 [P] Update `backend/agents/grants/grants_agent.py`: broaden `description` to mention "Also supports drafting and gap-checking the NSF TechAccess: AI-Ready America (NSF 26-508) Kentucky Coordination Hub LOI and full proposal, plus program-officer questions, page-budget prioritization, and standalone deadline citation." Append the single-token tags `"techaccess"`, `"loi"`, `"proposal"`, `"techaccess26508"` to `skill_tags` (single-token style matches existing tags per I1). Do NOT change `agent_id`, port wiring, or any other field; existing routing must remain stable.
- [X] T008 [P] Confirm `mcp_tools.py` continues to expose the `TOOL_REGISTRY` symbol after edits, and that the existing exception classes (`RETRYABLE_EXCEPTIONS`, `NON_RETRYABLE_EXCEPTIONS`) are inherited by the new tool functions without modification (Constitution X production-readiness check; reuse, don't fork the error model).

**Checkpoint**: Foundation ready — the knowledge module is complete and tested, the scope-lock tool is in place and tested, and the agent's description surfaces TechAccess. User story phases can now begin.

---

## Phase 3: User Story 1 — Draft a section of the LOI or full proposal on demand (Priority: P1) 🎯 MVP

**Goal**: A team member can ask the agent to produce, on demand, a draft of any of the five required full-proposal sections or the LOI title/synopsis. Drafts use the exact required heading, address every required sub-element, frame the Hub as a coordinator/convener, ground claims in Kentucky-specific detail, map training language to the literacy/proficiency/fluency continuum, and (for Section 4) include every NSF-required metric plus reach/depth/system-change layers and a Year 1 baseline.

**Independent Test**: Send the agent a message such as "Draft Section 1 — Vision and Approach to Responsibilities for the Kentucky Coordination Hub." Verify the response Card uses the exact heading, references all five Hub responsibilities by name, includes a strategy for small-scale local pilots and a UK/Kentucky prior-experience claim, and contains zero direct-delivery framing. Repeat for the LOI synopsis: confirm the title begins "Kentucky Coordination Hub:", the synopsis fits ~one page, and the response covers compressed Section 1 + Section 2 content.

### Implementation for User Story 1

- [X] T009 [US1] Implement `draft_loi` in `backend/agents/grants/mcp_tools.py` per [contracts/draft_loi.md](contracts/draft_loi.md). Internally: (1) build the title using `LOI_RULES["title_prefix"]`, then validate against `LOI_RULES["forbidden_acronyms"]` (sourced from `nsf_techaccess_knowledge.py` per Decision 9 / A2); (2) build the synopsis through a private helper `_build_loi_synopsis(...)` that produces compressed Section-1-equivalent + Section-2-equivalent content within `LOI_RULES["synopsis_page_limit"]`; (3) emit a deadline-reminder `Alert(variant="info")` referencing 2026-06-16; (4) include the PI/personnel `Table` from inputs or partner-default working assumption. Register in `TOOL_REGISTRY`. **NOTE**: This task lands BEFORE `draft_proposal_section` because the latter delegates to `_build_loi_synopsis(...)` defined here (Decision 8 / D1).
- [X] T010 [US1] Implement `draft_proposal_section` in `backend/agents/grants/mcp_tools.py` per [contracts/draft_proposal_section.md](contracts/draft_proposal_section.md). Internally: (1) gate on `techaccess_scope_check`; (2) for `section_key="loi_synopsis"`, delegate to `draft_loi(produce="synopsis", ...)` via the shared `_build_loi_synopsis(...)` helper from T009 (D1 / Decision 8); (3) for Sections 1–5, build the LLM prompt from `SECTIONS[section_key]`, `SECTION_REQUIREMENTS[section_key]`, applicable `HUB_RESPONSIBILITIES`, applicable `FRAMING_RULES`, and `KY_PARTNERS` (use `partner_roster_override` if supplied, otherwise the full likely architecture as a working assumption that is named in the draft); (4) post-process to enforce all eight invariants (heading present, sub-elements referenced, hub responsibilities covered for Section 1, NSF-required metrics + extended layers + Year 1 baseline + independent evaluation for Section 4, no direct-delivery framing patterns, every training reference mapped to AI-readiness level + audience, **and when `request_administration_priority_alignment=true` at least one phrase from `ADMINISTRATION_PRIORITY_PHRASES` is present** per A1 / FR-019); (5) on failure, append a "Required-coverage gap" appendix rather than silently shipping incomplete output. Register in `TOOL_REGISTRY`.
- [X] T011 [US1] Add unit tests for `draft_proposal_section` to `backend/tests/agents/grants/test_techaccess_tools.py`: with the LLM mocked to return a deficient draft, assert the post-processor injects the missing required heading and appends the "Required-coverage gap" appendix; with a well-formed mock draft, assert all eight invariants pass and the output Card has the expected `title`; assert that `section_key="loi_synopsis"` produces output identical to `draft_loi(produce="synopsis", ...)` byte-for-byte (D1 parity check); assert that `request_administration_priority_alignment=true` always yields output containing at least one `ADMINISTRATION_PRIORITY_PHRASES` substring (A1 / FR-019). Cover all six `section_key` values plus the bad-key refusal path.
- [X] T012 [US1] Add unit tests for `draft_loi` to `backend/tests/agents/grants/test_techaccess_tools.py`: title prefix is exact; every entry in `LOI_RULES["forbidden_acronyms"]` is rejected when supplied as `descriptive_phrase`; synopsis word count stays within budget; the deadline-reminder Alert is present and references 2026-06-16.
- [X] T013 [US1] Add round-trip integration tests in a new file `backend/tests/agents/grants/test_techaccess_integration.py` exercising both tools via `MCPServer().process_request(MCPRequest(method="tools/call", params={"name": ..., "arguments": ...}))`. Assert `MCPResponse.ui_components` contains the expected `Card.title` and that refusal paths surface as `error={"code": -32000, "retryable": True}` per the existing tool-error routing in `mcp_server.py:86-106`.
- [X] T014 [US1] Manual UI smoke per [quickstart.md](quickstart.md) "End-to-end smoke test": run the backend and frontend, enable the `grants` agent in a chat, send "Draft the LOI synopsis for the Kentucky Coordination Hub", and verify the `LOI Title` and `LOI Synopsis` Cards render correctly with the deadline Alert. Constitution Principle X requires this manual UI exercise before declaring the story complete.

**Checkpoint**: User Story 1 is fully functional and testable independently. The team can now produce LOI and proposal-section drafts. This is the MVP — stop here and validate before continuing if desired.

---

## Phase 4: User Story 2 — Refine, strengthen, and gap-check an existing draft against NSF criteria (Priority: P2)

**Goal**: A team member can paste an existing draft section, ask the agent to (a) refine the language and/or (b) gap-check against required sub-elements and NSF review criteria, and receive structured, actionable output (named gaps, concrete rewrites, criterion-by-criterion verdicts).

**Independent Test**: Paste a draft Section 2 missing the governance/decision-making structure and ask "Gap-check this against NSF review criteria." Verify the response includes a coverage `Table` with a `✗` row for governance, a verdict against each applicable review criterion, and a "Suggested Rewrites" Card with replacement prose. Then take the same draft and ask "Refine this — preserve the partner roster but fix any direct-delivery framing." Verify the refined output preserves named entities while rewriting direct-delivery passages and emits a "What Changed and Why" Card listing the framing rules invoked.

### Implementation for User Story 2

- [X] T015 [US2] Implement `refine_section` in `backend/agents/grants/mcp_tools.py` per [contracts/refine_section.md](contracts/refine_section.md). Internally: (1) gate on `techaccess_scope_check`; (2) build a refinement prompt that explicitly preserves named entities when `preserve_factual_claims=true`; (3) post-process to detect any remaining `FRAMING_RULES.violation_pattern_hints` substrings and emit a follow-up rewrite; (4) verify every training reference in the refined output names both an audience and an AI-readiness level — if not, augment the output. Register in `TOOL_REGISTRY`.
- [X] T016 [US2] Implement `gap_check_section` in `backend/agents/grants/mcp_tools.py` per [contracts/gap_check_section.md](contracts/gap_check_section.md). Internally: (1) gate on `techaccess_scope_check`; (2) build a coverage `Table` row-by-row from `SECTION_REQUIREMENTS[section_key]`, marking each present/partial/absent via case-insensitive substring + LLM verification; (3) emit verdicts against each applicable criterion (Intellectual Merit, Broader Impacts, the five solicitation-specific criteria); (4) scan for `FRAMING_RULES.violation_pattern_hints` and quote each offender; (5) for `section_4`, additionally enumerate NSF-required metric coverage, extended-layer coverage, baseline statement presence, and independent-evaluation-component presence; (6) when `include_rewrites=true`, append a "Suggested Rewrites" Card pairing weak passages with stronger replacements. Register in `TOOL_REGISTRY`.
- [X] T017 [US2] Add unit tests for `refine_section` to `backend/tests/agents/grants/test_techaccess_tools.py`: golden adversarial input "CAAI will deliver AI training to all KCTCS students" → refined output reframes as coordinator/convener and maps to a literacy/proficiency/fluency level + audience; with `preserve_factual_claims=true`, named partners and numbers in the input appear unchanged in the output; empty `draft_text` yields the canonical error Alert.
- [X] T018 [US2] Add unit tests for `gap_check_section` to `backend/tests/agents/grants/test_techaccess_tools.py`: a Section 2 draft missing governance content yields a `✗` row for the governance sub-element; a Section 4 draft with no baseline statement yields "Year 1 baseline: missing" in the Metric Coverage card; framing-violation substrings are quoted in the violations Card.
- [X] T019 [US2] Add integration tests for both tools to `backend/tests/agents/grants/test_techaccess_integration.py`: round-trip via `MCPServer.process_request` returns the expected Cards (Refined Draft + What Changed and Why for `refine_section`; coverage Table + verdicts + violations + rewrites for `gap_check_section`).
- [X] T020 [US2] Manual UI smoke: paste a deliberately weak Section 2 draft into a chat with the `grants` agent enabled, request a gap-check, and confirm the rendered output matches expectations from [quickstart.md](quickstart.md).

**Checkpoint**: User Stories 1 and 2 both work independently. The team can now draft and self-review sections against the precise NSF rubric.

---

## Phase 5: User Story 3 — Supplemental materials, program-officer questions, page-budget prioritization, and deadline citation (Priority: P3)

**Goal**: A team member can request (a) a permitted supplemental artifact — PAPPG-format Letter of Collaboration for a named partner, a Data Management Plan, or a Mentoring Plan (only when the user confirms the budget includes postdocs/grad-students); (b) a structured ready-to-send list of questions for the NSF program officer that filters out anything answered in NSF 26-508 (FR-015 / SC-012); (c) page-budget prioritization advice that protects required sub-elements (FR-016 / SC-013); or (d) standalone deadline citation outside any drafting flow (FR-020 / SC-014). Prohibited supplemental artifacts (Letters of Support, additional narrative supplements) are refused with an explanation.

**Independent Test**: Send "Generate a PAPPG-format Letter of Collaboration for KCTCS." → verify single LOC Card with KCTCS's specific contribution, no endorsement framing. Send "Write me a Letter of Support for UK leadership." → verify refusal Alert. Send "Write a Mentoring Plan." with no budget confirmation → verify refusal Alert. Send "Draft questions for the NSF program officer about hub-to-hub coordination and matching funds." → verify a numbered list of questions, none of which duplicate solicitation content. Send `prioritize_page_budget` with a 17-page section breakdown → verify a current-vs-target Table and an ordered cut list that preserves required sub-elements. Send "What are the deadlines for this proposal?" → verify a Card with all three dates.

### Implementation for User Story 3

- [X] T021 [US3] Implement `draft_supplemental_artifact` in `backend/agents/grants/mcp_tools.py` per [contracts/draft_supplemental_artifact.md](contracts/draft_supplemental_artifact.md). Internally: (1) lookup `SUPPLEMENTAL_RULES[artifact_key]`; on `is_allowed=False`, return the canonical refusal Alert with the rule's `refusal_message` (covers `letter_of_support`, `additional_narrative`); (2) when `artifact_key="mentoring_plan"`, require `budget_includes_postdocs_or_grad_students=true` and return a refusal Alert otherwise; (3) when `artifact_key="letter_of_collaboration"`, require `partner_key`; if it matches a `KY_PARTNERS` entry, default `partner_contribution` to that partner's `unique_contribution`; (4) build the document via the LLM, then post-process to scan for forbidden endorsement substrings ("strongly support", "endorse", "highly recommend") and rewrite/strip them; (5) for `data_management_plan`, ensure the output mentions a common cross-partner instrument and an independent evaluation component. Register in `TOOL_REGISTRY`.
- [X] T022 [US3] Implement `draft_program_officer_questions` in `backend/agents/grants/mcp_tools.py` per [contracts/draft_program_officer_questions.md](contracts/draft_program_officer_questions.md) (FR-015 / SC-012). Internally: (1) iterate `PROGRAM_OFFICER_QUESTION_TOPICS`; (2) filter out any topic with `solicitation_resolved=True`; (3) refine each remaining topic's `seed_question` with `team_specific_context` via the LLM, capped at `max_questions`; (4) post-process to scan each generated question against a small set of canonical solicitation phrases (e.g., "rather than delivering training directly", "leverage existing resources") and discard any question whose text overlaps; (5) emit the two-Card payload (questions + filtered topics). Register in `TOOL_REGISTRY`.
- [X] T023 [US3] Implement `prioritize_page_budget` in `backend/agents/grants/mcp_tools.py` per [contracts/prioritize_page_budget.md](contracts/prioritize_page_budget.md) (FR-016 / SC-013). Internally: (1) validate every section_key in `current_pages` is in `{"section_1"..."section_5"}`; (2) build the per-section current-vs-target table using `PAGE_BUDGET[section_key].target_pages`; (3) when `sum(current_pages) <= 15`, emit the "no cuts required" info Alert and skip the cut list; (4) otherwise, propose an ordered cut list that NEVER targets `protected_subelement_keys` (verified by substring scan when `drafts` are supplied; verified by exclusion otherwise) and brings projected total ≤ 15; (5) emit under-investment warnings for any section below 0.5 × target. Register in `TOOL_REGISTRY`.
- [X] T024 [US3] Implement `cite_deadlines` in `backend/agents/grants/mcp_tools.py` per [contracts/cite_deadlines.md](contracts/cite_deadlines.md) (FR-020 / SC-014). Internally: (1) read `DEADLINES`; (2) honor `include` filter when supplied; (3) emit a single `Card(title="NSF 26-508 Critical Deadlines")` containing a `Table` of (deadline, date, submission path, notes); (4) refuse unknown `include` keys with a canonical error Alert. Register in `TOOL_REGISTRY`.
- [X] T025 [US3] Add unit tests for the four US3 tools to `backend/tests/agents/grants/test_techaccess_tools.py`: (a) `draft_supplemental_artifact` — every prohibited `artifact_key` returns the canonical error Alert; `mentoring_plan` without the budget flag is refused; LOC for a known `partner_key` includes that partner's `unique_contribution`; LOC output contains zero endorsement substrings. (b) `draft_program_officer_questions` — topics with `solicitation_resolved=True` never appear in output; `max_questions=3` is respected; empty topic intersection yields the canonical refusal. (c) `prioritize_page_budget` — 17-page input with bloated Section 5 yields cut-list targeting Section 5; 14-page input yields "no cuts required" Alert; 15-page input with under-target Section 1 yields under-investment warning; invalid section_key yields canonical error Alert; cut list never targets a `protected_subelement_keys` substring. (d) `cite_deadlines` — default call returns three rows; `include=["loi"]` returns one row; unknown key yields error Alert; full-proposal row mentions "AOR signature required".
- [X] T026 [US3] Add integration tests for the four US3 tools to `backend/tests/agents/grants/test_techaccess_integration.py`: round-trip via `MCPServer.process_request` for each happy path (LOC for KCTCS, DMP, Mentoring Plan with budget flag, program-officer questions with default topics, page-budget call with 17-page input, deadline citation default) returns the expected Cards; refusal cases surface as `error={"code": -32000, "retryable": True}`.
- [X] T027 [US3] Manual UI smoke per [quickstart.md](quickstart.md): exercise each happy path and each refusal path for all four US3 tools in a chat, confirm rendered output.

**Checkpoint**: All three user stories functional and independently verified. The team can produce LOI text, full-proposal drafts, gap-checks, all permitted supplemental materials, program-officer question lists, page-budget prioritization advice, and standalone deadline citations.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Finalize quality bars before merge.

- [X] T028 [P] Measure coverage with `pytest --cov=backend/agents/grants --cov-report=term-missing backend/tests/agents/grants/` and confirm ≥90% on `nsf_techaccess_knowledge.py` (file-level) AND on each of the nine new tool functions inside `mcp_tools.py` (function-level — extract per-function coverage from the `term-missing` report). Constitution Principle III blocks merge below this threshold (U3).
- [X] T029 [P] Run `ruff check backend/agents/grants/ backend/tests/agents/grants/` and resolve any new findings (Constitution Principle IV).
- [X] T030 Confirm the existing grants-agent tests under `backend/tests/agents/grants/` continue to pass unchanged (no regression for the existing CAAI grant-search/match charter — required by FR-001 and Clarifications Q2).
- [X] T031 [P] Walk through [quickstart.md](quickstart.md) end-to-end against the **local** running stack (`docker compose up` for backend, `npm run dev` for frontend) to validate the team-facing usage examples render correctly. Local docker-compose is sufficient: this feature does NOT change runtime infrastructure (no DB, no auth, no new container, no schema), so Constitution Principle X's staging gate does not apply (U2). Capture screenshots / chat transcripts for the PR.
- [X] T032 [P] Verify the agent picker in the frontend surfaces the broadened `description` and updated `skill_tags` from the `grants` agent. No frontend code changes are expected; if the picker does not refresh, document the cache-bust step in the PR.
- [X] T033 Structured-logging audit on the nine new tool functions in `backend/agents/grants/mcp_tools.py`: (a) scope-classification redirects (out_of_family) emit `logger.info` with the classification reason; (b) tool-level refusals returned as `Alert(variant="error")` emit `logger.warning` with the tool name and a redacted snippet of the offending argument; (c) unexpected exceptions emit `logger.error` with the tool name. Constitution Principle X requires this for production diagnosability (U1).
- [X] T034 Open the PR, reference this branch (`011-nsf-grant-agent`) and SC-011 / SC-012 / SC-013 / SC-014 from spec.md as the merge-acceptance bar; confirm Constitution Principle V (no new dependencies) by inspecting the diff for any change to `pyproject.toml` / `requirements.txt`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1. **BLOCKS all user stories** — the knowledge module and `techaccess_scope_check` are required by every drafting tool.
- **Phase 3 (US1, P1)**: Depends on Phase 2. Independent of US2 and US3.
- **Phase 4 (US2, P2)**: Depends on Phase 2. Independent of US1 and US3 — does not require US1 to be complete (refinement/gap-check tools work on any pasted text, not necessarily text the agent itself produced).
- **Phase 5 (US3, P3)**: Depends on Phase 2. Independent of US1 and US2.
- **Phase 6 (Polish)**: Depends on whichever user stories are landing in this PR.

### User Story Dependencies

- **US1**: After Foundational. No dependency on US2/US3.
- **US2**: After Foundational. No dependency on US1/US3.
- **US3**: After Foundational. No dependency on US1/US2.

### Within Each User Story

- Tool implementations (T009/T010 in US1, T015/T016 in US2, T021/T022/T023/T024 in US3) edit the same file (`mcp_tools.py`) and should be sequenced to avoid merge conflicts; tests for those tools live in separate test files and can be authored in parallel with implementation (TDD-friendly).
- T009 (`draft_loi`) MUST land before T010 (`draft_proposal_section`) because T010 delegates to the `_build_loi_synopsis(...)` helper introduced in T009 (Decision 8 / D1).
- Integration tests follow unit tests within a story.
- Manual UI smoke is the last task in each story phase.

### Parallel Opportunities

- **Phase 1**: T002 [P] runs alongside T001.
- **Phase 2**: T003 (knowledge module) is parallelizable with T007 (agent description) since they edit different files. T004 [P] can be authored alongside T003 (TDD). T005 (scope-check tool) is sequential with later tool work in `mcp_tools.py`. T006 [P] runs alongside T005. T008 [P] runs alongside other Phase 2 tasks.
- **Phase 3 (US1)**: T011/T012 unit tests can be drafted in parallel with T009/T010 implementation (different files). T013 follows T009+T010.
- **Phase 4 (US2)**: T017/T018 in parallel with T015/T016.
- **Phase 5 (US3)**: T025 unit tests can be drafted in parallel with T021/T022/T023/T024 implementations (different files). T026 follows once all four implementations land.
- **Phase 6**: T028, T029, T031, T032 all [P] (different surfaces).

---

## Parallel Example: User Story 1

```text
# Foundational layer must be DONE before US1 starts:
# T003 (knowledge.py), T004 (knowledge tests), T005 (scope_check), T006 (scope_check tests),
# T007 (agent description), T008 (logging audit) all complete and merged.

# Within US1, sequencing (T009 lands first because T010 delegates to its _build_loi_synopsis helper):
Task: "T009 — implement draft_loi (with _build_loi_synopsis helper) in backend/agents/grants/mcp_tools.py"
Task: "T012 — write unit tests for draft_loi in backend/tests/agents/grants/test_techaccess_tools.py"  # parallel with T009

Task: "T010 — implement draft_proposal_section (delegates to _build_loi_synopsis for loi_synopsis) in backend/agents/grants/mcp_tools.py"
Task: "T011 — write unit tests for draft_proposal_section in backend/tests/agents/grants/test_techaccess_tools.py"  # parallel with T010

# After both implementations land:
Task: "T013 — integration tests for both US1 tools"
Task: "T014 — manual UI smoke"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) — confirm pytest collection and ruff baseline.
2. Complete Phase 2 (Foundational) — knowledge module, scope-check tool, agent description update. Run tests; confirm zero regression in existing grants-agent tests.
3. Complete Phase 3 (US1) — drafting tools.
4. **STOP and VALIDATE**: a UK proposal team member exercises `draft_proposal_section` for each of Sections 1–5 and `draft_loi` for the LOI synopsis; success criteria SC-001, SC-002, SC-003, SC-006, SC-007, SC-008, SC-009, SC-010 are verified by the team. (SC-011 / SC-012 / SC-013 / SC-014 are verified after US2 + US3 land.)
5. Run Phase 6 polish for the MVP slice; merge.

### Incremental Delivery

1. MVP merge above.
2. Add US2 → run Phase 6 polish for the new surface → merge.
3. Add US3 → run Phase 6 polish for the new surface → merge.
4. After all three: SC-011 is verifiable end-to-end across the team's full proposal-development cycle through the 2026-07-09 internal deadline.

### Parallel Team Strategy

With three developers (or one developer working in three branches off `011-nsf-grant-agent`):

1. Whole team completes Phase 1 + Phase 2 together.
2. Once Foundational is merged:
   - Developer A: US1 (draft tools)
   - Developer B: US2 (refine + gap-check)
   - Developer C: US3 (supplemental artifacts)
3. Each story merges independently; Phase 6 polish runs once all three land or after each merge.

### Risk and Rollback

- The merge target is the existing `grants` agent. Every change must preserve existing behavior for non-TechAccess sessions (FR-001). T027 and existing grants-agent tests are the guardrail.
- All new code is additive (one new file, additions to two existing files, three new test files). Rollback is `git revert` on the PR — no data migration is required (Constitution IX is N/A).

---

## Notes

- [P] tasks operate on different files with no incomplete dependencies.
- [Story] labels (`US1`/`US2`/`US3`) appear only in user-story phases per the format rules.
- Constitution III (≥90% coverage) and X (golden + edge + error paths, plus structured logging and manual UI exercise) apply to every new file in this feature.
- No database schema changes (Constitution IX is N/A).
- No new third-party dependencies (Constitution V satisfied by inspection of the merge diff in T031).
