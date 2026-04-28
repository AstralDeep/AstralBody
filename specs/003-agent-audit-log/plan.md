# Implementation Plan: Agent & User Action Audit Log

**Branch**: `003-agent-audit-log` | **Date**: 2026-04-28 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/003-agent-audit-log/spec.md`

## Summary

Deliver a per-user, append-only audit log covering every user-attributable action in AstralBody — both direct user actions (auth, conversation, file upload, settings) and agent actions performed on the user's behalf (tool calls, state-changing UI renders, external integrations). The log is read-only for the user, strictly admin-blind (no operator can read another user's log through this feature), retained for 6 years to satisfy HIPAA recordkeeping, and structured to satisfy NIST SP 800-53 AU controls (AU-2, AU-3, AU-8, AU-9, AU-11, AU-12). The user-facing surface is a dedicated, deep-linkable route in the SPA backed by a new REST endpoint and a live WebSocket stream of new entries while the route is open. Raw payload bytes are never copied into the audit row; entries hold non-PHI metadata + a stable pointer to source artifacts in their original stores. PHI-bearing fields (filenames, payload digests) use either a generated artifact ID or HMAC/per-tenant-salted constructions to resist re-identification.

## Technical Context

**Language/Version**: Python 3.11 (backend, per `backend/.venv` + constitution Principle I); TypeScript 5+ on Vite + React (frontend, per constitution Principle II)
**Primary Dependencies**:
  - Backend: FastAPI (existing), Pydantic, SQLAlchemy + Alembic for the audit store, `cryptography` (HMAC), structlog or stdlib `logging` for ops-level emission alongside structured DB persistence
  - Frontend: existing `useWebSocket` hook + DynamicRenderer/catalog primitives (constitution Principle VIII — no new bespoke components without approval)
**Storage**: PostgreSQL `audit_events` table (append-only, no UPDATE/DELETE grants for the application role), plus a write-only WORM-style cold archive for entries older than the active retention slice (e.g., S3-compatible object storage with object-lock / versioning; concrete provider deferred to ops). Hash-chain column links each entry to the prior entry in the same user's log to satisfy AU-9 integrity verification.
**Testing**: pytest (backend, ≥90% coverage per Principle III) — unit + integration including a tamper-detection test, an admin-blindness test, and a recording-coverage test that exercises every authority boundary; Vitest + React Testing Library on the frontend; Playwright (or existing equivalent) for the route-level user journey.
**Target Platform**: Linux server (FastAPI under uvicorn); browser SPA served by Vite for dev / static-host for prod. ROTE middleware adapts payloads for non-browser device classes — the audit-log route is browser-only in MVP.
**Project Type**: Web application (existing `backend/` + `frontend/` split — see Project Structure below).
**Performance Goals**:
  - SC-001: a new entry is visible to the user within 5 s in 95% of cases (live WS push budget)
  - SC-006: first page of audit-log entries renders in under 2 s for users with up to 10,000 historical entries
  - Recording overhead: audit emission MUST add no more than ~10 ms p95 to the action it describes (asynchronous fan-out from the orchestrator boundary)
**Constraints**:
  - HIPAA: 6-year retention from the action's recorded timestamp (FR-012); BAA-relevant data minimization (FR-004)
  - NIST SP 800-53 AU controls AU-2/3/8/9/11/12 (FR-020)
  - Admin-blind: no role, scope, or impersonation path may read another user's audit through this feature (FR-019)
  - Append-only: no UPDATE/DELETE pathway exists for application code (FR-014, FR-019, AU-9)
  - No raw payload bytes in the audit row (FR-004); filenames + digests handled per FR-015/FR-016
  - Constitution Principle VII: auth via Keycloak; agents use RFC 8693 attenuated-scope tokens — agent-action audit entries record the issuing user as `actor_user_id` (the on-behalf-of subject), not the agent's machine identity
**Scale/Scope**:
  - Up to 10,000 audit entries per user is the SC-006 sizing target; data model and indices MUST hold up to ≥10× that without query degradation
  - Recording sites span FastAPI handlers, WebSocket message handlers, the orchestrator tool-dispatch path, and a small set of `system_*` events (login/logout/refresh)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance | Notes |
|-----------|------------|-------|
| I. Primary Language (Python) | ✅ | All backend code is Python. |
| II. Frontend Framework (Vite + React + TS) | ✅ | Audit-log route is a TypeScript page added to the existing Vite/React app; uses existing `useWebSocket` hook and SDUI primitives. No new bundler / framework. |
| III. Testing Standards (90% + integration) | ✅ | Plan calls for unit, integration, and contract tests including admin-blindness, tamper-detection, and recording-coverage tests. CI coverage gate already enforces 90%. |
| IV. Code Quality (PEP 8 / ESLint) | ✅ | Standard tooling unchanged. |
| V. Dependency Management | ⚠️ Approval pending | Plan introduces no truly new runtime libraries (cryptography is stdlib-adjacent and likely already present transitively; SQLAlchemy/Alembic already in use). If a verified WORM/object-lock client is required for cold archive, that is the only candidate dependency and MUST follow Principle V (lead-developer approval, PR rationale). Recorded in Complexity Tracking. |
| VI. Documentation (docstrings, /docs) | ✅ | New audit endpoints exposed via FastAPI's existing `/docs`; data-model.md captures the schema; quickstart.md captures operator runbook. |
| VII. Security (Keycloak, RFC 8693) | ✅ | Audit-log API authenticates via the existing Keycloak JWT validation. Agent actions are recorded against the on-behalf-of user via the RFC 8693 actor claim (`act` claim); no new auth provider. FR-019 admin-blindness is enforced at the API layer (Principle VII bullet on API-layer authorization). |
| VIII. User Experience (primitives, SDUI) | ✅ | The audit-log route is composed from existing primitive components in `frontend/src/catalog.ts`. Any net-new primitive (e.g., a hash-chain integrity badge) MUST be approved & documented before use; absence of such a primitive is not a blocker — current primitives are sufficient for the MVP. |

**Result**: PASS with one tracked item under Principle V (potential WORM-archive client) — noted in Complexity Tracking, not a blocker for Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/003-agent-audit-log/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── rest-audit-api.md
│   ├── ws-audit-events.md
│   └── audit-event-schema.json
├── checklists/
│   └── requirements.md  # produced by /speckit.specify
└── tasks.md             # /speckit.tasks (not produced here)
```

