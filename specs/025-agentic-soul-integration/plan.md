# Implementation Plan: Agentic Soul Integration

**Branch**: `025-agentic-soul-integration` | **Date**: 2026-05-27 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/025-agentic-soul-integration/spec.md`

## Summary

Bring openclaw's agentic experience — personalized onboarding, enableable skills, agent personality ("soul"), cross-session memory, scheduled autonomous work ("cron"), and background consolidation ("dreaming") — into AstralBody **without weakening its security or HIPAA posture**, and rendered entirely through the existing server-generated UI primitives.

Technical approach: reuse AstralBody's existing machinery wherever it exists, and add the smallest number of new, security-equivalent pieces where it does not.

- **Personalization (profile, personality/"soul", memory)** is stored per-user in Postgres and injected into the orchestrator's LLM system prompt at the existing injection point (after the knowledge-synthesis block, before `_call_llm`). The personality is **subordinate** to the existing safety/compliance preamble.
- **Skills** are *not* a new artifact: a skill is an agent's tool, surfaced with a description and gated by the existing `agent_scopes` / `tool_overrides` model. The "catalog" is a read view over already-registered tools.
- **Onboarding** extends the existing `onboarding_state` + `tutorial_step` system with personalization steps rendered as **ParamPicker** primitives (profession/goals capture, skill toggles, personality choice).
- **Scheduled jobs ("cron")** add a durable job store + a single in-process asyncio scheduler loop that, when a job is due, executes it through the existing `BackgroundTaskManager` + `VirtualWebSocket` substrate (so outputs persist to chat history exactly like an async query). Cron/interval/one-shot timing is computed by a **pure-Python** evaluator (no new dependency).
- **Unattended authorization** is the one place the spec's "reuse persistent login" assumption breaks: persistent login is client-side only and RFC 8693 exchange needs a *live* token. So we add a **server-side, encrypted offline-grant store** that captures the user's Keycloak `offline_access` refresh token at job-creation consent time and, per run, exchanges it for a fresh access token → then performs the existing delegated (DPoP-bound) token exchange, **bounded by the user's current live-checked scopes** and capped at 365 days. This reuses the same Keycloak grant the login feature relies on; it does not introduce a new IdP path.
- **Dreaming** is a per-user-default-on consolidation sweep, itself implemented as a scheduled (system-owned) job that promotes high-signal **structured** short-term signals into durable memory.
- **PHI gate**: memory and short-term signals are gated by **Microsoft Presidio** running locally in-process (lead-dev-approved dependency, 2026-05-27) — every candidate value is blocked from durable memory if any HIPAA-relevant entity is detected. Structured typed categories are retained as defense-in-depth, with a cheap pure-Python pre-filter and fail-closed behavior if the detector is unavailable. PHI may still flow *through* a job run and be delivered/audited in-app, but never persists.

All new user-facing surfaces (onboarding, skills catalog, personality editor, memory viewer, schedule manager, dream review) render through the 27 existing primitives — **no new frontend component types** (SC-009).

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5.x on Vite + React 18 (frontend)
**Primary Dependencies**: FastAPI, `websockets`, `psycopg2` (the existing synchronous `shared.database.Database`), the existing OpenAI-compatible LLM client (`_call_llm`), `python-jose` (JWT), `cryptography` (already present — used for DPoP EC keys and will back offline-token encryption), `asyncio` (stdlib scheduler). Frontend: React 18, Tailwind, framer-motion, lucide-react, oidc-client-ts. **One approved new dependency**: `presidio-analyzer` + `presidio-anonymizer` (+ transitive spaCy + language model) for local PHI detection — lead-dev-approved 2026-05-27 per Constitution V. No other new third-party libraries (scheduling, cron, the PHI write-path glue remain pure-Python/stdlib).
**Storage**: PostgreSQL (existing). New per-user tables added idempotently in `backend/shared/database.py::Database._init_db()` following the existing `CREATE TABLE IF NOT EXISTS` + `_column_exists()` convention: `user_personalization`, `memory_item`, `short_term_signal`, `scheduled_job`, `job_run`, `consolidation_sweep`, `user_offline_grant`. New `event_class` values added to the audit `EVENT_CLASSES` tuple. No schema changes to existing tables except (optionally) none.
**Testing**: `pytest` + `ruff` (backend, ≥90% coverage on changed code per Constitution III); `vitest` + ESLint (frontend). Integration tests exercise scheduler timing, offline-grant re-derivation, PHI-gate rejection, and onboarding round-trip.
**Target Platform**: Linux server (Docker / docker-compose), modern browsers.
**Project Type**: Web application (existing `backend/` + `frontend/`).
**Performance Goals**: Scheduled jobs fire within 1 minute of due time (SC-007); per-turn personalization injection adds negligible latency (single indexed per-user read, cacheable); scheduler loop tick ≤ 30 s.
**Constraints**: HIPAA — in-app delivery only (no external channels), no PHI in durable memory, all actions audited; server-generated UI only (no new primitive types, Constitution VIII); no new third-party dependencies (Constitution V); single-orchestrator scheduling (durable + defined restart recovery).
**Scale/Scope**: Multi-tenant; per-user active-job cap and minimum-interval floor (configurable, FR-038); run-time concurrency reuses the existing `MAX_CONCURRENT_TASKS = 5` background-task cap.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Primary Language (Python backend) | ✅ PASS | All new backend code is Python. |
| II. Frontend Framework (Vite+React+TS) | ✅ PASS | No frontend stack change; new UIs are server-generated via existing primitives, so frontend deltas are minimal/none. |
| III. Testing ≥90% | ✅ PASS (planned) | Unit + integration tests planned for scheduler, offline-grant, PHI gate, memory CRUD, onboarding, prompt injection. |
| IV. Code Quality (PEP 8 / ESLint) | ✅ PASS | Enforced in CI. |
| V. Dependency Management (no new libs) | ✅ PASS w/ approval | **One approved exception**: `presidio-analyzer`/`presidio-anonymizer` (+ transitive spaCy + model) for PHI detection — explicitly approved by the lead developer / product owner on 2026-05-27 and to be documented in the PR per Constitution V (Apache-2.0, runs locally). All other new code stays pure-Python/stdlib: cron/interval evaluation, scheduler loop, and memory write-path glue use **no** croniter/APScheduler/Celery; offline-token encryption uses the already-present `cryptography`. See research.md R1, R3, R5. |
| VI. Documentation | ✅ PASS | Docstrings/JSDoc; new REST endpoints surface at `/docs`. |
| VII. Security | ⚠️ PASS w/ review | Reuses Keycloak, RFC 8693 delegation, DPoP, per-agent scopes, hash-chained audit. **New sensitive surface**: a server-side encrypted store of user `offline_access` refresh tokens (research.md R2). Requires: encryption at rest, per-run live scope re-check, revocation honoring, 365-day hard cap, and audit of every mint. Flagged for lead-dev security review. |
| VIII. User Experience (primitives) | ✅ PASS | All new surfaces use the existing 27 primitives (ParamPicker/Card/Table/Button/Alert/…); **no new primitive types** (SC-009). |
| IX. Database Migrations | ✅ PASS | Follows the established project migration convention — idempotent DDL auto-applied on startup in `Database._init_db()` (`CREATE TABLE IF NOT EXISTS` + `_column_exists()` guards), which is this project's auto-migration mechanism and satisfies Principle IX's intent (versioned-in-code, auto-applied, idempotent, safe on repeat). Consistent with spec FR-037. |
| X. Production Readiness | ✅ PASS (planned) | No stubs; structured logs + audit for every new action; configurable limits (no hard-coded host/secret); scheduler + offline-grant changes validated end-to-end in staging before merge. |

**Initial gate: PASS** (two ⚠️ items are constraints/review-flags, not violations). No entries required in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/025-agentic-soul-integration/
├── plan.md              # This file
├── research.md          # Phase 0 output (decisions: offline-grant, PHI gate, cron, scheduler, prompt injection)
├── data-model.md        # Phase 1 output (new tables + entities)
├── quickstart.md        # Phase 1 output (how to exercise each story locally)
├── contracts/           # Phase 1 output (REST + WS contracts)
│   ├── personalization-api.md
│   ├── scheduled-jobs-api.md
│   ├── memory-api.md
│   ├── onboarding-personalization.md
│   └── websocket-events.md
└── checklists/
    └── requirements.md  # (from /speckit-specify)
```

