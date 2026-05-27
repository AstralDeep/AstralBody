# Contract: WebSocket events (new)

Reuses the existing WS envelope (`backend/shared/protocol.py`). New surfaces use existing message types where possible; two additions are listed. All server→client UI uses existing `ui_render`/`ui_append` with existing primitive components (no new types).

## Reused (no change)
- **client→server** `ui_event` with `action="chat_message"` — carries ParamPicker submits and all personalization/skill/schedule interactions (the orchestrator interprets them and calls the new endpoints/tools).
- **server→client** `ui_render` (`components`, `target`) / `ui_append` — render the skills catalog, personality editor, memory viewer, schedule manager, and dream review, all from existing primitives.
- **server→client** `chat_step` — progress for scheduled-job execution (reuses feature 014 step kinds/statuses).

## New event 1 — `notification` (server→client, in-app delivery)
Emitted when a scheduled job completes or fails, or when a job is auto-paused for auth (FR-022/FR-024). Purely in-app; no external channel.
```json
{
  "type": "notification",
  "level": "info | success | warning",
  "source": "schedule | dreaming",
  "job_id": "uuid | null",
  "chat_id": "uuid | null",
  "title": "Morning brief is ready",
  "body": "3 items summarized in your chat.",
  "created_at": 1748340060000
}
```
- If the user is offline at completion, the result still persists to chat history; the notification is surfaced on next connect (best-effort, no external send).

## New event 2 — `offline_grant_request` (client↔server, consent capture)
Used during schedule creation to capture the offline grant from the live session (R2). When the user confirms a schedule that needs unattended authority and no valid grant exists:
- **server→client** `{ "type": "offline_grant_request", "reason": "schedule", "agent_id": "general" }`
- the client re-affirms consent and the server captures/encrypts the session's `offline_access` refresh token into `user_offline_grant` (server-side only; the token is never echoed back).
- **server→client** `{ "type": "offline_grant_ack", "ok": true, "expires_at": 1779790000000 }`

If the session lacks an `offline_access` refresh token (e.g., scope not requested), the server returns `{ "type": "offline_grant_ack", "ok": false, "reason": "offline_access_unavailable" }` and the schedule create fails with 422 (the user is told they must be in an interactive login to schedule unattended work).

## Invariants
- No WS event carries PHI in cleartext beyond what the live chat already shows; notification `body` is PHI-redacted.
- No event type enables external delivery; SC-006 holds by construction (there is no external-channel emitter).
