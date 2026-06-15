# Implementation Plan: Finish Soul Integration

**Branch**: `030-finish-soul-integration` | **Date**: 2026-06-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/030-finish-soul-integration/spec.md`

## Summary

Bring feature 025 (agentic-soul-integration) to genuine end-to-end completion and finish feature 029's knowledge-base cleanup, closing the verified gaps from the 2026-06-15 implementation audit. This is a **remediation/wiring** feature: the underlying modules (scheduler runner/loop, offline-grant store, memory tools, dreaming consolidation, personalization panels, audit infra) already exist and are unit-tested — they are not reachable, not gated safely, not observable, or not covered. The work is to (1) add the missing orchestrator seams the scheduler runner already calls, (2) register memory tools and interpret onboarding submits using the existing `scheduling_chat.py` meta-tool pattern, (3) capture offline-grant consent over WS and gate unattended execution **fail-closed** behind a recorded security sign-off, (4) auto-register dreaming as a per-user recurring job, (5) add the deferred tests + structured observability to reach the ≥90% changed-code gate, and (6) durably remove retired/merged agents' knowledge files. No new user-facing capabilities; no new third-party libraries.

## Technical Context

**Language/Version**: Python 3.11+ (production image) / 3.13 (local `.venv`)
**Primary Dependencies**: FastAPI, websockets, psycopg2, the OpenAI-compatible LLM client (`_call_llm` via `llm_config.client_factory`), `cryptography` (Fernet, offline grants), `python-jose` (JWT), astralprims ≥0.2.0 (defines primitives), `shared.external_http`. PHI gate uses already-approved presidio/spacy/tzdata. **No new third-party runtime libraries.**
**Storage**: PostgreSQL via `shared/database.py::_init_db()` idempotent, guarded startup migrations. Existing tables reused: `scheduled_job`, `job_run`, `user_offline_grant`, `memory_item`, `short_term_signal`, `user_personalization`, `consolidation_sweep`. No new tables anticipated; any column addition (if needed for notification persistence) ships as an idempotent `_init_db` delta.
**Testing**: pytest (both CI invocations: default `tests` path `-m 'not integration'` + module dirs `audit/llm_config/orchestrator/onboarding/personalization/scheduler/dreaming`), FastAPI `TestClient`, coverage via `pytest-cov` + `diff-cover` (≥90% changed-code). Run locally via root `.venv` against docker `postgres:17-alpine` with `ASTRAL_ENV=development`.
**Target Platform**: Linux server container (orchestrator serving WS + REST + SDUI on `:8001`); web client via orchestrator render layer.
**Project Type**: Server-driven web service (single backend; no separate frontend).
**Performance Goals**: Scheduled jobs execute within their expected window (SC-001); no added latency to interactive chat. Background work (sweeps, runs) is off the request path.
**Constraints**: Fail-closed production posture (`ASTRAL_ENV` unset == production); unattended execution MUST NOT run without recorded security sign-off (FR-005); no token egress from offline-grant store; RFC 8693 delegation bounded by intersection of consented + live scopes; all new actions audited; no React/SPA reintroduction.
**Scale/Scope**: Per-user scheduled jobs and memory; existing user base. Scope strictly = audit-identified 025/029 gaps.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Primary Language (Python) | ✅ Pass | All changes are backend Python. |
| II. UI Delivery (SDUI) | ✅ Pass | Consent cards, notifications, onboarding all via astralprims primitives rendered by webrender; no SPA. |
| III. Testing (≥90% changed-code) | ✅ Pass (is a goal) | FR-015/FR-016 add the deferred tests and target the gate explicitly. |
| IV. Code Quality (ruff) | ✅ Pass | ruff clean repo-wide; CI enforces. |
| V. Dependency Management | ✅ Pass | FR-022: zero new third-party runtime libs. |
| VI. Documentation | ✅ Pass | FR-018 operator docs + `/docs` routers; docstrings on new seams; security sign-off recorded. |
| VII. Security | ⚠️ Central | FR-004 recorded lead-dev security review of offline-grant store; FR-005 fail-closed gate; FR-006 scope intersection; Keycloak/RFC 8693 unchanged. See Complexity Tracking. |
| VIII. User Experience | ✅ Pass | astralprims primitives only. |
| IX. Database Migrations | ✅ Pass | Any delta via idempotent `_init_db`; destructive knowledge-file deletion is intentional cleanup — recorded for lead-dev approval (see Complexity Tracking). |
| X. Production Readiness | ✅ Pass | This feature **removes** stubs/dead code (the broken seams, dead cron, dead call site) and adds observability (FR-017) + staging validation. |
| XI. Continuous Integration | ✅ Pass | Existing pipeline gates apply unchanged; coverage gate is the merge bar. |

**No unjustified violations.** Security (VII) and the destructive knowledge cleanup (IX) are tracked below.

## Project Structure

### Documentation (this feature)

```text
specs/030-finish-soul-integration/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (orchestrator seams, WS events, meta-tools)
│   ├── orchestrator-seams.md
│   ├── websocket-events.md
│   └── memory-meta-tool.md
├── checklists/
│   └── requirements.md  # Spec quality checklist (already created)
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── orchestrator/
│   ├── orchestrator.py        # ADD run_scheduled_turn(), notify_user(); wire memory meta-tool;
│   │                          #   interpret onboarding submits; fix personalization_skill_lines call site;
│   │                          #   gate scheduler loop start on recorded sign-off
│   ├── memory_chat.py         # NEW — memory meta-tool module (mirrors scheduling_chat.py)
│   ├── scheduling_chat.py     # reused as the pattern reference (no behavior change)
│   ├── offline_grant.py       # security-review sign-off recorded; gating constant
│   └── chrome_events.py       # WS offline_grant_request/ack handlers (consent capture)
├── scheduler/
│   ├── runner.py              # seams now satisfied; structured logs/metrics on run success/fail
│   ├── loop.py                # start gated by sign-off flag (fail-closed)
│   └── store.py               # offline_grant_id populated from captured grant
├── personalization/
│   ├── memory_tools.py        # reused; registered via memory_chat.py
│   ├── service.py             # ensure per-user dreaming job registration on init
│   └── repository.py          # dreaming job helpers; structured logs on memory writes
├── dreaming/
│   └── consolidation.py       # structured logs/metrics on sweeps
├── shared/
│   └── database.py            # idempotent delta only if notification persistence needs a column
├── knowledge/                 # DURABLE removal of retired/merged agent .md files (git-ignored)
└── tests/                     # deferred contract/integration tests + new-path coverage
    ├── personalization/tests/test_profile_api.py        # T013
    ├── onboarding/tests/test_personalize_steps.py       # T014
    ├── tests/integration/test_onboarding_personalization.py  # T015
    ├── personalization/tests/test_skills_api.py         # T024
    ├── personalization/tests/test_memory_api.py         # T033
    └── tests/test_scheduler_e2e.py                      # T040
docs/
└── keycloak-realm-settings.md # operator note corrections (FR-018)
```

**Structure Decision**: Single backend service (no frontend dir). Changes are concentrated in `backend/orchestrator/`, `backend/scheduler/`, `backend/personalization/`, `backend/dreaming/`, with one new module (`memory_chat.py`), deferred tests, and a durable `backend/knowledge/` cleanup. All existing modules are reused; this is wiring + tests + observability, not rebuild.

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Fail-closed scheduler gate tied to a recorded security sign-off (FR-004/FR-005) | Constitution VII: unattended execution under offline-grant authority MUST NOT run without lead-dev sign-off; the loop is currently live without it | "Just turn it on" rejected — ships security-critical code ungoverned; "leave it broken" rejected — silent failures + ungoverned authority. A recorded sign-off + fail-closed flag is the minimum safe mechanism. |
| Durable knowledge-file deletion in a git-ignored, runtime-indexed dir (FR-021) | A one-time `git rm` does not remove on-disk files in built images; the runtime indexer re-discovers them | A plain delete was the original (029) approach and is exactly what failed. Durability requires the files not to exist in the image build context AND the indexer not to re-create them — recorded as intentional destructive cleanup for lead-dev approval (Principle IX). |