### Source Code (repository root)

```text
backend/
├── audit/                          # NEW — feature module
│   ├── __init__.py
│   ├── models.py                   # SQLAlchemy AuditEvent (append-only)
│   ├── repository.py               # write/read DAO; integrity (hash-chain) helpers
│   ├── recorder.py                 # async fire-and-forget emit API used by handlers
│   ├── middleware.py               # FastAPI middleware: records direct user actions at API boundary
│   ├── ws_recorder.py              # hooks WebSocket message handlers in orchestrator
│   ├── orchestrator_hooks.py       # hooks Orchestrator.dispatch_tool / send_ui_render / external integrations
│   ├── api.py                      # FastAPI router: GET /api/audit, GET /api/audit/{id}
│   ├── ws_publisher.py             # publishes audit_append events on the user's existing WS
│   ├── retention.py                # 6-year retention scan + WORM archive boundary
│   ├── pii.py                      # filename redaction + HMAC digest helpers (FR-015/016)
│   └── schemas.py                  # Pydantic input/output models
├── alembic/versions/
│   └── XXXX_create_audit_events.py # migration: table, indices, role grants (no UPDATE/DELETE)
├── orchestrator/
│   └── orchestrator.py             # MODIFIED: emit audit at tool-dispatch / ui-render / external-call points
├── shared/
│   └── protocol.py                 # MODIFIED: add `audit_append` server→client message type
└── tests/
    ├── unit/audit/
    │   ├── test_pii.py
    │   ├── test_repository_hash_chain.py
    │   └── test_recorder.py
    ├── integration/audit/
    │   ├── test_admin_blindness.py        # FR-019 — explicit
    │   ├── test_recording_coverage.py     # FR-021 — every boundary emits
    │   ├── test_retention.py              # FR-012 / AU-11
    │   ├── test_tamper_detection.py       # AU-9 / hash chain
    │   ├── test_ws_live_push.py           # FR-010
    │   └── test_pointer_integrity.py      # FR-017 — dangling-pointer state
    └── contract/audit/
        └── test_rest_contract.py

frontend/
├── src/
│   ├── pages/
│   │   └── AuditLogPage.tsx        # NEW — dedicated route component
│   ├── routes.tsx                  # MODIFIED: add /audit route
│   ├── hooks/
│   │   ├── useWebSocket.ts         # MODIFIED: dispatch audit_append events to subscribers
│   │   └── useAuditStream.ts       # NEW — subscription hook for the route
│   ├── api/
│   │   └── audit.ts                # NEW — REST client for /api/audit
│   ├── components/audit/
│   │   ├── AuditEntryRow.tsx       # composed from existing primitives
│   │   ├── AuditDetailDrawer.tsx   # for US2
│   │   └── AuditFilters.tsx        # for US3
│   └── components/AppChrome.tsx    # MODIFIED: add "Audit log" button → /audit
└── tests/
    └── audit/
        ├── AuditLogPage.test.tsx
        ├── useAuditStream.test.ts
        └── e2e/audit_log.spec.ts   # Playwright: open route, see entries, refresh recovers gap
```

