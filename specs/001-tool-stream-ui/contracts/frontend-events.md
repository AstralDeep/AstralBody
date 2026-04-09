# Contract: Frontend Event Handling and Component Merge

**Feature**: 001-tool-stream-ui
**Layer**: The TypeScript surface inside [frontend/src/hooks/useWebSocket.ts](../../../frontend/src/hooks/useWebSocket.ts) and [frontend/src/components/DynamicRenderer.tsx](../../../frontend/src/components/DynamicRenderer.tsx).
**Revised**: 2026-04-09 — `mergeStreamChunk` and `StreamErrorPayload` extended to render the new `phase: "reconnecting"` state introduced by FR-021a. No additional handling needed for FR-009a fan-out: the frontend simply receives chunks like before; deduplication happens server-side.

This contract specifies the frontend behavior the rest of the React app may rely on, and the invariants the streaming feature MUST preserve when adding new code.

---

## 1. New WebSocket message handler: `ui_stream_data`

`useWebSocket.ts` adds a case to `handleMessage`:

```ts
case "ui_stream_data": {
  const msg = data as UIStreamDataMessage;
  // 1. Defense in depth: drop if not for current chat.
  if (msg.session_id !== activeChatIdRef.current) return;

  // 2. Drop if seq is out of order.
  const lastSeq = streamSeqRef.current.get(msg.stream_id) ?? -1;
  if (msg.seq <= lastSeq) return;
  streamSeqRef.current.set(msg.stream_id, msg.seq);

  // 3. Merge or append.
  setUiComponents((prev) => mergeStreamChunk(prev, msg));

  // 4. If terminal, drop the stream from the active set.
  if (msg.terminal) {
    activeSubscriptionsRef.current.delete(msg.stream_id);
    streamSeqRef.current.delete(msg.stream_id);
  }
  return;
}
```

### `mergeStreamChunk(prev, msg)` semantics

```ts
function mergeStreamChunk(
  prev: ComponentTree,
  msg: UIStreamDataMessage
): ComponentTree {
  // Walk prev recursively. Find the node whose id === msg.stream_id (the
  // anchor for this stream's component).
  //
  // CASE 1 — normal data chunk (msg.error == null):
  //   Replace the anchor with msg.components[0]. If no anchor exists, this
  //   is the first chunk: append msg.components to the canvas.
  //
  // CASE 2 — reconnecting chunk (msg.error?.phase === "reconnecting"):
  //   Replace the anchor with a *decorated* copy of itself: same id, same
  //   visual content, but with an overlay showing "Reconnecting (attempt N/3)".
  //   Use `decorateReconnecting(node, msg.error)`. If no anchor exists yet
  //   (subscribe immediately followed by a transient error before any data),
  //   create a placeholder component with the stream_id and the reconnecting
  //   overlay.
  //
  // CASE 3 — failed chunk (msg.error?.phase === "failed"):
  //   Replace the anchor with a *failure* variant whose id is preserved and
  //   which renders the error message + a retry button if msg.error.retryable
  //   (or a "sign in again" button if msg.error.code === "unauthenticated" |
  //   "unauthorized"). Use `decorateFailed(node, msg.error)`.
  //
  // In all cases the anchor's `id` MUST be preserved so the next chunk
  // (recovery, next reconnect attempt, or terminal) merges into the same
  // node and the same React fiber.
}
```

**Invariants the merge MUST satisfy** (verified by `frontend/src/__tests__/stream_merge.test.tsx`):

1. **Identity preservation**: components with `id !== msg.stream_id` are returned as `===` references (same object identity), so `React.memo` siblings do not re-render.
2. **Structural preservation**: container nesting is unchanged.
3. **No duplication**: a chunk for a stream that already has a rendered component does not append a second one.
4. **First-chunk append rule**: if no component with `id === msg.stream_id` is found anywhere in the tree, the chunk's components are appended to the top-level canvas array.
5. **Reconnecting overlay** *(new for FR-021a)*: a chunk with `error.phase === "reconnecting"` MUST NOT remove the existing component; it MUST decorate it with a visible "reconnecting" indicator. The user keeps seeing the last good data underneath, so the experience is "this is a little stale right now and we're working on it" rather than "your component vanished."
6. **Recovery overwrites the overlay** *(new for FR-021a)*: when a normal data chunk arrives after a reconnecting chunk for the same `stream_id`, the merge replaces the entire decorated node with the fresh data — the overlay disappears in the same render. The transition is one React commit, no flicker.
7. **Failure variant preserves id**: if `error.phase === "failed"` is set and `msg.components` is empty, the existing component (if any) is replaced with a failure variant whose `id` is preserved (so a subsequent manual-retry success merges into it correctly).

