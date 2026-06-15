# Contract: Offline-Grant Consent WebSocket Events (FR-003)

Captures the user's `offline_access` refresh token at job-creation consent time and writes the resulting grant id onto the scheduled job. Routed through the existing `ui_event` / `chrome_events.py` dispatch and `handle_ui_message`.

## Server → Client: `offline_grant_request`

Sent when a scheduled job is being created and unattended execution requires persistent authority.

```json
{
  "type": "offline_grant_request",
  "request_id": "<uuid>",
  "job_proposal_id": "<uuid>",
  "reason": "This recurring task needs permission to run while you're away.",
  "scopes": ["tools:read", "tools:write"]
}
```

## Client → Server: `offline_grant_ack`

The client affirms (or declines) capture of its offline-access refresh token.

```json
{
  "type": "offline_grant_ack",
  "request_id": "<uuid>",
  "job_proposal_id": "<uuid>",
  "granted": true
}
```

## Server behavior on ack

- If `granted` is `true`: call `OfflineGrantStore.capture(...)` using the live session's `offline_access` refresh token, obtain `grant_id`, and write it to the job's `offline_grant_id` (`scheduler/store.py`). Confirm to the user.
- If `granted` is `false`: create no grant; the job is created **paused** (or not created), and the user is told unattended runs are disabled for it.
- MUST be idempotent on `request_id` (no duplicate grant capture).
- MUST audit the consent decision (auth audit class).
- If `FF_SCHEDULER_EXECUTION` is disabled (no security sign-off, FR-005): the request flow MAY still capture consent, but the scheduling surface MUST clearly report that unattended execution is currently unavailable, and no execution loop runs.

## Failure modes

- No `offline_access` in the session → respond with an actionable error (user must re-auth with offline scope); do not silently create a job that can never run.
- Capture failure → no `offline_grant_id` written; job not left in a falsely-runnable state.
