# Contract: `chat_step` WebSocket event (server → client)

New WebSocket message type emitted by the orchestrator on every step lifecycle transition. Travels on the same authenticated chat WebSocket as `chat_status`, `ui_render`, and `audit_append`. Client handler lives in [`frontend/src/hooks/useWebSocket.ts`](../../../frontend/src/hooks/useWebSocket.ts).

## Direction

Server → Client only. Clients do not send `chat_step` messages.

## Wire shape

```json
{
  "type": "chat_step",
  "chat_id": "<uuid>",
  "step": {
    "id": "<uuid>",
    "chat_id": "<uuid>",
    "turn_message_id": 12345,
    "kind": "tool_call",
    "name": "search_grants",
    "status": "in_progress",
    "args_truncated": "{\"query\": \"NSF biomedical 2026\"}",
    "args_was_truncated": false,
    "result_summary": null,
    "result_was_truncated": false,
    "error_message": null,
    "started_at": 1746489600000,
    "ended_at": null
  }
}
```

## Field semantics

- `type`: literal `"chat_step"`.
- `chat_id`: redundant with `step.chat_id`, present at top level so clients can filter without parsing the payload.
- `step`: the full `ChatStep` row as defined in [`data-model.md`](../data-model.md). The same shape is returned by the REST endpoint (see `chat_steps_rest.md`), so client rendering code is one path.

## Lifecycle — events emitted per step

A single step generates **exactly two** events under normal conditions:

1. **Start event** — `status: "in_progress"`, `ended_at: null`, `result_summary: null`, `error_message: null`. Emitted from `ChatStepRecorder.start()` immediately before the underlying step's work begins.
2. **Terminal event** — `status` ∈ {`completed`, `errored`, `cancelled`}, `ended_at` populated. Emitted from `ChatStepRecorder.complete()` / `.error()` / `.cancel()` after the step terminates.

`interrupted` is **never** emitted live — it is a read-time healing of orphaned `in_progress` rows.

## Idempotency & ordering guarantees

- Each event carries the full row state (not deltas) — clients overwrite the entry keyed by `step.id`. Out-of-order delivery (terminal arriving before start, e.g., across reconnect) is safe; the client always renders the highest-`started_at`/`ended_at` view it has.
- Emission order within a turn matches the order steps began (FR-013) — the recorder serializes its emit calls.

## PHI guarantees (FR-009b)

The orchestrator MUST redact PHI before emitting this event. Specifically:

- `args_truncated`, `result_summary`, and `error_message` are run through `backend/shared/phi_redactor.py` before serialization.
- `name` is treated as a non-PHI label (tool/agent/phase identifier) and is not redacted.
- A redacted-and-truncated string MUST always be `≤ 512` UTF-8 characters.
- If the redactor cannot complete (e.g., raises), the recorder MUST emit the terminal event with the field replaced by the literal `"[redaction failed]"` and structured-log the error — but MUST NOT block step lifecycle progression and MUST NOT leak raw PHI.

## Cancellation contract (FR-020/021)

When the user cancels a turn:

1. The orchestrator emits one terminal `chat_step` event with `status: "cancelled"` for **every** step that was `in_progress` at cancel time.
2. The orchestrator does NOT emit further `chat_step` events for that step even if the underlying request later returns; results are dropped per R6.

## Frontend handling

`useWebSocket.ts` adds a new switch arm:

```ts
case "chat_step": {
  const step = data.step as ChatStep;
  setChatSteps(prev => ({
    ...prev,
    [step.chat_id]: {
      ...(prev[step.chat_id] ?? {}),
      [step.id]: step,
    },
  }));
  break;
}
```

`ChatInterface.tsx` reads `chatSteps[activeChatId]`, sorts by `started_at`, and interleaves entries between the user message and the assistant reply for each turn.
