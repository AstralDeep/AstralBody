# WebSocket Contract — `tool_progress` Message

**Status**: Existing protocol message (feature 014). **Referenced** by this feature, not changed.

The two long-running agents (CLASSify and Forecaster) emit `tool_progress` messages from their `JobPoller` on every poll iteration and on terminal job state. The orchestrator already forwards these to the originating WebSocket client without modification.

---

## Message shape

Defined in [backend/shared/protocol.py:228-240](../../backend/shared/protocol.py#L228-L240):

```python
@dataclass
class ToolProgress(Message):
    type: str = "tool_progress"
    tool_name: str = ""
    agent_id: str = ""
    message: str = ""
    percentage: Optional[int] = None  # 0-100, or None if indeterminate
    metadata: Dict[str, Any] = field(default_factory=dict)
```

---

## Conventions used by this feature

For every long-running tool (`train_classifier`, `retest_model`, `train_forecaster`, `generate_forecast`):

### Per-poll progress emission

```json
{
  "type": "tool_progress",
  "tool_name": "train_classifier",
  "agent_id": "classify-1",
  "message": "Training in progress (epoch 3 of 10)",
  "percentage": 30,
  "metadata": {
    "job_id": "<upstream task id>",
    "phase": "training",
    "correlation_id": "<orchestrator correlation id>"
  }
}
```

### Terminal success

```json
{
  "type": "tool_progress",
  "tool_name": "train_classifier",
  "agent_id": "classify-1",
  "message": "Training complete.",
  "percentage": 100,
  "metadata": {
    "job_id": "...",
    "phase": "completed",
    "correlation_id": "...",
    "result": {
      "metrics": { "accuracy": 0.92, "f1": 0.91, "...": "..." },
      "shap_url": "https://...",
      "summary": "Random Forest trained on 4,832 samples..."
    }
  }
}
```

### Terminal failure

```json
{
  "type": "tool_progress",
  "tool_name": "train_classifier",
  "agent_id": "classify-1",
  "message": "Training failed: <reason>",
  "percentage": null,
  "metadata": {
    "job_id": "...",
    "phase": "failed",
    "correlation_id": "..."
  }
}
```

### Polling-failure cutoff (FR-017)

Emitted exactly once after 5 consecutive transport failures (~25 s of upstream unavailability):

```json
{
  "type": "tool_progress",
  "tool_name": "train_classifier",
  "agent_id": "classify-1",
  "message": "Couldn't reach the service to confirm job status — try again later.",
  "percentage": null,
  "metadata": {
    "job_id": "...",
    "phase": "status_unknown",
    "correlation_id": "..."
  }
}
```

---

## Phase enum (informational)

`metadata.phase` ∈ `{"started", "training" | "forecasting" | "evaluating", "completed", "failed", "status_unknown"}`.

The frontend renders the progress bar's color and finality based on `phase`. Existing renderer behavior is unchanged.

---

## Feature flag

Forwarding is gated on the existing `progress_streaming` flag (on by default since feature 014 shipped). When OFF, the orchestrator drops `tool_progress` messages, the frontend never sees progress, and users only see the synchronous acknowledgment from `train_classifier` etc. This is acceptable degraded behavior — the flag is not user-visible — but should be ON in production.
