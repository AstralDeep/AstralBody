# Contract: Audit Action Types — Persistent Login

This feature adds **three new `action_type` values** under the existing `event_class="auth"` bucket. No new `event_class` is added.

## 1. The three new action types

| `action_type` | When emitted | `outcome` values |
|---------------|--------------|------------------|
| `auth.login_interactive` | Recorded by the orchestrator when a user reaches the WS register handler **and** the frontend's `register_ui` message included `resumed: false` (or omitted the field entirely — backward-compatible default). | `success`, `failure` |
| `auth.session_resumed` | Recorded by the orchestrator when `register_ui` includes `resumed: true` **and** the JWT validates successfully (silent resume succeeded). | `success` only |
| `auth.session_resume_failed` | Recorded by the orchestrator when `register_ui` includes `resumed: true` **but** JWT validation fails OR the WS register otherwise fails. Also recorded by the frontend after the 3-retry budget is exhausted (via a one-shot REST `POST /api/audit/session-resume-failed` endpoint — see §3). | `failure` only |

## 2. Recording sites

### Backend (Python)

In `backend/orchestrator/orchestrator.py`, inside the WS register handler, after parsing the `RegisterUI` message:

```python
# pseudo-code; mirrors existing auth audit hook style
resumed = register_msg.resumed or False
try:
    claims = await verify_token_ws(token)            # existing
    action = "session_resumed" if resumed else "login_interactive"
    await audit_record_auth(action=action, outcome="success", claims=claims, ...)
except JWTError as e:
    action = "session_resume_failed" if resumed else "login_interactive"
    await audit_record_auth(action=action, outcome="failure", claims=None, ...,
                             outcome_detail=str(e))
    raise
```

The existing `audit_record_auth` helper at [backend/audit/hooks.py:55](../../../backend/audit/hooks.py#L55) already takes `action` + `outcome` and writes `event_class="auth", action_type=f"auth.{action}"`. No changes to that helper are needed; the three new actions slot in automatically.

### Frontend (TypeScript)

Records nothing directly. The frontend's only audit-relevant duties are:

1. Set `resumed: boolean` correctly on the `register_ui` WS message (see [ws-register-flag.md](ws-register-flag.md)).
2. On the rare path where the retry budget is exhausted and the WS never actually connects (FR-011), POST a one-shot record to `/api/audit/session-resume-failed` so the failure is captured. Payload:
   ```json
   { "reason": "retry-budget-exhausted", "attempts": 3, "last_error": "Network request failed" }
   ```
   The endpoint validates the payload, looks up the user via the bearer token (or falls back to `actor_user_id="anonymous"` if no token is recoverable), and writes a single audit row with `event_class="auth", action_type="auth.session_resume_failed", outcome="failure"`.

> **Why a separate REST endpoint and not the WS?** If we have exhausted the retry budget, the WS connection has failed; we have no in-band channel. REST is the fallback.

## 3. New REST endpoint

**`POST /api/audit/session-resume-failed`**

- **Auth**: Bearer token if available; accepts an unauthenticated body and records `actor_user_id="anonymous"` in that case.
- **Body**:
  ```json
  {
    "reason": "retry-budget-exhausted" | "definitive-4xx" | "token-expired" | "deployment-mismatch",
    "attempts": <integer 0..3>,
    "last_error": "<string ≤ 500 chars>"
  }
  ```
- **Response**: `204 No Content` on success; `400` on malformed body; never `401` (we want to record even failed-auth cases).
- **Implementation**: ~25 LOC inside `backend/audit/api.py`, mirroring the existing `audit_view` recording pattern.

## 4. Example audit rows

```json
{
  "event_class": "auth",
  "action_type": "auth.login_interactive",
  "outcome": "success",
  "actor_user_id": "f47ac10b-…",
  "inputs_meta": { "preferred_username": "alice", "azp": "astral-frontend", "resumed": false },
  "started_at": "2026-05-15T14:30:00Z"
}
```

```json
{
  "event_class": "auth",
  "action_type": "auth.session_resumed",
  "outcome": "success",
  "actor_user_id": "f47ac10b-…",
  "inputs_meta": { "preferred_username": "alice", "azp": "astral-frontend", "resumed": true },
  "started_at": "2026-05-15T14:30:02Z"
}
```

```json
{
  "event_class": "auth",
  "action_type": "auth.session_resume_failed",
  "outcome": "failure",
  "actor_user_id": "f47ac10b-…",
  "inputs_meta": { "resumed": true },
  "outcome_detail": "Refresh token expired",
  "started_at": "2026-05-15T14:30:02Z"
}
```

## 5. Backward compatibility

- Existing audit-log readers that filter by `event_class` or by exact-match `action_type` strings continue to work; we are only *adding* new dotted-name values, never renaming or removing existing ones.
- The Audit Log frontend panel (`frontend/src/components/audit/AuditLogPanel.tsx`) renders any action_type string verbatim; no UI code change is needed.

## 6. Tests

Backend tests at `backend/audit/tests/test_session_resume_actions.py` (new):

- `test_resumed_true_records_session_resumed` — assert that a WS register with `resumed: true` + valid JWT writes `action_type="auth.session_resumed"`.
- `test_resumed_false_records_login_interactive` — assert the default path.
- `test_resumed_true_invalid_jwt_records_resume_failed`.
- `test_resumed_omitted_treated_as_false_for_backward_compat`.
- `test_session_resume_failed_rest_endpoint_records_anonymous_when_unauthenticated`.

All five MUST pass before this feature can be considered done.
