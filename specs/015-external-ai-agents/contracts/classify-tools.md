# MCP Tool Contracts — CLASSify Agent

**Agent ID**: `classify-1`
**Underlying service**: `classify.ai.uky.edu` (URL is user-supplied; this is the placeholder hint)
**Auth**: `Authorization: Bearer <CLASSIFY_API_KEY>`
**Long-running tools**: `train_classifier`, `retest_model`

All tools below require `_credentials` (injected by orchestrator) carrying `CLASSIFY_URL` and `CLASSIFY_API_KEY`. Calls without both raise an `MCPError` with `code="credentials_missing"` which the orchestrator surfaces as the FR-009 "configuration required" alert.

---

## `train_classifier`

Start training a Random Forest classifier on a previously-uploaded CSV.

**Long-running**. Returns immediately with a job handle; the agent's poller pushes `ToolProgress` updates and a final result message into chat (FR-015). Counts against the FR-026 cap.

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "file_handle": {"type": "string", "description": "Handle to a CSV uploaded via AstralBody's file mechanism."},
    "class_column": {"type": "string", "description": "Name of the column to classify on."},
    "options": {
      "type": "object",
      "description": "Hyperparameter overrides. See get_ml_options for the option set.",
      "additionalProperties": true
    }
  },
  "required": ["file_handle", "class_column"]
}
```

**Synchronous return** (acknowledgment only):

```json
{
  "task_id": "<upstream ClearML task id>",
  "status": "started",
  "message": "Training started. Progress will be posted here as it runs."
}
```

**Pushed via ToolProgress** (asynchronously):
- intermediate: `{ "phase": "training", "percentage": 0..99, "message": "<upstream status>" }`
- terminal success: `{ "phase": "completed", "result": { "metrics": {...}, "shap_url": "...", "summary": "..." } }`
- terminal failure: `{ "phase": "failed", "message": "<reason>" }`
- transport-failure cutoff: `{ "phase": "status_unknown", "message": "Couldn't reach the service to confirm job status — try again later." }`

---

## `retest_model`

Run inference on a new test CSV using a previously-trained classifier.

**Long-running**. Same lifecycle pattern as `train_classifier`.

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "file_handle": {"type": "string"},
    "model_id": {"type": "string", "description": "Identifier of the trained model to reuse."}
  },
  "required": ["file_handle", "model_id"]
}
```

---

## `get_training_status`

Synchronous one-shot probe for an upstream training task. Exposed for explicit user "did my job finish?" queries; usually unnecessary because the poller pushes updates automatically.

**Input schema**:

```json
{
  "type": "object",
  "properties": { "task_id": {"type": "string"} },
  "required": ["task_id"]
}
```

**Returns**: `{ "task_id": "...", "status": "started"|"in_progress"|"succeeded"|"failed", "percentage": 0-100|null, "message": "..." }`

---

## `get_class_column_values`

Discovery helper. Lists distinct values in a column of a previously-uploaded CSV — useful before calling `train_classifier` so the user can confirm the class column has the right cardinality.

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "file_handle": {"type": "string"},
    "class_column": {"type": "string"}
  },
  "required": ["file_handle", "class_column"]
}
```

**Returns**: `{ "values": ["...", "..."], "count": <int> }`

---

## `get_ml_options`

Returns the upstream service's supported hyperparameter set. Cheap GET — also serves as the `_credentials_check` probe at credential save time (R-005).

**Input schema**: `{ "type": "object", "properties": {} }`

**Returns**: `{ "options": { ... } }` (passed through from upstream).

---

## `_credentials_check` (internal)

**Not** registered in the user-facing `tools/list`. Invoked by the orchestrator immediately after `PUT /api/agents/{agent_id}/credentials`. Calls `GET /get-ml-options` with the saved credentials and a 5-second timeout.

Returns one of:

```json
{ "credential_test": "ok" }
{ "credential_test": "auth_failed", "detail": "<upstream message>" }
{ "credential_test": "unreachable", "detail": "<network error>" }
{ "credential_test": "unexpected", "detail": "<status code or parse failure>" }
```

The orchestrator surfaces this verdict in the `PUT` response body so the frontend can render the FR-008 outcome.

---

## Error mapping (all tools)

| Upstream condition | Tool result |
|---------------------|-------------|
| 401 / 403 | `MCPError(code="auth_failed", message="The saved API key was rejected by the service. Update it in the agent's settings.")` (FR-021) |
| Connection timeout / DNS / connection refused | `MCPError(code="service_unreachable", message="CLASSify is unreachable. Try again later.", retryable=True)` (FR-022) |
| 429 | `MCPError(code="rate_limited", message="CLASSify is rate-limiting requests. Try again in a moment.", retryable=True)` |
| 5xx | Same as 429, surfaced as retryable. |
| 4xx other | `MCPError(code="bad_request", message="<upstream detail>")` |
| Concurrency cap exceeded | Returned by orchestrator before dispatch; agent never sees it. |
