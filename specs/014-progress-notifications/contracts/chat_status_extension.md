# Contract: `chat_status` extension for the rotating cosmic-word indicator

Extension only — the existing `chat_status` event ([`useWebSocket.ts:373-378`](../../../frontend/src/hooks/useWebSocket.ts#L373-L378)) keeps its current shape. We are NOT changing the existing `status` enum or emission cadence.

## Existing shape (unchanged)

```json
{
  "type": "chat_status",
  "status": "thinking" | "executing" | "fixing" | "done" | "idle",
  "message": "Processing..."
}
```

## What changes

**Nothing in the wire shape.** The frontend `<CosmicProgressIndicator>` component derives the rotating word entirely client-side — randomly chosen from the 55-word list in [`frontend/src/components/chat/chatStepWords.ts`](../../../frontend/src/components/chat/chatStepWords.ts) — based on `chatStatus.status`:

| `chatStatus.status` | Indicator behaviour |
|---|---|
| `idle` | Hidden. |
| `thinking`, `executing`, `fixing` | Visible, rotating cosmic word every 1.2 sec. |
| `done` | Hidden. Indicator unmounts within one render cycle. |

## Why client-side word selection

R7 documents the rationale: deterministic 1.2 sec cadence regardless of network jitter, no extra WebSocket traffic, and a single source of truth (the `chatStepWords` constant) that the backend never has to know about.

## Constraints (FR-001 through FR-006, SC-001/SC-002)

- The indicator MUST appear within 500 ms of submit. Today, `setChatStatus({status: "thinking"})` is called on submit at [`useWebSocket.ts:1011`](../../../frontend/src/hooks/useWebSocket.ts#L1011) — the indicator simply mounts on that transition, which is synchronous from the user's POV.
- The displayed word MUST change at least once per second on average (SC-002). The 1.2 sec interval satisfies this.
- A word MUST NOT stall more than 3 seconds (SC-002). The interval guarantees this.
- Words MUST come from the approved 55-word list (FR-002, SC-002). The `chatStepWords.ts` constant is the canonical list and is the only source the indicator reads.
- The indicator MUST NOT name tools or system internals (FR-004). The component does not consume `chatStatus.message` or any tool-name field — only the `status` enum.
- At most one indicator per turn (FR-006). The component is rendered exactly once inside the existing loading-state slot in `ChatInterface.tsx`.

## Compatibility

Backwards compatible: existing consumers of `chat_status` (the loading slot text, etc.) are untouched. The rotating word is rendered by a sibling component that subscribes to the same state.
