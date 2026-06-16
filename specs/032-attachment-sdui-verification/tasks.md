---
description: "Task list for feature 032 — Agentic File-Upload SDUI & Delegated-Authority Verification"
---

# Tasks: Agentic File-Upload SDUI & Delegated-Authority Verification

**Input**: Design documents from `specs/032-attachment-sdui-verification/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: This feature **is** a verification/test harness — its pytest integration suite is the primary deliverable and the CI merge gate (FR-030, SC-012). Test tasks are therefore integral, not optional.

**Organization**: Tasks are grouped by user story (US1 tangible UI · US2 delegated authority · US3 backend-only UI). All harness code lives under `backend/verification/`. The only out-of-package edits are one CI line and one `.gitignore` line.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 (setup, foundational, polish carry no story label)
- All paths are repository-relative; the harness package is `backend/verification/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeleton and run configuration.

- [ ] T001 Create the `backend/verification/` package skeleton — `__init__.py` plus subpackages `checks/`, `drivers/`, `tests/`, and the `fixtures/` data dir, each with an `__init__.py` where applicable (per plan.md Project Structure)
- [ ] T002 [P] Add the gitignored run-artifacts dir `backend/verification/.runs/` to `.gitignore` (FR-031)
- [ ] T003 [P] Implement `RunConfig` (mode, base_url, out dir, run_id, step/turn/time/retry budgets, credential env-var NAMES, redaction patterns, `--strict`) in `backend/verification/config.py` (FR-022, D12/D13)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The agentic engine, drivers, checks framework, personas, and isolation that every user story depends on.

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete.

- [ ] T004 [P] Implement secret-safe redaction + `CapturedEvidence` dataclasses (messages, components, workspace_state, audit_rows, audit_chain_ok, client_inspection, device_diff, run_mode) in `backend/verification/evidence.py` (FR-022, data-model.md)
- [ ] T005 [P] Implement `Outcome`/`Verdict`/confidence + deterministic↔LLM-judge reconciliation rules in `backend/verification/verdict.py` (FR-003/004, D1/D13, contracts/check-and-verdict.md)
- [ ] T006 [P] Implement `Check` ABC (typed `run`/`counter`, pure over evidence), registry, replay, and adversarial pairing in `backend/verification/checks/base.py` (FR-002/003, contracts/check-and-verdict.md)
- [ ] T007 [P] Implement namespaced principals (`__verif__<run>_<persona>_<role>`) + teardown of deletable rows/blobs in `backend/verification/isolation.py` (FR-031, D14)
- [ ] T008 [P] Define the extensible `Persona` catalogue and generate clearly-synthetic fixtures (tabular CSV, a document, an image, one unsupported extension; medical fixture flagged synthetic, no real PHI) in `backend/verification/personas.py` and `backend/verification/fixtures/` (FR-007, synthetic-only assumption)
- [ ] T009 Implement the `Scenario` catalogue (persona + fixture + query + expected properties + warrants_ui + auth_mode) in `backend/verification/scenarios.py` (data-model.md; depends on T008)
- [ ] T010 [P] Implement the `Driver` protocol (authenticate/upload/send_query/read_workspace/read_audit/set_scope/trigger_component_action/teardown) in `backend/verification/drivers/base.py` (FR-030, contracts/driver.md)
- [ ] T011 [P] Implement the deterministic scripted LLM — the two-step real-reader→real-component-emitting-tool chain that derives the second tool call's args from the first tool's real output; include an inventory of which built-in tools emit which component types (general agent `mcp_tools.py`, connectors widget tools) — in `backend/verification/drivers/scripted_llm.py` (D2/D3)
- [ ] T012 Implement the in-process driver — orchestrator boot, namespaced session registration, real attachment upload that **reuses the upload route's own attachments store + `AttachmentRepository`** (real sha256/content-type sniff/category/ownership, not a hand-rolled INSERT), scripted-LLM drive of `handle_chat_message` with a capture socket, workspace/audit reads (`live_components`, `verify_chain`), `set_agent_scopes`, and `component_action` re-exec — in `backend/verification/drivers/in_process.py` (D2/D4/D5/D6; depends on T004, T007, T010, T011)
- [ ] T013 Implement the closed-loop runner (plan→act→observe→verify, hard step/turn/time bounds, informed retries with carried-forward failure, definite pass/fail/uncertain) in `backend/verification/runner.py` (FR-001/005/006, D13; depends on T005, T006, T009, T012)
- [ ] T014 Implement the pytest `conftest` (orchestrator + shared-Postgres boot, scripted-LLM + namespaced-principal fixtures, guaranteed teardown) in `backend/verification/tests/conftest.py` (depends on T007, T012)

