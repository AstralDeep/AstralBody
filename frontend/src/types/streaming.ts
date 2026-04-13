/**
 * Streaming message types for the 001-tool-stream-ui feature.
 *
 * These match the wire shapes documented in
 * specs/001-tool-stream-ui/contracts/protocol-messages.md (browser-facing
 * messages) and contracts/frontend-events.md.
 *
 * The frontend's existing `WSMessage` discriminated union (in useWebSocket.ts)
 * is intentionally loose (`{type: string, [key]: unknown}`), so these
 * interfaces are used inside the `handleMessage` switch via `as` casts
 * rather than enforced at the union level.
 */

/**
 * The error payload embedded inside a `ui_stream_data` message when a
 * stream is in the reconnecting backoff loop OR has terminally failed.
 *
 * Distinguish via the `phase` field:
 * - `"reconnecting"` — orchestrator is in the FR-021a auto-retry loop
 *   (1s/5s/15s exponential backoff, max 3 attempts). The frontend SHOULD
 *   render a "reconnecting" overlay on the existing component without
 *   removing it. `attempt` and `next_retry_at_ms` are populated.
 * - `"failed"` — terminal. The frontend SHOULD render an error variant
 *   with either a manual retry button (when `retryable: true`) or a
 *   "sign in again" prompt (for `unauthenticated`/`unauthorized` codes,
 *   which always have `retryable: false` per the security carve-out).
 */
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
    /** "reconnecting" = system is in the FR-021a auto-retry loop;
     *  "failed" = terminal, requires user action. */
    phase: "reconnecting" | "failed";
    /** Present when phase === "reconnecting". Current retry attempt (1, 2, or 3). */
    attempt?: number;
    /** Present when phase === "reconnecting". Wall-clock epoch ms of next attempt. */
    next_retry_at_ms?: number;
    /** True only when phase === "failed" AND the cause is recoverable by
     *  user action. Always false for auth codes (security carve-out). */
    retryable: boolean;
}

/**
 * One streaming chunk delivered from the orchestrator to the browser.
 *
 * Identifies its target via `stream_id` (matched against
 * `Component.id` in the `uiComponents` tree by `mergeStreamChunk`).
 *
 * Out-of-order chunks (lower `seq` than what the client has already seen)
 * MUST be dropped — the server may have re-issued via `RECONNECTING →
 * STARTING` and a stale chunk from the previous attempt could arrive late.
 *
 * See contracts/protocol-messages.md §A4.
 */
export interface UIStreamDataMessage {
    type: "ui_stream_data";
    stream_id: string;
    session_id: string;
    seq: number;
    components: Array<Record<string, unknown>>;
    raw?: unknown;
    terminal?: boolean;
    error?: StreamErrorPayload | null;
}

/**
 * Server-to-client confirmation that a `stream_subscribe` action succeeded.
 *
 * The `attached` field (FR-009a) is `true` when this client joined an
 * EXISTING deduplicated subscription (e.g. another tab of the same user
 * already had this stream running) instead of creating a fresh one. When
 * `attached: true`, the next chunk the client receives MAY be a
 * `phase: "reconnecting"` chunk if the existing subscription happens to be
 * mid-RECONNECTING.
 *
 * See contracts/protocol-messages.md §A3.
 */
export interface StreamSubscribedMessage {
    type: "stream_subscribed";
    stream_id: string;
    tool_name: string;
    agent_id: string;
    session_id: string;
    max_fps: number;
    min_fps: number;
    attached: boolean;
}

/**
 * Server-to-client rejection of a `stream_subscribe` or `stream_unsubscribe`
 * action — the stream was never created (or never existed). Used at
 * subscribe time for cap-exceeded, unauthorized, params-invalid, etc.
 *
 * Codes (per contracts/protocol-messages.md §A6):
 * - `limit_exceeded` — per-user concurrent stream cap reached
 * - `not_streamable` — tool exists but is not declared streamable
 * - `unauthorized` — user lacks scope or chat ownership
 * - `params_invalid` — params failed schema validation
 * - `params_too_large` — params exceeds 16 KB
 * - `agent_unavailable` — agent owning the tool is not connected
 */
export interface StreamErrorMessage {
    type: "stream_error";
    request_action: "stream_subscribe" | "stream_unsubscribe";
    session_id?: string;
    payload: {
        tool_name?: string;
        stream_id?: string;
        code: string;
        message: string;
    };
}

/**
 * Per-stream client-side metadata. Tracks the original subscribe parameters
 * so the frontend can re-issue on reconnect AND so a manual retry button
 * (after `phase: "failed"`) can resubscribe with the same args.
 */
export interface StreamSubscriptionRecord {
    stream_id: string;
    chat_id: string;
    tool_name: string;
    agent_id: string;
    params: Record<string, unknown>;
}