**Structure Decision**: The repository already follows a `backend/` + `frontend/` split. The audit feature is a new backend module (`backend/audit/`) plus narrow modifications to the existing orchestrator and protocol layer, paired with a new frontend route and a thin REST/WS client. No new top-level project; no constitution-impacting structural change.

## Phase 0 — Outline & Research

The following items are unknown or ambiguous from the spec and are resolved in [research.md](./research.md):

1. **NIST AU control mapping**: which exact controls (AU-2, AU-3, AU-8, AU-9, AU-11, AU-12) and what concrete implementation each demands.
2. **Append-only enforcement**: how to prevent UPDATE/DELETE in PostgreSQL at the role/grant level vs. application-only conventions.
3. **Hash-chain construction for AU-9**: per-user chain vs. global chain; rotation strategy; how to detect and surface tamper events.
4. **HMAC key custody for FR-016**: where the server-held HMAC key lives, rotation cadence, what happens to historical entries on key rotation.
5. **Filename handling per FR-015**: extension+ID vs. encrypted-field-with-separate-ACL — pick one and apply uniformly.
6. **WORM archive for entries past the active window**: are we keeping all 6 years online in PostgreSQL, or hot-cold splitting? What guarantees the archive itself satisfies AU-9?
7. **RFC 8693 actor mapping**: how the audit recorder extracts the on-behalf-of user from the agent's delegated token (claim path, fallback if absent).
8. **WebSocket event filtering**: confirm server-side filter so a user never receives another user's `audit_append` even by message-id collision.
9. **Asynchronous emission semantics**: fire-and-forget vs. transactional outbox — must satisfy SC-003 (100% recording) without blocking actions.
10. **Recording sites inventory**: complete list of authority boundaries that must emit audit events for FR-021 to hold.

**Output**: `research.md` with one Decision/Rationale/Alternatives block per item, all `NEEDS CLARIFICATION` resolved.

## Phase 1 — Design & Contracts

**Prerequisites**: research.md complete.

1. **Data model** → [data-model.md](./data-model.md): `audit_events` table schema, indices, hash-chain column, role grants, partitioning strategy if any, and the entity diagram (AuditEvent → User, AuditEvent → Conversation, AuditEvent → Agent, AuditEvent → ArtifactPointer). Includes state-transition diagram for the `outcome` field (in_progress → success | failure | interrupted).

