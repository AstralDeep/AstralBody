# Contract: Onboarding State (User-Scoped)

**Feature**: 005-tooltips-tutorial
**Owner module**: `backend/onboarding/api.py`
**Auth**: Keycloak JWT required. `user_id` is **always** the validated JWT subject — never a request parameter.

All endpoints reject any request that includes a `user_id`, `actor_user_id`, `as_user`, or similar override parameter with `400 Bad Request` (mirroring feature 003's strict per-user policy).

---

## `GET /api/onboarding/state`

Return the calling user's onboarding state. If no row exists, returns the implicit default (`status = "not_started"`).

**Response 200**:

```json
{
  "status": "not_started" | "in_progress" | "completed" | "skipped",
  "last_step_id": 7 | null,
  "last_step_slug": "open-audit-log" | null,
  "started_at": "2026-04-28T17:14:02Z" | null,
  "completed_at": "2026-04-28T17:18:31Z" | null,
  "skipped_at": null
}
```

**Response 401**: Missing or invalid JWT.

---

## `PUT /api/onboarding/state`

Idempotently upsert the calling user's onboarding state. The server computes the audit-log effects:

- Transition from absent/`not_started` → `in_progress` records `onboarding_started`.
- Transition to `completed` records `onboarding_completed` and sets `completed_at = now()`.
- Transition to `skipped` records `onboarding_skipped` and sets `skipped_at = now()`.

**Request body**:

```json
{
  "status": "in_progress" | "completed" | "skipped",
  "last_step_id": 7 | null
}
```

**Validation**:
- `status` is required and must be one of the three writable values; clients cannot set `not_started` (delete is not exposed).
- `last_step_id`, when non-null, must reference a non-archived step the caller is allowed to see (i.e., a `user`-audience step, or an `admin`-audience step if the caller has admin role). Otherwise `400 Bad Request`.
- Forbidden monotonicity: a row already in `completed` or `skipped` cannot transition back to `in_progress` via this endpoint (use `POST /api/onboarding/replay` for replay semantics). Returns `409 Conflict`.

**Response 200**: same shape as `GET /api/onboarding/state`.

**Response 400**: Validation failure (including disallowed override parameters).
**Response 401**: Missing or invalid JWT.
**Response 409**: Disallowed state transition.

---

## `POST /api/onboarding/replay`

Records that the user activated the replay affordance. Does **not** mutate `onboarding_state` (per research Decision 8) — the user's terminal state is preserved so auto-launch suppression remains correct.

**Request body**: empty.

**Response 204**: No content. An `onboarding_replayed` audit event is recorded with `prior_status` set to the current row's status (or `not_started` if no row exists).

**Response 401**: Missing or invalid JWT.

---

## Test plan (backend)

- `GET` returns `not_started` for a brand-new user.
- `PUT` from absent → `in_progress` records `onboarding_started` exactly once.
- `PUT` from `in_progress` → `completed` records `onboarding_completed` and sets `completed_at`.
- `PUT` from `completed` → `in_progress` returns `409`.
- `PUT` with a `user_id` query parameter returns `400`.
- `PUT` with a `last_step_id` pointing at an admin-audience step from a non-admin caller returns `400`.
- `POST /replay` does not change `status`/`completed_at`/`skipped_at`.
- Cross-user read leakage: a request authenticated as user A cannot, by any combination of parameters, read user B's row.
