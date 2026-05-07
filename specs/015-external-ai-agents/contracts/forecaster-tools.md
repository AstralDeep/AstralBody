# MCP Tool Contracts — Timeseries Forecaster Agent

**Agent ID**: `forecaster-1`
**Underlying service**: `forecaster.ai.uky.edu` (URL user-supplied)
**Auth**: `Authorization: Bearer <FORECASTER_API_KEY>`
**Long-running tools**: `train_forecaster`, `generate_forecast`

All tools below require `_credentials` carrying `FORECASTER_URL` and `FORECASTER_API_KEY`.

---

## `train_forecaster`

Train one or more forecasting models on a tabular time series.

**Long-running**. Returns acknowledgment with `task_id`; poller pushes `ToolProgress`.

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "file_handle": {"type": "string", "description": "Handle to a CSV uploaded via AstralBody's file mechanism."},
    "dataset_name": {"type": "string"},
    "parameters": {
      "type": "object",
      "description": "Forecasting parameters: time column, value column, frequency, horizon, model selections, etc.",
      "additionalProperties": true
    }
  },
  "required": ["file_handle", "dataset_name", "parameters"]
}
```

**Synchronous return**:

```json
{ "task_id": "...", "status": "started", "message": "Training started. Progress will be posted here." }
```

---

## `generate_forecast`

Run an N-step forecast against an already-trained model.

**Long-running**. Same lifecycle as `train_forecaster`.

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "dataset_name": {"type": "string"},
    "parameters": {
      "type": "object",
      "description": "Forecast parameters: horizon, model selection, optional confidence levels.",
      "additionalProperties": true
    }
  },
  "required": ["dataset_name", "parameters"]
}
```

---

## `get_results_summary`

Synchronous. Fetch the LLM-generated summary of a completed forecast run.

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "dataset_name": {"type": "string"}
  },
  "required": ["dataset_name"]
}
```

**Returns**: `{ "summary": "...", "metrics": {...}, "models_compared": ["...", "..."] }`

---

## `get_recommendations`

Synchronous. Returns model recommendations based on an already-completed run's results.

**Input schema**: `{ "type": "object", "properties": { "dataset_name": {"type": "string"} }, "required": ["dataset_name"] }`

**Returns**: `{ "recommendations": [ { "model": "...", "rationale": "..." }, ... ] }`

---

## `_credentials_check` (internal)

Calls a low-cost authenticated GET against the service (final endpoint to be confirmed during implementation; candidate is `GET /download-model?probe=true` because authentication is exercised regardless of whether a probe model exists). Returns the same verdict shape as the CLASSify version.

---

## Error mapping

Identical mapping table as [classify-tools.md §Error mapping](classify-tools.md#error-mapping-all-tools), with "CLASSify" replaced by "Forecaster" in user-facing messages.