**Checkpoint**: Foundation ready — user stories can proceed (in parallel if staffed).

---

## Phase 3: User Story 1 — Tangible, server-driven UI across personas (Priority: P1) 🎯 MVP

**Goal**: Prove file-upload queries yield interactive, file-derived, persisted, re-executable components for each persona.

**Independent Test**: Run one persona end-to-end in-process; confirm the captured response contains ≥1 interactive component whose data reflects the uploaded file, that it persists in the workspace with a stable identity and survives reload, and that a text-only assistant could not produce it.

- [ ] T015 [P] [US1] Implement tangible-UI checks + counter-checks — `component_present`, `component_from_file` (known_markers provenance), `persisted_with_identity`, `survives_reload`, `re_executable` — in `backend/verification/checks/tangible_ui.py`, importing the shared `vocabulary_ok` (single implementation; see T022/D1) rather than redefining it (FR-010/011/012/013/023; data-model.md)
- [ ] T016 [US1] Wire US1 scenarios for all four personas (everyday→statement table+chart+metrics, researcher→dataset chart+stats and paper→tabbed summary, medical→synthetic labs flagged, government→budget breakdown+YoY) in `backend/verification/scenarios.py` (acceptance scenarios 1-6; depends on T009, T015)
- [ ] T017 [US1] Implement the unsupported-type observation check (upload an unsupported extension → observe draft→self-test→`pending_admin_approval` via `attachment_autoparse`/`parser_registry`, recorded as expected, not a harness error) in `backend/verification/checks/tangible_ui.py` (acceptance scenario 7, FR-015; depends on T015)
- [ ] T017a [US1] Implement the medical health-data-protection check — confirm health-categorized (synthetic) content engages the product's PHI/health protections, and that no real patient data is required/stored/transmitted — in `backend/verification/checks/tangible_ui.py` (Clarifications 2026-06-15 medical MUST; depends on T015)
- [ ] T018 [US1] In-process persona integration tests (each persona reaches a verdict; warranted queries yield file-derived components; persistence + identity + re-exec + reload; prose-only stays acceptable for non-warranting queries) in `backend/verification/tests/test_inprocess_personas.py` (SC-001/002/003/004; depends on T013, T016, T017)

**Checkpoint**: US1 fully functional and independently testable — this is the MVP.

---

## Phase 4: User Story 2 — Delegated authority on every interaction (Priority: P2)

**Goal**: Prove every interaction runs under scoped delegated authority with cross-user isolation, admin-only parser approval, and an unbroken audit chain.

**Independent Test**: With principals A, B, and an admin, drive a flow as A; reference A's attachment as B (refused); use an ungranted scope (withheld); attempt non-admin parser approval (denied); confirm each produced an audit record attributing the right principal and the chain verifies unbroken.

- [ ] T019 [P] [US2] Implement authority checks + counter-checks — `cross_user_refused`, `scope_withheld`, `disabled_tool_action_refused`, `admin_only_approval`, `delegation_attribution` (actor≠principal), `audit_chain_unbroken`, `denials_audited` — in `backend/verification/checks/authority.py` (FR-016/017/018/019/020; D5/D6/D7/D8)
- [ ] T020 [US2] Extend the in-process driver with multi-principal (A/B/admin) flows and delegated-authority evidence capture (delegation `act` claim via `delegation.py`, `actor_principal_from_claims` attribution, `_h_draft_approve` admin gate with synthetic-extension draft + teardown) in `backend/verification/drivers/in_process.py` (depends on T012)
- [ ] T021 [US2] Authority integration tests (cross-user refusal + no leakage via persistence/history; ungranted scope withheld; revoked-tool `component_action` refused+audited; non-admin approval refused, admin approval reaches go-live; chain unbroken; run-mode labelled) in `backend/verification/tests/test_authority.py` (SC-005/006/007/010; depends on T013, T019, T020)

