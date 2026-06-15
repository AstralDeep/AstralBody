# Quickstart: Finish Soul Integration

End-to-end validation for the remediation work. Run locally with the root `.venv` + docker postgres (per the project verification setup).

## Setup

```bash
docker compose up -d postgres                      # postgres:17-alpine, 127.0.0.1:5432
# .venv synced to backend/requirements.txt (astralprims>=0.2.0, a2a-sdk>=1.0.2)
./.venv/Scripts/python.exe -m pip install -r backend/requirements.txt --upgrade
```

All test commands run from `backend/` with `ASTRAL_ENV=development`.

## 1. Tests + coverage gate (FR-015/FR-016, SC-006)

```bash
cd backend
ASTRAL_ENV=development ../.venv/Scripts/python.exe -m pytest -q -m 'not integration'
ASTRAL_ENV=development ../.venv/Scripts/python.exe -m pytest audit/tests llm_config/tests orchestrator/tests onboarding/tests personalization/tests scheduler/tests dreaming/tests -q
# changed-code coverage:
diff-cover coverage.xml --compare-branch origin/main --fail-under=90
```
Expect: green suite; new files `test_profile_api.py`, `test_personalize_steps.py`, `test_skills_api.py`, `test_memory_api.py`, `tests/integration/test_onboarding_personalization.py`, `test_scheduler_e2e.py` present and passing; changed-code coverage ≥90%.

## 2. Scheduler runs safely or not at all (US1, SC-001/SC-002)

- With `FF_SCHEDULER_EXECUTION` unset/false: start the app; confirm the execution loop does NOT start (log line absent), the scheduling surface reports unattended execution unavailable, and `test_scheduler_e2e.py` proves no job-execution path is reachable.
- With sign-off recorded and `FF_SCHEDULER_EXECUTION=true`: create a one-shot job due now; confirm it runs, output lands in chat history, and an in-app `notification` arrives. Revoke the grant; confirm next run records `skipped_auth`, pauses, and notifies (no execution under stale authority).

## 3. Conversational memory (US2, SC-003)

- In chat: "Remember I prefer concise answers." → assistant stores it (audited).
- Later turn: "What are my answer preferences?" → assistant recalls via `memory_get`/`memory_search`.
- Attempt to store PHI-like content → refused, not persisted.

## 4. Onboarding personalizes (US3, SC-004)

- New user completes onboarding (profession/goals, enable ≥1 skill, personality) → profile + skills persist; enabled-skill guidance changes assistant behavior.
- Return as the same user → not re-onboarded; preferences in effect.

## 5. Dreaming runs automatically (US4, SC-005)

- User with `dreaming_enabled=true` → a per-user recurring consolidation job exists and fires on the default cadence; a `consolidation_sweep` row + structured log appear.
- Disable dreaming → no sweep runs; re-enable → resumes (no restart).

## 6. Observability (FR-017, SC-007)

Inspect logs/metrics for a scheduled run, a sweep, a memory write, and a grant mint — each emits a structured `extra={...}` log discoverable without code changes.

## 7. Knowledge cleanup (US6, SC-008)

```bash
# none of these should exist in the image build context, and the regenerated index has 0 refs:
ls backend/knowledge/capabilities/{grants,nefarious,classify,forecaster,llm_factory}.md   # → absent
ls backend/knowledge/techniques/{grants,nefarious,classify,forecaster,llm_factory}.md     # → absent
grep -E 'grants|nefarious|classify|forecaster|llm_factory' backend/knowledge/_index.md    # → no agent entries
```

## 8. Bookkeeping (FR-020, SC-010)

Confirm `specs/025-agentic-soul-integration/tasks.md` reflects reality: T022 (chrome surface), T050 (scheduling_chat) marked done; T018 annotated archived. No done-marked task contradicts the code.

## Staging (Constitution X)

Run §2–§6 against the live backend in staging with a real browser before declaring complete; record evidence in the PR.