---

## 2. Modified `ui_render` handler

Today, on `ui_render` for canvas, the frontend auto-saves every component via `save_component` and auto-subscribes streamable ones via `stream_subscribe`. **Both behaviors are preserved**, with two corrections:

### 2.a Don't auto-save streaming components

```ts
// in the existing ui_render handler, around the auto-save block:
for (const c of msg.components) {
  if (isStreamingComponent(c)) continue;  // NEW: skip auto-save for streaming
  send({ type: "ui_event", action: "save_component", ... });
}
```

`isStreamingComponent(c)` returns true if `c.id?.startsWith("stream-")` OR `streamableToolsRef.current.has(c._source_tool)`. Rationale: per the integration risk in the codebase exploration, auto-saving streaming components causes history bloat and confusion. Per A-007 / FR-009, we persist the *subscription metadata* server-side, not the chunks.

### 2.b Auto-subscribe is scoped to active chat

```ts
// in the existing auto-subscribe block:
if (msg.session_id === activeChatIdRef.current) {
  // existing logic
}
```

This is a defense-in-depth check; the server already gates by chat, but the frontend MUST NOT issue a subscribe for a chat the user isn't currently viewing.

---

## 3. Chat-switch behavior

When the user switches chats (the existing `setActiveChatId(...)` flow), `useWebSocket.ts` MUST:

1. For every entry in `activeSubscriptionsRef.current` whose stored `chat_id` is the **old** chat: do nothing on the wire — the **server** already migrates them to dormant on the same `load_chat` action that the frontend is about to send. The frontend simply removes them from `activeSubscriptionsRef`.
2. Send the `load_chat` action with the new `chat_id` (existing behavior).
3. On receipt of the `chat_loaded` response, the server will (a) re-issue any dormant streams as fresh `stream_subscribed` + `ui_stream_data` messages; (b) the frontend's existing handlers for those messages naturally restore the UI.

**Invariant**: after a chat switch completes, the only entries in `activeSubscriptionsRef.current` are streams belonging to the **newly active** chat.

---

## 4. Reconnect behavior

The existing reconnect path in `useWebSocket.ts` (lines ~691-704) re-sends `register_ui` and re-subscribes to all entries in `activeSubscriptionsRef.current`. This continues to work for streams belonging to the active chat. For dormant streams (different chat), the frontend does **not** re-subscribe — they will be resumed by the server the next time the user navigates back to that chat (per §3 above).

**Invariant**: a reconnect with the same JWT and same active chat results in the same set of `ui_stream_data` chunks resuming, with at most a 3-second visible gap (SC-003).

---

## 5. `DynamicRenderer.tsx` changes

### 5.a Stable React keys

```tsx
// Today: keys are array indices
{components.map((c, i) => <PrimitiveSwitch key={i} component={c} />)}

// New: keys are component.id when present, fallback to a stable hash
{components.map((c, i) => (
  <PrimitiveSwitch key={c.id ?? `idx-${i}`} component={c} />
))}
```

### 5.b `React.memo` on streaming-eligible primitives

The primitive components that are likely to be streamed (`Metric`, `LineChart`, `BarChart`, `Table`, `Card`, `List`, `Progress`, `Text`, `Alert`) are wrapped:

```tsx
export const Metric = React.memo(MetricImpl, (prev, next) => {
  return prev.component.id === next.component.id
    && shallowEqualIgnoring(prev.component, next.component, ["_meta"])
    && prev.onAction === next.onAction;
});
```

The custom comparator means: if a sibling streams an update, this component does **not** re-render unless its own data changed. This is the mechanism that lets us hit SC-005 (100 users × 3 streams without unbounded growth).

**Constraint**: the `onAction` callback passed to primitives MUST be referentially stable across renders (use `useCallback` in the parent). Today's code already does this for most primitives; verify in tests.

