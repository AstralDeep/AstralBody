# Contract: Check & Verdict

**Feature**: 032 | Phase 1 | Authoritative for the replayable-check and verdict shapes (FR-002/003/004).

## Check interface (Python)

```python
class Check(Protocol):
    check_id: str                 # stable, e.g. "us1.component_from_file"
    property: Property            # tangible_ui | delegated_authority | backend_only_ui
    counter_check_id: str         # the adversarial counter-check (FR-003)
    is_deterministic: bool        # True for all gate checks (D1)

    def run(self, evidence: CapturedEvidence, inputs: dict) -> CheckResult: ...
    def counter(self, evidence: CapturedEvidence, inputs: dict) -> CheckResult: ...
```

- `run` and `counter` MUST be **pure** over `(evidence, inputs)` so a check replays identically from a persisted RunRecord (FR-002). No network, no clock, no randomness.
- `counter` attempts to **falsify** `run`'s positive conclusion (e.g., for `component_from_file`, the counter asserts the "found" markers are not generic/fabricated by checking they are absent from an empty-file control).

## CheckResult

```json
{
  "check_id": "us1.component_from_file",
  "outcome": "pass | fail | uncertain",
  "observed": { "...": "typed, redacted observation" },
  "reason": "human-readable, one line"
}
```

## Verdict (per check, scenario, property, run)

```json
{
  "verdict_id": "string",
  "scope": "check | scenario | property | run",
  "outcome": "pass | fail | uncertain",
  "confidence": "high | medium | low",
  "evidence_ref": "evidence_id",
  "refs": { "persona": "researcher", "scenario": "researcher:dose-response",
            "check": "us1.component_from_file", "counter_check": "us1.markers_not_generic" },
  "run_mode": "real_keycloak | mock_inprocess",
  "adversarial": { "deterministic": "pass", "llm_judge": "na", "reconciled": "pass" }
}
```

## Reconciliation rules (FR-003 / D13)

1. `outcome = pass` ⟺ `adversarial.deterministic = pass` AND `adversarial.llm_judge ∈ {pass, na}` AND the counter-check did NOT refute.
2. Any disagreement (deterministic vs llm_judge, or counter-check refutes) ⇒ `outcome = uncertain`, both evidences retained.
3. `llm_judge = na` whenever no real LLM is available (always in CI / scripted-LLM mode). The deterministic result is sufficient and authoritative.
4. A check that cannot observe its inputs (missing/garbled evidence) ⇒ scenario terminal `errored_observation`, NOT `fail` (FR-033).

## Replay

`replay(run_record)` re-executes every `Check.run`/`counter` against the persisted `CapturedEvidence` and MUST reproduce identical outcomes — the proof that verdicts rest on recorded evidence, not live state.
