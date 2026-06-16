# Implementation Plan: Agentic File-Upload SDUI & Delegated-Authority Verification

**Branch**: `032-attachment-sdui-verification` | **Date**: 2026-06-16 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/032-attachment-sdui-verification/spec.md`

## Summary

Deliver an autonomous, closed-loop **verification harness** (a new test-side Python package, `backend/verification/`) that drives the *existing* AstralBody upload → parse → server-driven-UI → delegated-authority → audit pipeline and proves three differentiating properties across four personas (everyday person, researcher, medical professional, government official): **(1)** file-upload queries yield tangible, file-derived, persisted, re-executable server-driven UI components; **(2)** every interaction happens under scoped **delegated authority** with cross-user isolation, admin-only parser approval, and an unbroken tamper-evident audit chain; **(3)** the interface is generated only from the backend's published component vocabulary with a near-zero-logic client.

The harness is **agentic in structure and judgment but deterministic in its verdict gate** (clarification 2026-06-16). It runs on two surfaces sharing one core: an **in-process** path — driving `Orchestrator.handle_chat_message` with a deterministic **scripted LLM injected through the existing client-factory seam** and capturing the exact server→client messages via the `VirtualWebSocket`-style buffer — packaged as a `@pytest.mark.integration` suite that becomes a **CI merge gate**; and an **opt-in external client** path (websockets + httpx against a live deployment and the real Keycloak realm) that reproduces the same verdicts through the real network surface. Output is a **dual run record**: machine-readable JSON verdicts + a stakeholder-readable Markdown report, written to a gitignored, per-run-namespaced artifacts directory. No product behavior changes; no new runtime dependencies.

## Technical Context

**Language/Version**: Python 3.11+ (backend runtime image; local `.venv` 3.13). Test-side package only.
**Primary Dependencies**: Existing only — `pytest` + `pytest-asyncio` (asyncio_mode=auto), the in-process `Orchestrator` and `VirtualWebSocket` (`orchestrator/async_tasks.py`), the LLM client-factory seam (`llm_config/client_factory.py`, injected via `orch._call_llm`), `astralprims` (component type assertions), `webrender.allowed_primitive_types()` (published vocabulary), `audit` repository (`verify_chain`, `actor_principal_from_claims`), `workspace` (`live_components`, identity), `delegation.py` (RFC 8693), `attachments` store/repository, `parser_registry`/`attachment_autoparse`. External mode reuses already-present `websockets` and `httpx`/`requests`. **No new third-party runtime libraries** (Constitution V, FR-032).
**Storage**: No schema change (FR-032). The harness reads existing tables (`user_attachments`, `message_attachment`, `chats`, `messages`, `saved_components`, `workspace_layout`, `audit_events`, `agent_scopes`, `tool_overrides`, `draft_agents`, `attachment_parser`) and writes to them only as a side effect of driving the product under **namespaced harness principals**, then tears down deletable rows. Run records are files under a gitignored artifacts dir.
**Testing**: `pytest`. In-process suite marked `@pytest.mark.integration`, run in CI by appending `verification/tests` to the test gate's second invocation (which carries no `-m` filter). Deterministic via the scripted LLM.
**Target Platform**: Linux container (`astralbody`), shared live Postgres; CI = built image vs `postgres:17-alpine`, development posture.
**Project Type**: Backend verification/test harness + CLI (`python -m verification`). No UI is added; the existing SDUI client surface is *inspected*, not modified.
**Performance Goals**: Each persona scenario reaches a definite verdict within a bounded budget (default per-scenario: ≤ 8 plan→act→observe→verify steps, ≤ 6 ReAct turns, ≤ 60 s wall-clock in-process, ≤ 2 informed retries). Full in-process suite target < ~90 s so it fits the 30-minute CI test job comfortably alongside the existing suites.
**Constraints**: Deterministic verdict gate (no model dependency for pass/fail). Credentials by env-var NAME only, never embedded/logged; fail-safe redaction (FR-022/SC-011). Fail-closed posture preserved (dev posture in CI like all suites). Must not pollute real user data (namespacing + teardown, FR-031).
**Scale/Scope**: 4 personas × (1–3 scenarios) ≈ 6–10 in-process scenarios; ~3 file categories (tabular, document, image) + 1 unsupported-type probe; ~15 structured checks across US1/US2/US3, each with an adversarial counter-check.

## Constitution Check

*GATE: evaluated against constitution v2.1.0. Re-checked after Phase 1 design — still PASS.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Primary Language (Python) | PASS | Entire harness is Python. |
| II. UI Delivery Architecture (SDUI) | PASS | Adds no UI and no primitives; *observes* the existing SDUI and *statically inspects* `client.js` without modifying it. |
| III. Testing Standards (≥90% changed-code coverage) | PASS | The in-process suite covers the harness's own changed lines; coverage flows into the existing `coverage.xml` → diff-cover gate. |
| IV. Code Quality (ruff/PEP 8) | PASS | New package lints under repo-root `ruff`; docstrings on public functions. |
| V. Dependency Management (no new deps) | PASS | stdlib + already-present packages only (FR-032). Documented in PR. |
| VI. Documentation | PASS | Google-style docstrings; this plan + contracts + quickstart; check/verdict schemas documented. |
| VII. Security (Keycloak, RFC 8693, secrets) | PASS | Verifies — does not weaken — the delegation model; reads creds by env NAME only; never embeds/logs secrets; adds no alternative auth provider. |
| VIII. User Experience (astralprims) | PASS | No new primitives; asserts the property that delivered types ∈ published vocabulary. |
| IX. Database Migrations | PASS | No schema change; only product-path writes under namespaced principals (FR-032). |
| X. Production Readiness | PASS | No stubs; error paths handled (FR-033 distinguishes "product wrong" vs "harness could not observe"); observability via the run record; preserves fail-closed posture. |
| XI. Continuous Integration | PASS | In-process suite wired as a merge gate by adding `verification/tests` to the existing test job's second invocation (CI-config change, not a product change). |

**Result**: No violations. Complexity Tracking left empty.

The only edit outside the new `backend/verification/` package is a one-line addition of `verification/tests` to the `.github/workflows/ci.yml` test gate's second pytest invocation. This is a CI-configuration change (permitted; CI-only), not a change to product upload/parse/render/authorization/audit behavior.

## Project Structure

### Documentation (this feature)

```text
specs/032-attachment-sdui-verification/
├── spec.md              # Feature specification (clarified)
├── plan.md              # This file
├── research.md          # Phase 0 — decisions + rationale (seams, determinism, isolation, CI wiring)
├── data-model.md        # Phase 1 — Persona, Scenario, Check, Evidence, Verdict, RunRecord, DA-assertion
├── quickstart.md        # Phase 1 — how to run (in-process pytest + external CLI)
├── contracts/           # Phase 1 — Check, Verdict, Driver, Report, CLI, scripted-LLM contracts
│   ├── check-and-verdict.md
│   ├── driver.md
│   ├── report-schema.md
│   └── cli.md
└── checklists/
    └── requirements.md  # (existing) spec quality checklist