**Checkpoint**: US1 AND US2 both work independently.

---

## Phase 5: User Story 3 — Backend-only UI / near-zero-logic client (Priority: P3)

**Goal**: Prove every component is from the backend's published vocabulary and arrives as server-produced markup, with a client that only injects output and forwards actions.

**Independent Test**: Capture a persona response and confirm each component's type ∈ `allowed_primitive_types()` and is accompanied by server-produced markup; statically inspect `client.js` and confirm no per-component construction logic and no client-side rendering framework.

- [ ] T022 [P] [US3] Implement thin-client checks + counter-checks — `server_markup_present`, `client_has_no_construction_logic`, `client_has_no_framework`, `device_diff_is_backend` (ROTE adapter compare), `action_is_backend_intent`, and the shared `vocabulary_ok` — in `backend/verification/checks/thin_client.py` (FR-023/024/025/026/027; D9/D10)
- [ ] T023 [US3] Thin-client + SDUI integration tests (zero out-of-vocabulary components; server `html` present; objective client-surface measurement recorded; device differences attributable to the backend adapter; action expressed as backend intent) in `backend/verification/tests/test_thin_client.py` (SC-008; depends on T013, T022)

**Checkpoint**: All three user stories independently functional.

---

## Phase 6: Polish & Cross-Cutting (reporting, differentiation, external surface, CLI, CI)

**Purpose**: The durable run record, the differentiation claim, the opt-in external surface, the CLI, the cross-cutting tests, and the CI merge-gate wiring.