### Source Code (repository root)

```text
backend/
├── shared/
│   ├── database.py              # EXTEND _init_db(): new tables + helper methods
│   └── primitives.py            # REUSE (no new primitive types)
├── orchestrator/
│   ├── orchestrator.py          # EXTEND: inject personality+memory+skill guidance into system prompt
│   │                            #         (after knowledge-synthesis block, before _call_llm)
│   ├── async_tasks.py           # REUSE BackgroundTaskManager + VirtualWebSocket as the job runtime
│   ├── tool_permissions.py      # REUSE for skill (=tool) gating
│   └── delegation.py            # REUSE exchange_token_for_agent; called by scheduler runner
├── personalization/             # NEW module
│   ├── repository.py            # profile, personality, memory CRUD (per-user scoped)
│   ├── service.py               # prompt-fragment assembly; memory recall; "remember" capture
│   ├── phi_gate.py              # PHI exclusion gate (reuses audit pii sanitization + structured fields)
│   ├── memory_tools.py          # orchestrator-callable: memory_search / memory_get / remember
│   ├── api.py                   # REST: profile/personality/memory get/put/delete
│   └── schemas.py
├── scheduler/                   # NEW module
│   ├── store.py                 # scheduled_job / job_run durable persistence
│   ├── cron.py                  # PURE-PYTHON next-run evaluator (one-shot / interval / cron, tz-aware)
│   ├── loop.py                  # single asyncio scheduler loop (startup task); restart recovery
│   ├── runner.py                # executes a due job via offline-grant → delegation → BackgroundTaskManager
│   ├── governance.py            # per-user cap + min-interval floor + fairness
│   ├── api.py                   # REST: list/create/inspect/run-now/pause/resume/delete jobs
│   └── schemas.py
├── auth/ (orchestrator)         # EXTEND: offline-grant capture + server-side refresh exchange
│   └── offline_grant.py         # NEW: encrypted store + mint-fresh-access-token-from-refresh
├── dreaming/                    # NEW module (thin; rides on scheduler + personalization)
│   ├── consolidation.py         # signal scoring + promotion (structured, non-PHI)
│   └── api.py                   # REST: enable/disable/trigger + sweep review
├── onboarding/                  # EXTEND existing module
│   ├── api.py / repository.py   # EXTEND for personalization steps
│   └── seeds/                   # NEW personalization tutorial steps (sdui ParamPicker targets)
└── audit/
    └── schemas.py               # EXTEND EVENT_CLASSES tuple with new classes

frontend/
└── src/
    ├── components/DynamicRenderer.tsx   # REUSE (renders all server-generated surfaces)
    └── components/settings/             # MINIMAL: add entry points (skills/personality/schedule/memory)
                                         #          that open a server-generated panel; no new render logic
```

**Structure Decision**: Web application (Option 2). The feature is overwhelmingly backend: new `personalization/`, `scheduler/`, and `dreaming/` modules, an `offline_grant` extension to auth, an extension to `onboarding/`, and a system-prompt injection in `orchestrator.py`. Frontend work is intentionally near-zero because every new surface renders through the existing primitives + `DynamicRenderer`; only thin entry points (buttons that request a server-generated panel) may be added.

## Complexity Tracking

> No Constitution violations require justification. The two ⚠️ gate items are handled as explicit constraints (pure-Python scheduling/cron/PHI per Principle V) and a flagged security review (server-side offline-grant store per Principle VII), both documented in research.md — not deviations from the constitution.
