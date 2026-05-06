# Contract — User Tool-Selection Preference API

## Endpoints

### `GET /api/users/me/tool-selection?agent_id={agent_id}`

Returns the current user's saved tool-selection preference for the specified agent.

**Auth**: existing Keycloak bearer token; user identity derived from token claims.

**Path/query params**:

- `agent_id` (query, required): the agent whose selection to fetch.

**Response 200**:

```json
{
  "agent_id": "agent_123",
  "selected_tools": ["search_web", "read_file"]
}
```

If the user has not narrowed the selection for this agent, the response is:

```json
{
  "agent_id": "agent_123",
  "selected_tools": null
}
```

A `null` value (vs. an empty array) signals "no narrowing — use default" (FR-019). The frontend MUST distinguish `null` from `[]`.

**Errors**: 401 unauthorized; 404 if `agent_id` is not visible to the user.

---

### `PUT /api/users/me/tool-selection`

Saves the current user's tool-selection preference for an agent.

**Request body**:

```json
{
  "agent_id": "agent_123",
  "selected_tools": ["search_web", "read_file"]
}
```

- `selected_tools` MUST be a strict subset of the tools the agent exposes that are also permitted to the user (i.e., would pass `is_tool_allowed`). The backend re-validates this; tools that fail the check are rejected with 400.
- `selected_tools` MUST NOT be empty. Zero-selection is enforced at the UI layer per FR-021; if a client somehow sends `[]`, the backend MUST reject with 400 (`reason: "empty_selection_not_allowed"`).

**Response 200**: same shape as GET.

**Errors**: 400 invalid selection; 401 unauthorized; 404 unknown agent.

---

### `DELETE /api/users/me/tool-selection?agent_id={agent_id}`

Implements the FR-025 "reset to default" action. Removes the user's saved selection for the agent so subsequent queries fall back to the agent's full permission-allowed set (FR-019).

**Response 204** on success.

**Errors**: 401 unauthorized.

---

## Persistence

Backed by the existing `user_preferences` JSON column under the key `tool_selection.<agent_id>` (see [data-model.md](../data-model.md#3-user_preferences-existing--json-key-added-under-existing-column)). No new table.

## Observability

Every PUT / DELETE emits a structured log line including `user_id`, `agent_id`, `selected_tool_count`, `action="set"|"reset"`. Reads are not logged at INFO; counts are emitted as a metric for SC-006.