```

### Source Code (repository root)

```text
backend/verification/                 # NEW test-side package (sibling of audit/, feedback/, llm_config/)
├── __init__.py
├── __main__.py                       # CLI: python -m verification --mode {in-process|external} [--persona ...] [--out DIR]
├── config.py                         # RunConfig: mode, base_url, out dir, budgets, credential env-var NAMES, redaction patterns
├── isolation.py                      # namespaced principals (__verif__<run>_<persona>_<role>) + teardown (FR-031)
├── personas.py                       # extensible Persona catalogue (everyday/researcher/medical/government)
├── fixtures/                         # synthetic, clearly-labelled inputs (csv, document, image, unsupported-ext) — no real PII/PHI
├── scenarios.py                      # Scenario = persona + file + query + expected properties + auth mode
├── evidence.py                       # CapturedEvidence dataclasses + secret-safe redaction
├── verdict.py                        # Outcome enum, Verdict, confidence, deterministic↔LLM-judge reconciliation
├── runner.py                         # closed-loop agent: plan→act→observe→verify, bounded steps/turns, informed retries
├── report.py                         # dual writer: verdicts.json + report.md + differentiation summary
├── llm_judge.py                      # OPTIONAL LLM-as-judge enrichment (existing _call_llm; never required; off in CI)
├── drivers/
│   ├── __init__.py
│   ├── base.py                       # Driver protocol: authenticate / upload / send_query / capture / read_workspace / read_audit / set_scope
│   ├── in_process.py                 # Orchestrator + VirtualWebSocket + scripted LLM + direct DB/audit/workspace reads
│   ├── external.py                   # websockets + httpx vs live endpoints + real Keycloak (opt-in)
│   └── scripted_llm.py               # deterministic per-scenario LLM: reader→component-emitting-tool chain from real output
├── checks/
│   ├── __init__.py
│   ├── base.py                       # Check ABC (typed input→typed result), registry, replay, adversarial pairing
│   ├── tangible_ui.py                # US1: component-present, file-provenance, persistence+identity, re-exec, vocabulary
│   ├── authority.py                  # US2: scope-withheld, cross-user isolation, admin-only approve, delegation attribution, audit-chain
│   └── thin_client.py                # US3: vocabulary, server-markup, static client inspection, ROTE adaptation, action-intent
└── tests/                            # pytest INTEGRATION suite = CI merge gate (scripted-LLM, in-process)
    ├── __init__.py
    ├── conftest.py                   # orchestrator+DB boot, namespaced principals, scripted-LLM fixtures, teardown
    ├── test_inprocess_personas.py    # US1 per-persona (SC-001..004)
    ├── test_authority.py             # US2 (SC-005..007, SC-010)
    ├── test_thin_client.py           # US3 (SC-008)
    ├── test_runner_termination.py    # FR-005/006 bounds + uncertain handling (SC-009)
    ├── test_report_redaction.py      # FR-008/022/028 dual artifact + secret redaction (SC-011)
    └── test_isolation_cleanup.py     # FR-031 namespacing + teardown (SC-013)

.github/workflows/ci.yml              # EDIT: append `verification/tests` to the test gate's 2nd pytest invocation
.gitignore                            # EDIT: ignore the run-artifacts dir (e.g., backend/verification/.runs/ or /tmp/astral-verif/)
```

**Structure Decision**: A single new backend package `backend/verification/` (functional name, sibling of the other cross-cutting modules) holds the entire harness — drivers, checks, runner, personas, fixtures, reporting, and its own pytest integration suite. This keeps all verification logic test-side and importable from the `cd /app/backend && pytest` working directory the project already uses, with zero product-code edits. The only out-of-package touches are a one-line CI test-invocation addition and a `.gitignore` entry for the run-artifacts directory.

## Complexity Tracking

> No Constitution violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
