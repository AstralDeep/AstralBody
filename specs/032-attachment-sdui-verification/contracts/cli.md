# Contract: CLI (`python -m verification`)

**Feature**: 032 | Phase 1 | Authoritative for the external/opt-in runnable surface (FR-030).

## Usage

```text
python -m verification [--mode in-process|external] [--persona KEY ...]
                       [--base-url URL] [--out DIR] [--run-id ID]
                       [--llm-judge] [--strict] [--quiet]
```

| Flag | Default | Meaning |
|---|---|---|
| `--mode` | `in-process` | `in-process` (scripted LLM, no network) or `external` (live endpoints + real Keycloak). |
| `--persona` | all four | repeatable; restrict to specific personas. |
| `--base-url` | `$ASTRAL_VERIFY_BASE_URL` | external mode target (e.g., `https://sandbox.ai.uky.edu`). |
| `--out` | `backend/verification/.runs` | gitignored artifacts root; a `<run_id>/` subdir is created. |
| `--run-id` | derived from `--stamp`/env | namespace for principals + artifacts (callers pass a timestamp; scripts can't read the clock). |
| `--llm-judge` | off | enable optional LLM-as-judge enrichment (real LLM only; never required; ignored if no LLM). |
| `--strict` | off | any `uncertain` verdict → non-zero exit. |
| `--quiet` | off | suppress progress narration; still writes the run record. |

## Behavior

- Reads ALL identity/provider credentials by env-var NAME only (`KEYCLOAK_AUTHORITY`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`, `KEYCLOAK_REALM`, `KEYCLOAK_TOKEN_URL`); never accepts a secret value as an argument (FR-022).
- External mode: if Keycloak is unreachable, degrade to a clearly-labelled mock run and set the `keycloak_unreachable_degraded` flag (Edge case "Real Keycloak unreachable") — never emit a real-realm guarantee for it (SC-010).
- Writes `verdicts.json` + `report.md` to `<out>/<run_id>/` (FR-008/028).
- Always terminates within the aggregate budget; prints the report path and a one-line summary.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | no `fail` verdicts; no credential near-exposure (and, with `--strict`, no `uncertain`). |
| `1` | ≥1 `fail` verdict. |
| `2` | credential near-exposure flagged (fail-safe, FR-022) OR (`--strict`) ≥1 `uncertain`. |
| `3` | harness could not observe the system under test (FR-033) — distinct from "product is wrong". |

## CI relationship

CI does NOT call this CLI. The merge gate is the in-process **pytest** suite (`verification/tests`, `@pytest.mark.integration`, added to the test job's second invocation). The CLI is the human/opt-in surface — handy for an external real-Keycloak run against the sandbox deployment.
