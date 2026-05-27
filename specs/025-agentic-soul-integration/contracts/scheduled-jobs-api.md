# Contract: Scheduled Jobs ("cron") API

REST under `backend/scheduler/api.py`. All require auth; jobs strictly scoped to the caller. Every lifecycle action and run is audited (`event_class="schedule"`, FR-033). Delivery is **in-app only** (FR-022/SC-006).

## POST `/api/schedule`
Create a job. Requires explicit consent: the request must include `consented_scopes` and `consent: true`. On create, the server captures/links a `user_offline_grant` from the **live** session (refresh token) — see websocket-events + auth flow.
Request:
```json
{
  "name": "Morning brief",
  "agent_id": "general",
  "instruction": "Summarize what's on my plate today.",
  "schedule_kind": "cron",
  "schedule_expr": "0 7 * * 1-5",
  "timezone": "America/New_York",
  "consented_scopes": ["tools:read", "tools:search"],
  "consent": true,
  "target_chat_id": null
}
```
Responses:
- **201** → created job (see GET shape) with computed `next_run_at`.
- **400** → invalid `schedule_expr` for `schedule_kind`, or interval below the minimum floor (FR-038).
- **403** → `consented_scopes` exceed the user's current scopes on the agent (cannot consent beyond own authority).
- **409** → per-user active-job cap reached (FR-038): `{ "error": "job_cap_reached", "limit": N }`.
- **422** → `consent` missing/false, or no offline grant available (user must be in an interactive session to consent).

## GET `/api/schedule`
List caller's jobs.
```json
{ "jobs": [ {
  "id": "uuid", "name": "Morning brief", "agent_id": "general",
  "schedule_kind": "cron", "schedule_expr": "0 7 * * 1-5", "timezone": "America/New_York",
  "consented_scopes": ["tools:read","tools:search"], "status": "active",
  "next_run_at": 1748340000000, "last_run_at": 1748253600000,
  "grant_expires_at": 1779790000000
} ] }
```

## GET `/api/schedule/{id}` → single job + recent runs
```json
{ "job": { "...": "as above" },
  "runs": [ { "id":"uuid","started_at":...,"ended_at":...,"outcome":"success","summary":"3 items" } ] }
```

## POST `/api/schedule/{id}/run` → run-now (uses same auth/exec path); **202** with a `job_run` id.
## POST `/api/schedule/{id}/pause` / `/resume` → toggle `status`; **200**.
## DELETE `/api/schedule/{id}` → `status='disabled'` + cancel future runs; **204**. Emits `schedule.delete`.

## Execution invariants (documented for tests)
1. **Timing** (SC-007): a job fires within 1 minute of `next_run_at`; verified with a short-interval job.
2. **Authority** (FR-021/SC-008): each run mints a fresh access token from the offline grant, intersects job `consented_scopes` ∩ **current** `agent_scopes`, then RFC 8693 delegates. A run can never exceed the user's current scopes.
3. **Fail-safe** (FR-024): if the grant is revoked/expired or scopes were removed, the run records `job_run.outcome='skipped_auth'`, the job is paused/expired, and the user is notified in-app — no execution with stale authority.
4. **In-app delivery** (FR-022): outputs persist to `target_chat_id` history via `VirtualWebSocket`; a `notification` WS event fires; no external-channel code path exists.
5. **No PHI persisted** (FR-026): PHI in the run output is delivered/audited but never written to `memory_item`/`short_term_signal`.
6. **Restart** (FR-025): durable jobs survive restart; interrupted runs → `interrupted`.
