/**
 * Streaming overlay decorators (001-tool-stream-ui FR-021a).
 *
 * `decorateReconnecting` and `decorateFailed` take an existing component dict
 * and return a NEW component dict that renders the appropriate overlay/error
 * state while PRESERVING the input's `id`. Preserving the id is critical so
 * that:
 *
 * - Subsequent merge operations (a successful chunk after retry, or another
 *   reconnect attempt) find the same anchor in `uiComponents` and overwrite
 *   it cleanly via `mergeStreamChunk`.
 * - The React fiber stays mounted across the reconnecting → recovery
 *   transition, avoiding a flicker.
 *
 * Phase 2 (foundational): these are STUBS that pass the input through. The
 * full overlay rendering is implemented in US5 T083, which adds:
 *
 * - For `decorateReconnecting`: an overlay badge showing "Reconnecting
 *   (attempt N/3)" and an optional countdown computed from
 *   `error.next_retry_at_ms`.
 * - For `decorateFailed`: an error variant with either a manual "Retry"
 *   button (when `error.retryable === true`) OR a "Sign in again" button
 *   (for `unauthenticated`/`unauthorized` codes).
 */
import type { StreamErrorPayload } from "../types/streaming";

type ComponentNode = Record<string, unknown>;

/**
 * Decorate a component to indicate the stream is in the auto-retry loop.
 *
 * Phase 2 stub: returns the input with a `_streamReconnecting` marker so
 * `DynamicRenderer` (in US5) can pick it up and render the overlay. The
 * input's `id` MUST be preserved.
 */
export function decorateReconnecting(
    node: ComponentNode,
    error: StreamErrorPayload,
): ComponentNode {
    return {
        ...node,
        _streamReconnecting: {
            attempt: error.attempt ?? 1,
            next_retry_at_ms: error.next_retry_at_ms,
            message: error.message,
            code: error.code,
        },
    };
}

/**
 * Decorate a component to indicate the stream has terminally failed.
 *
 * Phase 2 stub: returns the input with a `_streamFailed` marker so
 * `DynamicRenderer` (in US5) can pick it up and render the failure variant
 * with the correct retry / re-auth button. The input's `id` MUST be
 * preserved.
 */
export function decorateFailed(
    node: ComponentNode,
    error: StreamErrorPayload,
): ComponentNode {
    return {
        ...node,
        _streamFailed: {
            code: error.code,
            message: error.message,
            retryable: error.retryable,
        },
    };
}

/**
 * Helper used by `useWebSocket.ts` to decide whether to skip auto-saving a
 * component (per FR-009 / contracts/frontend-events.md §2.a — streaming
 * components are not saved to history because that would bloat the DB with
 * every chunk).
 */
export function isStreamingComponent(
    component: Record<string, unknown>,
    streamableTools: Record<string, unknown>,
): boolean {
    const id = component["id"];
    if (typeof id === "string" && id.startsWith("stream-")) return true;
    const sourceTool = component["_source_tool"];
    if (typeof sourceTool === "string" && sourceTool in streamableTools) return true;
    return false;
}
