# Implementation Plan: Security-Benchmark Harness — ASB / AgentDojo Against the Trust Envelope

**Branch**: `047-security-benchmark-harness` | **Date**: 2026-07-02 | **Spec**: [spec.md](spec.md)
**Framing source**: [`docs/thesis/thesis-statement-memo.md`](../../docs/thesis/thesis-statement-memo.md) (Direction B, non-negotiable).

## Summary

Stand up an **eval/test-only** harness (`backend/security_benchmark/`) that adapts AgentDojo, ASB, and InjecAgent onto Astral's agent/tool surface, drives them through the trust envelope, and reports **Attack Success Rate** with independent defense-layer ablation. Deterministic adjudication over the tool-call/audit trace (no model decides pass/fail). Mirrors the feature-032 verification harness posture: in-process CI-gating default (real gates via the `llm_config` client-factory seam), opt-in live path, namespaced principals, gitignored artifacts. **Zero new product-runtime dependencies** (Constitution V); an automated isolation guard enforces it.

## Technical Context

**Language/Version**: Python 3.11 (backend image); harness core uses **stdlib only** (runs in CI with an empty install).
**System under measurement (never modified, FR-011)**: `orchestrator/delegation.py`, `tool_permissions.py`, `personalization/phi_gate.py`, the red-team scope/egress verdict (`qual_audit`/`redteam`), and the hash-chained `audit/`.
**Injection seam**: the `llm_config` client-factory (same seam the 032 harness uses).
**Testing**: `security_benchmark/tests/` — adjudicator determinism, ablation numbers, isolation guard, cross-benchmark schema. All run without a DB.
**Storage**: gitignored `backend/security_benchmark/_artifacts/<run_id>/` (per-case JSON + `ASR_REPORT.md`).
**Constraints**: bounded, pinned CI config within budget; live model/network runs opt-in and non-gating.

## Constitution Check

- **V (no new runtime deps)**: PASS — core is stdlib; external benchmark corpora + `hypothesis` are eval-only in `requirements-eval.txt`, never imported by product runtime. **`isolation_check.py` proves it and gates CI (SC-004).**
- **Isolation precedent (032)**: PASS — namespaced `__bench__` principals, synthetic data, teardown, gitignored artifacts.
- **Cross-client parity**: N/A — measurement infrastructure; no wire-protocol, primitive, or UI surface touched. Web/Windows/Android clients unaffected (verified: no `ui_protocol.json`, `webrender`, or client path in the diff).
- **Determinism (Principle XI spirit)**: PASS — adjudication is deterministic; model nondeterminism reported as a band, never hidden.

Gate result: **PASS**.

## Project Structure

```
backend/security_benchmark/            # eval-only package
├── __init__.py            # HARNESS_VERSION (stamped into every run)
├── config.py              # RunConfig (model, benchmarks, seed, ablation, threshold)
├── envelope.py            # EnvelopeConfig — the ablation axis (5 layers)
├── adjudicator.py         # deterministic 4-outcome adjudication (FR-003/006/012)
├── run_record.py          # (model, benchmark_ver, harness_ver, seed) + per-case (FR-005)
├── report.py              # ASR + ablation table + cross-benchmark summary (FR-007)
├── isolation.py           # __bench__ namespaced principals + teardown (FR-008)
├── isolation_check.py     # dependency-isolation guard (FR-009, SC-004)
├── runner.py              # adapter → driver → adjudicate → record → report
├── __main__.py            # CLI + CI regression gate (FR-010)
├── adapters/{base,agentdojo,asb,injecagent}.py   # per-suite translators (FR-002, US1/US3)
├── drivers/{base,synthetic,inprocess}.py         # scripted (CI) + real-orchestrator seam
├── requirements-eval.txt  # eval-only deps (never in backend/requirements.txt)
├── README.md
└── tests/                 # runnable proof (adjudicator, ablation, isolation, schema)
```

**Structure Decision**: sibling eval area to `backend/verification/` (032). No product package imports it.

## Phased Approach

**Phase 0 — Study precedent.** Mirror 032's `RunConfig` / `Verdict-Outcome` / `isolation.py` / drivers patterns.

**Phase 1 — Core (US1).** Normalized case/trace model (`adapters/base.py`), deterministic adjudicator (4 outcomes, attempt-vs-effect point), run record, ASR report.

**Phase 2 — Ablation (US2).** `EnvelopeConfig` with 5 independently-toggleable layers; `LAYER_FOR_OBJECTIVE` for mechanistic attribution; LLM-judge column present-but-unimplemented.

**Phase 3 — Adapters (US1/US3).** AgentDojo, ASB, InjecAgent adapters emitting one schema; real-corpus loading behind `ASTRAL_BENCH_LOAD_REAL`, representative samples for CI/offline.

**Phase 4 — Drivers.** `synthetic` (deterministic, CI-runnable) + `inprocess` (real orchestrator via client-factory seam, DB-gated).

**Phase 5 — CI + isolation (US4).** CLI regression gate; `isolation_check.py` as unit test + standalone.

**Phase 6 — Verify** (done, in the real container): 14/14 tests green; ASR ablation reproduced; isolation guard green; regression gate trips on threshold breach.

## Evidence (verified in the `astralbody` container, Python 3.11)

- 14/14 harness tests pass.
- AgentDojo/ASB baseline ASR 0.833 → full-implemented-envelope 0.167; InjecAgent 0.750 → 0.000; each layer's marginal reduction attributable to the attack class it implements; LLM-judge column present with +0.000 (unbuilt).
- `isolation_check` green (no product module imports the harness or a benchmark package).
- CI regression gate exits non-zero when full-envelope ASR exceeds the threshold.

## Complexity Tracking

No constitution deviations. The only third-party items (benchmark corpora, `hypothesis`) are eval-only and isolation-guarded — the documented, gate-enforced exception the spec calls for, not a product-runtime dependency.
