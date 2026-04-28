# Quickstart: Agent & User Action Audit Log

**Branch**: `003-agent-audit-log`
**Audience**: developer or operator wiring up / verifying this feature locally.

## 1. Prerequisites

- PostgreSQL reachable from `backend/` (existing dev DB).
- `backend/.venv/Scripts/python.exe` exists (per project memory). All Python commands below assume this interpreter.
- An `AUDIT_HMAC_SECRET` value available to the backend process. For dev, set it in the existing env-loading mechanism alongside other secrets — do not commit it.

## 2. Apply the migration

The migration creates the partitioned `audit_events` table, the two roles (`app_audit_role`, `audit_retention_role`), the indices, the `audit_events_no_update` trigger, and the first 24 monthly partitions ahead of `now()`.

```
backend/.venv/Scripts/python.exe -m alembic upgrade head
```

Verify role grants:

```
psql -d astralbody -c "\dp audit_events"
```

You should see `INSERT, SELECT` for `app_audit_role`, `DELETE` for `audit_retention_role`, and **no UPDATE** for any role.

## 3. Start the backend

```
backend/.venv/Scripts/python.exe start.py
```

Recording sites are wired automatically (R10): the FastAPI middleware, WS handlers, orchestrator tool dispatch, and Keycloak auth callbacks all emit through `backend/audit/recorder.py`.

## 4. Smoke-check the user-facing flow

1. Log in as `dev-user-id` (mock auth).
2. Send a chat message that triggers an agent tool call.
3. Click the **Audit log** button in the main app chrome → land on `/audit`.
4. Confirm the entry for the tool call appears within ~5 s without refreshing (FR-010, SC-001).
5. Click the entry → detail drawer shows inputs/outputs metadata, outcome, and a link back to the conversation (US2).
6. Open `/audit` in another browser as a different user (e.g., adjust mock auth to `other-user`) and confirm the first user's entry is **not** visible (FR-007, FR-019).

## 5. Convince yourself admin-blindness holds

Run the dedicated integration test:

```
backend/.venv/Scripts/python.exe -m pytest backend/tests/integration/audit/test_admin_blindness.py -v
```

This test:

- Inserts audit rows for users `alice` and `bob`.
- Issues a Keycloak-signed token with the highest privileged role available in the project's role catalog.
- Hits `GET /api/audit` and `GET /api/audit/{bob's event_id}` as that admin token.
- Asserts the admin sees **only its own** rows (or none if the admin user has none) and that fetching bob's event by ID returns 404 (indistinguishable from non-existence).
- Asserts the WS publisher does not deliver bob's events to the admin's WS connection.

A failure here is a P0 — do not merge.

## 6. Convince yourself tamper-detection holds

```
backend/.venv/Scripts/python.exe -m backend.audit.cli verify-chain --user-id dev-user-id
```

The CLI walks the user's chain forward from genesis, recomputes `entry_hash` for each row, and compares. Any mismatch is reported with the offending row's `event_id`. To exercise the path, manually edit a row in a scratch DB and rerun — the verifier should flag it.

(Note: the CLI is *operator-side*, not exposed via the user-facing API. It exists only on the server.)

## 7. Convince yourself recording coverage holds

```
backend/.venv/Scripts/python.exe -m pytest backend/tests/integration/audit/test_recording_coverage.py -v
```

This test exercises every authority boundary listed in research.md §R10 and asserts each produces an audit row. New recording sites added later MUST add a case here (FR-021).

## 8. Retention

The retention job is a scheduled task (cron / k8s CronJob in prod; an opt-in CLI in dev):

```
backend/.venv/Scripts/python.exe -m backend.audit.cli purge-expired
```

Connects under `audit_retention_role` (separate credential) and `DROP`s any partition whose entire range is older than 6 years from `now()`. The application role is unaffected. Each purge action emits a system-level operations log entry (not a user audit event — there is no user to attribute it to).

## 9. Operator follow-ups (deferred from MVP)

These are tracked in research.md §"Open follow-ups" and are intentionally out of scope here:

- AU-5 alerting on audit-emit failures.
- AU-4 capacity monitoring.
- WORM/object-lock cold tier for partitions older than ~13 months.
- Forensic / subpoena access flow (out-of-band, separately scoped, must itself emit into the affected user's log per FR-019).

## 10. Frontend dev tips

- The audit-log route is at `frontend/src/pages/AuditLogPage.tsx`. It uses `useAuditStream` (WS) and the `audit.ts` REST client.
- All UI is composed from existing primitives in `frontend/src/catalog.ts` (constitution Principle VIII). If you find yourself wanting a new primitive, raise it for approval before building it.
- The route reflects filter and pagination state in the URL so deep links work (FR-005). Test by copying the URL with filters applied into a new tab.