2. **Contracts** → [contracts/](./contracts/):
   - `rest-audit-api.md` — `GET /api/audit` (paged list, filter params, returns only `actor_user_id == authenticated user`); `GET /api/audit/{event_id}` (404 if not the user's own); both reject any attempt to pass an `actor_user_id` query param that is not the caller's.
   - `ws-audit-events.md` — server→client `audit_append` message; subscription is implicit on `register_ui` and is filtered server-side.
   - `audit-event-schema.json` — JSON Schema for the public-facing audit event shape (a strict subset of the DB row — internal hash-chain link is NOT exposed).

3. **Quickstart** → [quickstart.md](./quickstart.md): operator runbook covering migration, role grants, key bootstrap, and the integration tests an operator runs to convince themselves admin-blindness and tamper-detection work end-to-end.

4. **Agent context update**: run `.specify/scripts/powershell/update-agent-context.ps1 -AgentType claude` to refresh `CLAUDE.md` with the new module paths.

**Outputs**: `data-model.md`, `contracts/*`, `quickstart.md`, refreshed agent context file.

## Post-Design Constitution Re-Check

Re-evaluated after research.md, data-model.md, contracts/, and quickstart.md landed:

| Principle | Post-design status | Notes |
|-----------|-------------------|-------|
| I. Primary Language (Python) | ✅ | Backend module is pure Python; no language drift introduced. |
| II. Frontend Framework | ✅ | New route + hooks are TypeScript on the existing Vite/React app. |
| III. Testing Standards | ✅ | Plan + contracts enumerate ≥6 distinct integration tests (admin-blindness, recording coverage, retention, tamper detection, WS live push, pointer integrity) plus contract tests; unit tests on PII helpers and hash-chain repository. ≥90% coverage on changed code is achievable and required for merge. |
| IV. Code Quality | ✅ | No new tooling. |
| V. Dependency Management | ✅ (with documented deferral) | Phase 1 design avoids any new runtime dependency in MVP — `cryptography` for HMAC is already in scope via Python stdlib (`hmac` + `hashlib`); SQLAlchemy/Alembic are in use; the WORM cold-tier was explicitly deferred in research.md §R6 and quickstart.md §9. If/when cold tier is added, it must follow Principle V approval. |
| VI. Documentation | ✅ | New endpoints surface in FastAPI's `/docs`; data-model.md and contracts/ documents complete the spec; quickstart.md is the operator runbook. |
| VII. Security | ✅ | Authorization via Keycloak JWT at the API layer; admin-blindness enforced server-side at both REST and WS; agent actions recorded against the on-behalf-of user via the RFC 8693 `act` claim per research.md §R7. |
| VIII. User Experience | ✅ | Route composes existing primitives from `frontend/src/catalog.ts`; no new primitive introduced. |

**Result**: Post-design check PASS. No new violations. Complexity Tracking entries above remain accurate (cold archive deferral is documented; multi-site recording remains the minimum to satisfy FR-021 + SC-003). Ready for `/speckit.tasks`.

## Complexity Tracking

| Violation / Risk | Why Needed | Simpler Alternative Rejected Because |
|------------------|------------|--------------------------------------|
| Possible new dependency (object-lock / WORM archive client) | NIST AU-9 / AU-11 over a 6-year window argues for a tamper-evident cold tier rather than relying solely on application role grants | Pure DB-grant-based append-only is simpler, but does not protect against a compromised DBA. If MVP keeps everything in PostgreSQL with hash-chain integrity checks, the WORM tier can land in a follow-up. Approval for any new client library MUST be obtained before introduction (Principle V). |
| Recording at multiple boundaries (API middleware + WS handlers + orchestrator hooks) | FR-021 and SC-003 (100% recording) require recording at *every* point authority is asserted; one global middleware cannot see WS messages or internal orchestrator tool dispatch | A single global middleware over only HTTP would silently miss WS-driven and agent-driven actions, violating FR-001/SC-003. The multi-site pattern is the minimum that covers the surface. |
