# WebSocket Protocol Additions

**Feature**: `004-component-feedback-loop`
**Substrate**: existing AstralBody WebSocket protocol — see [backend/shared/protocol.py](../../../backend/shared/protocol.py).

This document specifies the additions only. All other messages, fields, and conventions are unchanged.

---

## 1. `UIRender` envelope: per-component metadata extension

**Direction**: server → client
**Existing message** (`backend/shared/protocol.py:97-100`):

```python
@dataclass
class UIRender(Message):
    type: str = "ui_render"
    components: List[Dict[str, Any]] = field(default_factory=list)
    target: str = "canvas"
```

**Change**: each entry in `components` MAY now carry an additional metadata field, attached by the orchestrator alongside the existing `_source_agent`, `_source_tool`, `_source_params`:

| Field name              | Type     | Required | Notes |
|-------------------------|----------|----------|-------|
| `_source_correlation_id` | string   | optional | The audit-log `correlation_id` of the originating tool dispatch. **Omitted** when the component does not originate from a tool dispatch (e.g., static layout, system message). When present, the frontend uses it to scope feedback to the dispatch that produced this component. |

No version bump or new `type` is required. Existing clients that ignore unknown metadata fields continue to work.

---

## 2. `ui_event`: new actions

**Direction**: client → server
**Existing message** (`backend/shared/protocol.py:90-95`):

```python
@dataclass
class UIEvent(Message):
    type: str = "ui_event"
    action: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
```

### 2.1 `action: "component_feedback"` — submit feedback

```jsonc
{
  "type": "ui_event",
  "action": "component_feedback",
  "payload": {
    "correlation_id": "string | null",   // null only for non-tool-dispatch components
    "component_id":   "string | null",   // optional; identifies the specific component within a render
    "source_agent":   "string | null",
    "source_tool":    "string | null",
    "sentiment":      "positive | negative",
    "category":       "wrong-data | irrelevant | layout-broken | too-slow | other | unspecified",
    "comment":        "string | null"    // length-capped at 2048 chars at server ingress
  }
}
```

**Server behavior**:
1. Authenticate (existing JWT pattern).
2. Length-cap `comment` at 2048 chars; reject longer with `INVALID_INPUT`.
3. Run inline safety screen (`backend/feedback/safety.py`). If quarantined, persist with `comment_safety='quarantined'` and create a `quarantine_entry` (detector=`inline`).
4. Apply 10-second per-`(user, correlation_id, component_id)` dedup window (FR-009a). Within window → update existing row in place, no new audit event. Outside window → mark prior `active` row `superseded`, insert new `active` row, emit `feedback.submit` audit event.
5. Acknowledge via a server→client `ui_event` with `action="component_feedback_ack"` (see 2.4 below). Acknowledgement target ≤ 1 s p95 (SC-001).

### 2.2 `action: "feedback_retract"` — retract own feedback

```jsonc
{
  "type": "ui_event",
  "action": "feedback_retract",
  "payload": { "feedback_id": "uuid" }
}
```

**Server behavior**:
1. Authenticate; reject if `feedback_id` belongs to another user (404 indistinguishable from "not found", per FR-009).
2. Reject with `EDIT_WINDOW_EXPIRED` if `now() - created_at > 24 h` (FR-028).
3. Set `lifecycle='retracted'`; emit `feedback.retract` audit event.
4. Acknowledge with `feedback_retract_ack`.

### 2.3 `action: "feedback_amend"` — amend own feedback

```jsonc
{
  "type": "ui_event",
  "action": "feedback_amend",
  "payload": {
    "feedback_id": "uuid",
    "sentiment":   "positive | negative",
    "category":    "wrong-data | irrelevant | layout-broken | too-slow | other | unspecified",
    "comment":     "string | null"
  }
}
```

**Server behavior**:
1. Authenticate; reject cross-user as in 2.2.
2. Reject if `now() - created_at > 24 h` (FR-029).
3. Mark target `superseded`; insert new `active` row whose `superseded_by` chain points back; rerun inline safety screen on the new comment; emit `feedback.amend` audit event.
4. Acknowledge with `feedback_amend_ack`.

### 2.4 `action: "*_ack"` — server-originated acknowledgement events

**Direction**: server → client (sent as a regular outbound `ui_event` message; existing `ui_event` is documented as client-originated, but the server reuses the same wire shape for symmetry).

| Action                       | Payload                                                                  |
|------------------------------|---------------------------------------------------------------------------|
| `component_feedback_ack`     | `{ feedback_id, status: "recorded" \| "quarantined", deduped: bool }`     |
| `feedback_retract_ack`       | `{ feedback_id, status: "retracted" }`                                    |
| `feedback_amend_ack`         | `{ feedback_id: <new_id>, prior_id: <prior_id>, status: "amended" }`     |
| `component_feedback_error`   | `{ code: "EDIT_WINDOW_EXPIRED" \| "INVALID_INPUT" \| "NOT_FOUND", message: string }` |

The frontend `useFeedback` hook listens for these and surfaces toasts; `feedback:ack` window events are broadcast for any other listeners (mirrors the `audit:append` pattern from feature 003).

---

## 3. Wire-level error responses

All four new actions reuse the existing protocol error envelope (server → client `error` message with `code` + `message`), plus the new error codes listed above. No new transport-level mechanism is introduced.

---

## 4. Backwards compatibility

| Change | Compatibility |
|--------|---------------|
| New optional metadata field on UIRender components | Existing clients ignore unknown fields → fully compatible. |
| New `ui_event` actions | Existing clients never send these → fully compatible. Server returns existing "unknown action" error if an old client somehow sends one. |
| New server-originated ack `ui_event` messages | Existing clients ignore unknown actions → fully compatible. |