- [ ] T024 [P] Implement the dual run record (`verdicts.json`) + generated Markdown report (`report.md`) + evidence-backed differentiation summary, written to the gitignored per-run dir in `backend/verification/report.py` (FR-008/028/029, SC-003; contracts/report-schema.md)
- [ ] T025 [P] Implement the optional LLM-as-judge enrichment (uses the existing `_call_llm`; never required; resolves to `na` when no real LLM, e.g. in CI) in `backend/verification/llm_judge.py`, **with co-located unit tests covering the `na` path and the reconciliation outcomes** in `backend/verification/tests/test_llm_judge.py` (FR-003, D1; coverage gate C1)
- [ ] T026 Implement the external-client driver (httpx REST upload + websockets `/ws` register_ui/chat_message/capture; real Keycloak via env-named creds; degrade-and-flag when unreachable) in `backend/verification/drivers/external.py`, **with unit tests using mocked httpx/websockets transports (no live network) covering capture, the Keycloak-unreachable degrade+flag, and credential-by-name handling** in `backend/verification/tests/test_external_driver.py` (FR-021/030, D11; coverage gate C1; depends on T010)
- [ ] T027 Implement the CLI `python -m verification` (mode/persona/base-url/out/run-id/llm-judge/strict flags; **normalize `--mode in-process`→`in_process`**; exit codes 0/1/2/3; report path printed) in `backend/verification/__main__.py`, **with unit tests covering arg parsing, mode normalization, and each exit code (mocked runner)** in `backend/verification/tests/test_cli.py` (FR-030; contracts/cli.md; coverage gate C1, I1; depends on T013, T024, T026)
- [ ] T028 [P] Runner termination + uncertain-handling tests (hard bounds enforced; informed retry caps; adversarial disagreement → uncertain; no hung run) in `backend/verification/tests/test_runner_termination.py` (SC-001/009, FR-005/006)
- [ ] T029 [P] Report + redaction tests (dual artifact produced; report derived from JSON so they agree; zero credential exposure; near-exposure flags the run) in `backend/verification/tests/test_report_redaction.py` (SC-011, FR-022/028)
- [ ] T030 [P] Isolation + cleanup tests (namespacing; teardown leaves no residue in real users' data; safe to run repeatedly) in `backend/verification/tests/test_isolation_cleanup.py` (SC-013, FR-031)
- [ ] T031 Wire the CI merge gate: append `verification/tests` to the **second** pytest invocation in `.github/workflows/ci.yml` (the explicit-module list with no `-m` filter) (Constitution XI, SC-012, D15)
- [ ] T032 [P] Add Google-style docstrings + a package README to `backend/verification/`, and confirm `ruff check .` is clean from the repo root (Constitution IV/VI)
- [ ] T033 Run quickstart.md validation — the in-process suite (`pytest verification/tests`) and one CLI run — and confirm the dual artifact + differentiation summary are produced (quickstart §1-2, §5-6)

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (P1)**: no dependencies.
- **Foundational (P2)**: depends on Setup — **blocks all user stories**.
- **User Stories (P3-P5)**: each depends only on Foundational; mutually independent (different check/test files). US2's T020 and US1's T016 both touch already-created shared files (`in_process.py`, `scenarios.py`) so are sequential within their story, not cross-story blockers.
- **Polish (P6)**: depends on the user stories whose verdicts it reports/wires; T031 (CI) should land once `verification/tests` exists.

### Within each user story

- Checks before the integration tests that exercise them.
- The runner + drivers (Foundational) precede every story's tests.

### Parallel opportunities

- Setup: T002, T003 in parallel.
- Foundational: T004, T005, T006, T007, T008, T010, T011 in parallel (distinct files); T009 after T008; T012 after T004/T007/T010/T011; T013 after T005/T006/T009/T012; T014 after T007/T012.
- Across stories (once Foundational done): T015 (US1), T019 (US2), T022 (US3) in parallel; their test files (T018/T021/T023) follow each story's checks.
- Polish: T024, T025, T028, T029, T030, T032 in parallel; T026→T027; T031 last among CI.

---

## Parallel Example: Foundational

```bash
# Distinct files, no interdependencies — run together:
Task: "Implement evidence.py redaction + CapturedEvidence (T004)"
Task: "Implement verdict.py reconciliation (T005)"
Task: "Implement checks/base.py Check ABC + replay (T006)"
Task: "Implement isolation.py namespacing + teardown (T007)"
Task: "Define personas.py + synthetic fixtures (T008)"
Task: "Implement drivers/base.py Driver protocol (T010)"
Task: "Implement drivers/scripted_llm.py reader→component chain (T011)"
```

## Parallel Example: user-story checks

```bash
# After Foundational, the three stories' check modules are independent:
Task: "tangible_ui.py checks + counters (T015, US1)"
Task: "authority.py checks + counters (T019, US2)"
Task: "thin_client.py checks + counters (T022, US3)"
```

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (CRITICAL) → 3. Phase 3 US1 → **STOP & VALIDATE**: run `pytest verification/tests/test_inprocess_personas.py` and confirm tangible, file-derived, persisted, re-executable components for each persona. This alone is a demonstrable deliverable (the differentiation evidence).

### Incremental delivery

1. Setup + Foundational → engine ready.
2. US1 → MVP (tangible UI evidence).
3. US2 → delegated-authority evidence.
4. US3 → backend-only-UI evidence.
5. Polish → run record, differentiation, external surface, CLI, CI gate.

### Parallel team strategy

After Foundational: Dev A → US1, Dev B → US2, Dev C → US3 (independent check/test files); reconvene for Polish (report/CLI/CI).

---

## Notes

- [P] = different files, no incomplete dependencies. Shared-file edits (`scenarios.py`, `in_process.py`) are sequential within a story.
- Every task names an exact file path under `backend/verification/` (except T002 `.gitignore`, T031 `.github/workflows/ci.yml`).
- No product code is modified; no new runtime dependency is added (FR-032, Constitution V).
- The verdict gate is deterministic; the LLM-judge (T025) is enrichment only and resolves to `na` in CI.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.
