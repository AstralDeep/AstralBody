# Contract: Audit Event for Text-Only Dispatch

**Feature**: 008-llm-text-only-chat
**Type**: Backend audit event (persisted via existing `Recorder`)
**Status**: New `feature` value on existing event type

---

## What this is

Every successful or failed text-only chat dispatch emits an audit event using the **existing** `_record_llm_call` helper at [backend/llm_config/audit_events.py:195](../../../backend/llm_config/audit_events.py#L195). No new event type is introduced.

The only difference from a tool-augmented dispatch is the `feature` tag string: `"chat_dispatch_text_only"` instead of `"tool_dispatch"` or `"chat_dispatch"`.

---

## Event shape (existing schema)

```jsonc
{
  "action_type": "llm.call",
  "feature": "chat_dispatch_text_only",   // <-- new value introduced by this feature
  "actor_user_id": "<user-id>",
  "auth_principal": "<keycloak-subject>",
  "outcome": "success" | "failure",
  "inputs_meta": {
    "model": "<resolved-model>",
    "messages_count": <int>,
    "tools_count": 0                     // always 0 in text-only path
  },
  "outputs_meta": {
    "completion_tokens": <int>,
    "prompt_tokens": <int>
  },
  "error_meta": null | { "type": "...", "message": "..." }
}
```

---

## Emission rules

| Condition | Emission |
|-----------|----------|
| Text-only dispatch begins | NO separate "begin" event (matches existing `_record_llm_call` semantics — events are emitted at completion). |
| LLM returns successfully | One event with `outcome: "success"`. |
| LLM raises an exception | One event with `outcome: "failure"` and populated `error_meta`. |
| LLM is unavailable (pre-flight at [orchestrator.py:1739-1761](../../../backend/orchestrator/orchestrator.py#L1739-L1761)) | Existing `_record_llm_unconfigured` fires; this feature does NOT change that path. |

---

## Why this contract is sufficient for FR-009

> **FR-009**: Text-only chats MUST emit the same observability signals... distinguishable from agent-backed turns so operators can measure how often the fallback fires.

- "Same observability signals" — the same `_record_llm_call` helper writes the same fields.
- "Distinguishable" — operators query `WHERE feature = 'chat_dispatch_text_only'` to count fallback usage and compare against `WHERE feature IN ('tool_dispatch', 'chat_dispatch')`.

---

## Acceptance signals

- A backend test in `backend/tests/test_chat_text_only.py` MUST mock the audit recorder and assert that exactly one event with `feature="chat_dispatch_text_only"` is recorded for a successful no-tools dispatch.
- The same test file MUST assert that a tool-augmented dispatch in the same test session records `feature` values OTHER than `chat_dispatch_text_only`, ensuring no leak.
