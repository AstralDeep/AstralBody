# MCP Tool Contracts — Timeseries Forecaster Agent

**Agent ID**: `forecaster-1`
**Underlying service**: `forecaster.ai.uky.edu` (URL user-supplied)
**Auth**: `Authorization: Bearer <FORECASTER_API_KEY>`
**Long-running tools**: `start_training_job`

All tools below require `_credentials` carrying `FORECASTER_URL` and `FORECASTER_API_KEY`.

The tool set mirrors the documented Forecaster API workflow exactly
(see `forecaster-api-docs.md` at the repo root): a CSV is uploaded
once to get a dataset `uuid`, columns are mapped to roles, a training
job is started, status is polled, results are fetched, and the
dataset is cleaned up.

---

## `submit_dataset`

Upload a CSV time-series dataset to Forecaster. Returns the upstream `uuid`
and the list of column names. Synchronous.

Backed by `POST /dataset/submit` with a multipart `file` part.

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "file_handle": {"type": "string", "description": "Handle to a CSV uploaded via AstralBody's file mechanism."}
  },
  "required": ["file_handle"]
}
```

**Returns** (`_data`):

```json
{
  "uuid": "...",
  "columns": ["col-a", "col-b", "..."],
  "filename": "rides.csv",
  "allowed_roles": ["not-included", "time-component", "grouping", "target", "past-covariates", "future-covariates", "static-covariates"]
}
```

---

## `set_column_roles`

Assign each dataset column to one of seven roles. Synchronous.

Backed by `POST /dataset/save-columns` with form data `{categorizedString, uuid}`,
where `categorizedString` is a JSON-encoded role→[columns] dict. The tool
accepts the friendlier inverse (`{column_name: role}`) and converts internally.

**Allowed roles**: `not-included`, `time-component`, `grouping`, `target`,
`past-covariates`, `future-covariates`, `static-covariates`. Columns omitted
from `column_roles` fall into `not-included` by upstream default.

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "uuid": {"type": "string"},
    "column_roles": {
      "type": "object",
      "description": "Map of column_name → role. Example: {'Date': 'time-component', 'Volume': 'target', 'Rain': 'past-covariates'}.",
      "additionalProperties": {"type": "string", "enum": ["not-included", "time-component", "grouping", "target", "past-covariates", "future-covariates", "static-covariates"]}
    }
  },
  "required": ["uuid", "column_roles"]
}
```

---

## `start_training_job`

**Long-running**. Kicks off training; the agent's `JobPoller` pushes
`ToolProgress` updates and a terminal message with metrics on completion.

Backed by `POST /dataset/start-training-job` with form data `{uuid, options}`,
where `options` is a JSON-encoded **sparse** override dict (any key not
included uses the upstream default).

**Documented options** (defaults shown):

| Option | Default | Notes |
|---|---|---|
| `test-size` | `0.2` | Fraction held out for testing. |
| `expanding-window` | `False` | Set True for expanding-window backtests. |
| `expanding-window-forecast-horizon` | `6` | |
| `expanding-window-stride` | `6` | |
| `visualize` | `True` | |
| `generate-real-predictions` | `False` | Set True to forecast beyond the test set. |
| `real-prediction-length` | `12` | Used when `generate-real-predictions=True`. |
| `fill-future-covariates` | `False` | |
| `probabilistic` | `False` | |
| `probabilistic-likelihood` | `"quantile"` | |
| `probabilistic-num-samples` | `100` | |
| `models` | `["arima", "exponential-smoothing", "linear-regression", "xgboost", "random-forest", "lgbm", "nlinear", "tft"]` | |
| `arima-p` | `12` | |
| `arima-d` | `1` | |
| `arima-q` | `6` | |
| `lags` | `12` | |
| `lags-future` | `0` | |
| `output-chunk-length` | `6` | |
| `epochs` | `10` | |

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "uuid": {"type": "string"},
    "options": {"type": "object", "description": "Sparse override dict; only include keys you want to differ from upstream defaults.", "additionalProperties": true}
  },
  "required": ["uuid"]
}
```

**Synchronous return**:

```json
{ "uuid": "...", "status": "started", "options": {}, "message": "Training started. Progress will appear here automatically." }
```

---

## `get_job_status`

Synchronous wrapper around `GET /dataset/get-job-status?uuid=...`. Use only
for explicit user "did my job finish?" queries — `JobPoller` already pushes
status updates automatically while a long-running job runs.

**Returns** the same shape as the poller's poll-result:

```json
{ "status": "succeeded" | "in_progress" | "failed", "percentage": null, "message": "...", "result": ... }
```

Status mapping:

| Upstream `status` | Normalized | Notes |
|---|---|---|
| `"Completed"` | `succeeded` | `result` is filled with `/results/get-metrics` payload. |
| contains `"Training"` | `in_progress` | |
| any other non-empty | `in_progress` | Defensive — covers `"Initializing"`, `"Queued"`, etc. |
| empty / missing | `failed` | |

---

## `get_results`

Synchronous. Fetch the final `output_log` + per-model metrics for a completed job.

Backed by `GET /results/get-metrics?uuid=...`, which returns
`{output_log, file_contents}` where `file_contents` is the metrics JSON.

**Input schema**: `{ "type": "object", "properties": { "uuid": {"type": "string"} }, "required": ["uuid"] }`

**Returns** (`_data`): `{ "uuid": "...", "output_log": "...", "metrics": {...} }`

---

## `delete_dataset`

Synchronous. Removes the dataset and its trained models from the Forecaster service.

Backed by `POST /dataset/delete` with form data `{uuid}`.

**Input schema**: `{ "type": "object", "properties": { "uuid": {"type": "string"} }, "required": ["uuid"] }`

---

## `_credentials_check` (internal)

Calls `GET /dataset/get-job-status?uuid=probe-credentials-check`. Any
response *other than* 401/403 is treated as `ok` (the route is reachable
and auth was accepted; the sentinel UUID just doesn't exist). Returns the
same verdict shape as the CLASSify version.

---

## Error mapping

Identical mapping table as [classify-tools.md §Error mapping](classify-tools.md#error-mapping-all-tools), with "CLASSify" replaced by "Forecaster" in user-facing messages.

| Exception class | User-facing message |
|---|---|
| `AuthFailedError` | "The saved Forecaster API key was rejected. Update it in the agent's settings." |
| `ServiceUnreachableError` | "Forecaster is unreachable. Try again later." |
| `RateLimitedError` | "Forecaster is rate-limiting requests or temporarily unavailable. Try again in a moment." |
| `EgressBlockedError` | "Forecaster URL is not allowed: …" |
| `BadRequestError` | "Forecaster rejected the request: …" |
