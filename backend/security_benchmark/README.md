# Security-Benchmark Harness (spec 047)

Measures Astral's **trust envelope** against standard adversarial agent-security
benchmarks — **AgentDojo**, **Agent Security Bench (ASB)**, **InjecAgent** — and
reports **Attack Success Rate (ASR)** with per-layer defense ablation. It is the
fastest credible proof-of-progress for the evaluation chapter (Direction B).

> **Eval/test-only.** Nothing here is imported by product runtime code. The
> `isolation_check` guard fails CI if `backend/orchestrator`, `backend/agents`,
> or `backend/shared` ever import this package or an external benchmark corpus
> (Constitution V, FR-009/SC-004).

## Quick start (runs anywhere, no DB)

```bash
cd backend
python -m security_benchmark --benchmark agentdojo            # AgentDojo ASR ablation
python -m security_benchmark --benchmark agentdojo --benchmark asb --benchmark injecagent
python -m security_benchmark --benchmark agentdojo --asr-threshold 0.20   # CI regression gate
python -m security_benchmark.isolation_check                  # dependency-isolation guard
```

Artifacts land in `backend/security_benchmark/_artifacts/<run_id>/`
(gitignored): per-benchmark `*.record.json` (machine-readable, reproducible) and
`ASR_REPORT.md` (the thesis table).

## Modes

| Mode | What it drives | Needs | CI role |
|---|---|---|---|
| `synthetic` (default) | deterministic scripted model of the gates | stdlib only | isolation + ablation + regression gate |
| `in_process` | the **real** orchestrator via the `llm_config` client-factory seam (real token exchange, scope check, PHI gate, red-team verdict, audit chaining) | backend importable + Postgres | gating when a DB is present |
| `external` | the deployed sandbox | live sandbox + Keycloak | opt-in, **non-gating** |

The `synthetic` and `in_process` drivers share the same adapter → adjudicator →
report core; only the source of the per-case trace differs. Synthetic assumes a
maximally-gullible model on injected cases (worst case for the defender), so any
ASR reduction is attributable to the **envelope**, not to model reticence;
in-process gets real bait-taking from the model under test.

## Defense ablation (the point)

Layers toggle independently so each mechanism's marginal ASR reduction is
attributable (US2). Ladder: `none` → `+DAF/scopes` → `+PHI gate` →
`+red-team verdict` → `+LLM-as-judge`. The **LLM-as-judge** layer is not built
yet (§9.2.4); its column is present but marked *not implemented* and the harness
starts measuring it automatically once `FF_LLM_JUDGE` lands (FR-004, US2-AS3).

Example (AgentDojo sample corpus, scripted model):

| Envelope | ASR | Δ vs prev |
|---|---:|---:|
| none | 0.833 | — |
| +DAF | 0.500 | +0.333 |
| +DAF+PHI | 0.333 | +0.167 |
| +DAF+PHI+RT | 0.167 | +0.167 |
| +DAF+PHI+RT+LLM *(not impl)* | 0.167 | +0.000 |

Each layer suppresses exactly the attack class it implements (DAF ⇒ out-of-scope
tool + escalation; PHI gate ⇒ PHI egress; red-team ⇒ exfiltration), and the
semantic-manipulation case survives until the LLM judge exists.

## Reproducibility, isolation, safety

- **Reproducible** — every number carries its `(model, benchmark_version, harness_version, seed)` key; re-running reproduces it (SC-006). Model nondeterminism (in-process/live) is reported as a band, never hidden.
- **Out-of-corpus** — cases needing capabilities Astral lacks are excluded from the ASR denominator and reported separately (FR-012), never silently scored.
- **Namespaced + synthetic + torn down** — in-process/external runs use `__bench__`-namespaced principals and synthetic data (PHI cases are synthetic only), and delete their rows on teardown so no adversarial payload settles into real memory/workspace (FR-008, SC-007).

## Loading the real corpora

Set `ASTRAL_BENCH_LOAD_REAL=1` and install the eval extras
(`pip install -r security_benchmark/requirements-eval.txt`). Offline/CI runs use
the committed representative samples so the pipeline is always exercisable.

## Adding a benchmark

Implement a `BenchmarkAdapter` that emits normalized `BenchmarkCase`s (mapping
the suite's ground truth onto `AdversarialObjective`) and register it in
`adapters/__init__.py`. No change to the adjudicator, report, or runner is needed
(US3).
