# Tasks: Security-Benchmark Harness

**Feature**: 047-security-benchmark-harness | **Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)
Verified in the `astralbody` container (Python 3.11): 14/14 tests green.

## Phase 0 — Setup

- [X] T001 Create `backend/security_benchmark/` (eval-only sibling to `backend/verification/`), package `__init__` with `HARNESS_VERSION`.
- [X] T002 `requirements-eval.txt` — eval-only deps; NOT added to `backend/requirements.txt` (Constitution V).
- [X] T003 gitignore `backend/security_benchmark/_artifacts/`.

## Phase 1 — Adjudication + reporting core (US1, P1)

- [X] T004 `adapters/base.py` — normalized `BenchmarkCase` / `AdversarialObjective` / `CaseTrace` / `ToolCallObservation`; adapter ABC.
- [X] T005 `adjudicator.py` — deterministic 4-outcome adjudication (SUCCEEDED/BLOCKED/NOT_ATTEMPTED/OUT_OF_CORPUS); attempt-vs-effect point (FR-003, FR-006, FR-012).
- [X] T006 `run_record.py` — `(model, benchmark_version, harness_version, seed)` key + per-case; JSON writer (FR-005, FR-007).
- [X] T007 `report.py` — ASR, marginal reductions, ablation table, cross-benchmark summary (FR-007).

## Phase 2 — Ablation axis (US2, P1)

- [X] T008 `envelope.py` — 5 independently-toggleable layers, `LAYER_FOR_OBJECTIVE` attribution map, `NOT_IMPLEMENTED = {llm_judge}`, default ladder (FR-004).
- [X] T009 LLM-judge column present-but-unimplemented, valid table without it (US2-AS3).

## Phase 3 — Adapters (US1, US3, P2)

- [X] T010 `adapters/agentdojo.py` (US1) — categories spanning every implemented layer + control + out-of-corpus.
- [X] T011 `adapters/asb.py` + `adapters/injecagent.py` (US3) — same schema; registry in `adapters/__init__.py`.
- [X] T012 Real-corpus load behind `ASTRAL_BENCH_LOAD_REAL`; representative samples for CI/offline.

## Phase 4 — Drivers (FR-001)

- [X] T013 `drivers/synthetic.py` — deterministic scripted gates (CI-runnable, no DB); gullible-model assumption documented.
- [X] T014 `drivers/inprocess.py` — real orchestrator via `llm_config` client-factory seam; env-toggled layers; DB-gated with a clear runtime guard.

## Phase 5 — CI gate + isolation (US4, P2)

- [X] T015 `runner.py` + `__main__.py` — CLI, `--asr-threshold` regression gate (FR-010).
- [X] T016 `isolation_check.py` — AST scan asserting no product module imports the harness/benchmarks; unit test + standalone (FR-009, SC-004).

## Phase 6 — Tests & verification (in the real container)

- [X] T017 `tests/test_adjudicator.py` — 4 outcomes + determinism + attempt-vs-effect (7 tests).
- [X] T018 `tests/test_ablation.py` — baseline/full ASR, per-layer attribution, marginal-sum, LLM-judge-unimplemented, reproducibility (SC-001/002/006).
- [X] T019 `tests/test_isolation_check.py` — isolation holds + multi-benchmark same schema (SC-003/004).
- [X] T020 **Verify:** `docker exec astralbody python -m pytest security_benchmark/tests -q` → **14 passed**. CLI reproduces the ASR ablation; isolation guard green; regression gate trips on threshold breach.

## Deferred (documented, not blocking)

- [ ] T021 Wire the `inprocess` driver's live turn execution end-to-end against the DB-backed orchestrator (the CI-gating run). Seam + env-toggling + trace extraction points are in place; live corpus normalization + turn capture land when the gating CI job is provisioned (mirrors 032's live path being manual). Synthetic mode already gates isolation + ablation + regression in CI.
- [ ] T022 LLM-as-judge layer itself is a **separate build** (§9.2.4); this harness measures it once `FF_LLM_JUDGE` lands (FR-011 — harness never builds the defense it measures).

## Dependencies

- Fed by: 045 (Direction B non-negotiable); the existing gate modules are the system under measurement; 032 is the architectural precedent.
- Feeds: the evaluation chapter; the measurement slot for the LLM-judge; the before/after numbers the DAF (A, spec 048) and self-extension (D) chapters cite.
- Sibling (non-blocking): 048 — its property tests are unit-level; this harness is the system-level adversarial complement.