### 5.c No new primitive components

Per constitution VIII, no new primitive types. Streaming reuses existing ones. The `id` field that was already in every Zod schema in [frontend/src/catalog.ts](../../../frontend/src/catalog.ts) is finally exercised.

---

## 6. New TypeScript types

*Revised 2026-04-09 — `StreamErrorPayload` gains `phase`, `attempt`, `next_retry_at_ms` (FR-021a). `StreamSubscribedMessage` gains `attached` (FR-009a).*

Added to [frontend/src/types/](../../../frontend/src/types/) (existing folder):

```ts
// streaming.ts
export interface UIStreamDataMessage {
  type: "ui_stream_data";
  stream_id: string;
  session_id: string;
  seq: number;
  components: ComponentNode[];
  raw?: unknown;
  terminal?: boolean;
  error?: StreamErrorPayload | null;
}

export interface StreamErrorPayload {
  code:
    | "tool_error"
    | "unauthenticated"
    | "unauthorized"
    | "rate_limited"
    | "upstream_unavailable"
    | "chunk_too_large"
    | "cancelled";
  message: string;
  /** "reconnecting" = system is in the FR-021a auto-retry loop; "failed" = terminal. */
  phase: "reconnecting" | "failed";
  /** Present when phase === "reconnecting". Current retry attempt (1, 2, or 3). */
  attempt?: number;
  /** Present when phase === "reconnecting". Wall-clock epoch ms of next attempt. */
  next_retry_at_ms?: number;
  /** True only when phase === "failed" AND the cause is recoverable by user action. */
  retryable: boolean;
}

export interface StreamSubscribedMessage {
  type: "stream_subscribed";
  stream_id: string;
  tool_name: string;
  agent_id: string;
  session_id: string;
  max_fps: number;
  min_fps: number;
  /** True when this client attached to an existing deduplicated subscription
   *  (FR-009a) instead of creating a fresh one. The next chunk may be a
   *  reconnecting chunk if the existing subscription is mid-RECONNECTING. */
  attached: boolean;
}

export interface StreamErrorMessage {
  type: "stream_error";
  request_action: "stream_subscribe" | "stream_unsubscribe";
  session_id: string;
  payload: { tool_name?: string; code: string; message: string };
}
```

The existing `WSMessage` discriminated union in [frontend/src/types/](../../../frontend/src/types/) is extended with these.

---

## 7. JSDoc obligations (constitution VI)

Every new exported type and function above MUST carry JSDoc comments explaining purpose, params, and return value. Specifically:

- `mergeStreamChunk` — describe the merge rule and the identity preservation invariant.
- `isStreamingComponent` — describe the detection rule.
- `UIStreamDataMessage` and friends — describe the wire shape and reference [contracts/protocol-messages.md](protocol-messages.md).

---

## 8. Tests this contract must pass

Listed in the plan's Project Structure under `frontend/src/__tests__/`:

| Test | What it verifies |
|---|---|
| `stream_merge.test.tsx` | `mergeStreamChunk` preserves identity for siblings, replaces by id, appends on first-chunk. Also covers the reconnecting → recovery transition (case 2 → case 1) and the reconnecting → failed transition (case 2 → case 3) preserving `id` across all three. |
| `stream_lifecycle.test.tsx` | Chat switch removes from `activeSubscriptionsRef`; return restores via server-driven `ui_stream_data`. |
| `stream_render.test.tsx` | A streaming chunk does not cause sibling primitives to re-render (asserted by render-count spy on `React.memo`'d sibling). |
| `stream_reconnecting.test.tsx` *(NEW for FR-021a)* | A `phase: "reconnecting"` chunk decorates the existing component without removing it; a subsequent normal data chunk replaces the decoration in a single render; a `phase: "failed"` chunk after 3 reconnects shows the manual retry button. |
| `stream_attach.test.tsx` *(NEW for FR-009a)* | When `stream_subscribed` arrives with `attached: true` followed by a reconnecting chunk, the frontend renders the reconnecting state correctly (i.e., it doesn't assume it must be the first chunk). |

These together cover the frontend half of FR-002, FR-003, FR-004, FR-007, FR-008, FR-009a, FR-011, FR-016, FR-019, FR-021a.
