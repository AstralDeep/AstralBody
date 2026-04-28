# Contract: Tutorial Steps (User-Scoped Read)

**Feature**: 005-tooltips-tutorial
**Owner module**: `backend/onboarding/api.py`
**Auth**: Keycloak JWT required. The caller's roles determine which steps are returned.

This is the read-only step list consumed by the tutorial overlay. The caller never sees archived steps. Non-admin callers never see `audience='admin'` steps.

---

## `GET /api/tutorial/steps`

Return the ordered list of tutorial steps applicable to the calling user. The server filters by `archived_at IS NULL` and by `audience` (always include `'user'` steps; include `'admin'` steps only if the caller has the admin role). The result is sorted by `display_order ASC, id ASC`.

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
      "body": "Let's take a quick tour."
    },
    {
      "id": 2,
      "slug": "chat-with-agent",
      "audience": "user",
      "display_order": 20,
      "target_kind": "static",
      "target_key": "chat.input",
      "title": "Chat with an agent",
      "body": "Type a message here to start a conversation with an agent."
    },
    {
      "id": 12,
      "slug": "feedback-admin",
      "audience": "admin",
      "display_order": 100,
      "target_kind": "static",
      "target_key": "sidebar.feedback-admin",
      "title": "Review feedback proposals",
      "body": "Admins review flagged feedback and proposed knowledge updates here."
    }
  ]
}
```

The frontend uses the order of the returned array directly; clients must not re-sort.

**Response 401**: Missing or invalid JWT.

---

## Test plan (backend)

- A non-admin caller never sees any step with `audience='admin'`.
- An admin caller sees both `user` and `admin` steps in a single combined ordering.
- Archived steps are not returned to either audience.
- Steps are returned in `display_order ASC, id ASC` order regardless of insertion order.
- Cross-user request: same caller from different sessions sees identical content; user identity does not affect the list except via role.
