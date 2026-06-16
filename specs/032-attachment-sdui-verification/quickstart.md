# Quickstart: Agentic File-Upload SDUI & Delegated-Authority Verification

**Feature**: 032 | Phase 1

The harness lives at `backend/verification/`. Everything runs in the `astralbody` container (Python 3.11, shared Postgres). No new dependencies.

## 1. In-process (the deterministic CI gate)

Runs the whole pipeline with a scripted LLM — no network, no real LLM, no live deployment.

```bash
# Whole in-process suite (this is what CI runs as a merge gate)
docker exec astralbody bash -c "cd /app/backend && python -m pytest verification/tests -q"

# A single persona / property file
docker exec astralbody bash -c "cd /app/backend && python -m pytest verification/tests/test_inprocess_personas.py -q"
docker exec astralbody bash -c "cd /app/backend && python -m pytest verification/tests/test_authority.py -q"
```

Because the suite is `@pytest.mark.integration`, the default fast loop (`-m 'not integration'`) skips it; CI runs it via the explicit second invocation (see §4).

## 2. In-process via the CLI (writes a run record)

```bash
docker exec astralbody bash -c "cd /app/backend && python -m verification --mode in-process --run-id __verif__local01"
# → backend/verification/.runs/__verif__local01/{verdicts.json, report.md}
```

## 3. External (opt-in, real Keycloak, real LLM)

Proves the same properties through the real network surface. NOT a merge gate. Credentials are read by env-var NAME only — never pass secret values as arguments.

```bash
export ASTRAL_VERIFY_BASE_URL="https://sandbox.ai.uky.edu"
# KEYCLOAK_AUTHORITY / KEYCLOAK_CLIENT_ID / KEYCLOAK_CLIENT_SECRET / KEYCLOAK_REALM
# must already be present in the environment (by name).
python -m verification --mode external --run-id __verif__ext01 --out /tmp/astral-verif
# If Keycloak is unreachable, the run degrades to a clearly-labelled mock run (flagged), never a real-realm guarantee.
```

## 4. CI wiring (one-line edit)

Append `verification/tests` to the **second** pytest invocation in `.github/workflows/ci.yml` (the explicit-module list with no `-m` filter; it already exports `ASTRAL_ENV=development`, DB env, `AGENT_API_KEY`, `AUDIT_HMAC_SECRET`):

```text
... && python -m pytest audit/tests llm_config/tests orchestrator/tests onboarding/tests \
        personalization/tests scheduler/tests dreaming/tests verification/tests \
        -q --cov=. --cov-append --cov-report=xml:coverage.xml
```

## 5. What "pass" proves (acceptance, mapped to spec)

- **US1 / SC-002,003,004**: each warranting persona query returns ≥1 interactive component whose data comes from the uploaded file, persisted under a stable identity, re-executable, surviving reload.
- **US2 / SC-005,006,007,010**: cross-user reference refused; ungranted scope withheld; non-admin parser approval refused; every action audited on-behalf-of the user by a scoped delegate; chain unbroken; run mode labelled.
- **US3 / SC-008**: every delivered type ∈ `allowed_primitive_types()`; client surface measured to have no construction logic and no rendering framework.
- **Cross-cutting / SC-001,009,011,012,013**: every scenario reaches a bounded verdict; positive verdicts adversarially corroborated; zero credential exposure; runs in CI without a live deployment; leaves no residue in real users' data.

## 6. Reading the report

`report.md` is the stakeholder view: a per-persona × per-property verdict table, the coverage actually exercised, and the evidence-backed differentiation list ("what a text-only assistant can't do"). `verdicts.json` is the machine-readable, replayable record behind it.

## 7. Cleanup

The harness namespaces all principals/chats/attachments/drafts as `__verif__…` and tears down deletable rows + blobs on completion. Audit rows are append-only by design and remain — but only ever under namespaced principals, never under a real user.
