# Contract: Admin Tutorial Steps (Admin-Scoped Write)

**Feature**: 005-tooltips-tutorial
**Owner module**: `backend/onboarding/api.py`
**Auth**: Keycloak JWT required AND caller must have the admin role. Non-admin callers receive `403 Forbidden` (FR-018). The shared `require_admin` FastAPI dependency from feature 004 is reused.

All write operations record a `tutorial_step_edited` audit event (FR-017) and append a `tutorial_step_revision` row (data-model.md §3).

---

## `GET /api/admin/tutorial/steps`

Return the full step list, **including** archived steps, for admin editing. Includes both `user` and `admin` audience steps regardless of who is calling.

**Query parameters** (optional):
- `include_archived` (`bool`, default `true`) — set to `false` to mirror the user view.

**Response 200**:

```json
{
  "steps": [
    {
      "id": 1,
      "slug": "welcome",
      "audience": "user",
      "display_order": 10,
      "target_kind": "none",
      "target_key": null,
      "title": "Welcome to AstralBody",
      "body": "Let's take a quick tour.",
      "archived_at": null,
      "updated_at": "2026-04-28T17:14:02Z"
    }
  ]
}
```

**Response 401 / 403**: Missing JWT / non-admin caller.

---

## `POST /api/admin/tutorial/steps`

Create a new step.

**Request body**:

```json
{
  "slug": "review-feedback-quarantine",
  "audience": "admin",
  "display_order": 110,
  "target_kind": "static",
  "target_key": "sidebar.feedback-admin",
  "title": "Quarantine review",
  "body": "Quarantined feedback lands here for admin review."
}
```

**Validation**: as per data-model.md §2 (slug uniqueness, audience enum, target_kind/target_key consistency, non-empty title/body).

**Response 201**: created step row in the same shape as the GET response. A `tutorial_step_revision` row with `change_kind='create'` is written. An audit event with `event_class='tutorial_step_edited'` and `change_kind='create'` is recorded.

**Response 400**: Validation failure.
**Response 409**: `slug` already exists.

---

## `PUT /api/admin/tutorial/steps/{step_id}`

Edit an existing step. Partial update — only fields present in the request body are changed; `id`, `slug`, `created_at` cannot be modified through this endpoint.

**Request body** (any subset):

```json
{
  "audience": "user",
  "display_order": 25,
  "target_kind": "static",
  "target_key": "sidebar.audit",
  "title": "Open the audit log",
  "body": "Click here to review every action your agents have taken."
}
```

**Response 200**: updated step row. A `tutorial_step_revision` with `change_kind='update'`, `previous` = pre-edit snapshot, and `current` = post-edit snapshot is written. Audit event records `changed_fields` (list of column names whose values changed).

**Response 400 / 403 / 404**: Validation failure / non-admin / step not found.

---

## `POST /api/admin/tutorial/steps/{step_id}/archive`

Soft-delete a step (sets `archived_at = now()`). Idempotent — archiving an already-archived step returns `200` with no further effects.

**Response 200**: the updated step row. A `tutorial_step_revision` with `change_kind='archive'` is written.

**Response 403 / 404**: Non-admin / step not found.

---

## `POST /api/admin/tutorial/steps/{step_id}/restore`

Un-archive a previously archived step (sets `archived_at = NULL`). Idempotent.

**Response 200**: the updated step row. A `tutorial_step_revision` with `change_kind='restore'` is written.

**Response 403 / 404**: Non-admin / step not found.

---

## `GET /api/admin/tutorial/steps/{step_id}/revisions`

Return the revision history for a step in reverse-chronological order.

**Response 200**:

```json
{
  "revisions": [
    {
      "id": 17,
      "step_id": 2,
      "editor_user_id": "kc-uuid-of-admin",
      "edited_at": "2026-04-28T17:42:11Z",
      "change_kind": "update",
      "previous": { "title": "Chat with agent", "body": "...", "audience": "user", "...": "..." },
      "current":  { "title": "Chat with an agent", "body": "...", "audience": "user", "...": "..." }
    }
  ]
}
```

**Response 403 / 404**: Non-admin / step not found.

---

## Test plan (backend)

- `POST` with a non-admin JWT returns `403`.
- `POST` with a duplicate `slug` returns `409`.
- `PUT` writes a revision row whose `previous` matches the prior `current`.
- `PUT` audit event's `changed_fields` lists exactly the columns whose values changed (no false positives).
- `archive` followed by `restore` round-trips cleanly; both write revision rows.
- `archive` of step S removes S from `GET /api/tutorial/steps` for both audiences but it remains visible at `GET /api/admin/tutorial/steps?include_archived=true`.
- `archive` of a step that is referenced by a user's `onboarding_state.last_step_id` does not break that user's resume — they advance to the next non-archived step in order.
- All write endpoints record an audit event before returning success.
