/**
 * mergeStreamChunk — merges an incoming `ui_stream_data` chunk into the
 * existing `uiComponents` tree by walking the tree and finding the node
 * whose `id` matches the chunk's `stream_id`.
 *
 * Three cases (per specs/001-tool-stream-ui/contracts/frontend-events.md §1):
 *
 * 1. **Normal data chunk** (`msg.error == null`): replace the anchor with
 *    `msg.components[0]`. If no anchor exists yet, append `msg.components`
 *    to the canvas (this is how the FIRST chunk renders).
 *
 * 2. **Reconnecting chunk** (`msg.error?.phase === "reconnecting"`): decorate
 *    the existing anchor with a "reconnecting" overlay via
 *    `decorateReconnecting`. The user keeps seeing the last good data
 *    underneath, so the experience is "this is a little stale right now and
 *    we're working on it" rather than "your component vanished".
 *
 * 3. **Failed chunk** (`msg.error?.phase === "failed"`): decorate the anchor
 *    with `decorateFailed`, which renders an error message and either a
 *    manual retry button (when `retryable: true`) or a "sign in again"
 *    prompt (for auth codes — `retryable: false`).
 *
 * Identity invariants (verified by stream_merge.test.tsx):
 * - Components with `id !== msg.stream_id` are returned as `===` references
 *   (same object identity), so `React.memo` siblings do not re-render.
 * - Container nesting is unchanged.
 * - The anchor's `id` is preserved across all merge operations so a
 *   subsequent chunk merges into the same DOM node.
 *
 * In Phase 2 (foundational) only case 1 is fully implemented; cases 2 and 3
 * fall through to case 1 (the decorate stubs are no-ops). US5 (T084) fills
 * them in.
 */
import { decorateReconnecting, decorateFailed } from "./streamDecorate";
import type { UIStreamDataMessage } from "../types/streaming";

type ComponentNode = Record<string, unknown>;
type ComponentTree = ComponentNode[];

/**
 * Walk a component tree and replace the first node whose `id` field equals
 * `targetId` with `replacement`. Returns a new tree where:
 * - The mutated branch is a fresh array/object chain (so React state updates
 *   work correctly).
 * - Untouched nodes are returned as `===` references for `React.memo`
 *   compatibility.
 *
 * Returns `null` if no node was found (caller falls back to first-chunk
 * append).
 */
function replaceById(
    tree: ComponentTree,
    targetId: string,
    replacement: ComponentNode,
): ComponentTree | null {
    let found = false;
    const next: ComponentTree = [];
    for (const node of tree) {
        if (found) {
            // Already replaced — keep remaining nodes by reference
            next.push(node);
            continue;
        }
        if (node && typeof node === "object" && node["id"] === targetId) {
            next.push(replacement);
            found = true;
            continue;
        }
        // Recurse into children-bearing containers
        const recursed = recurseChildren(node, targetId, replacement);
        if (recursed !== null) {
            next.push(recursed);
            found = true;
        } else {
            next.push(node);
        }
    }
    return found ? next : null;
}

/**
 * Internal helper for `replaceById`: tries to descend into a node's children
 * (or content) field. Returns a new node with the replacement applied OR
 * `null` if the target id was not found anywhere in this subtree.
 *
 * Kept conservative: only recurses into `children` and `content` fields,
 * which is the convention for AstralBody container primitives (Container,
 * Card, Grid, Collapsible, Tabs).
 */
function recurseChildren(
    node: unknown,
    targetId: string,
    replacement: ComponentNode,
): ComponentNode | null {
    if (!node || typeof node !== "object") return null;
    const obj = node as Record<string, unknown>;

    for (const key of ["children", "content"] as const) {
        const childList = obj[key];
        if (Array.isArray(childList)) {
            const replaced = replaceById(childList as ComponentTree, targetId, replacement);
            if (replaced !== null) {
                return { ...obj, [key]: replaced };
            }
        }
    }
    return null;
}

/**
 * The public merge entry point used by `useWebSocket.ts`.
 *
 * @param prev  The current `uiComponents` state.
 * @param msg   The incoming `ui_stream_data` message.
 * @returns     The new `uiComponents` state.
 */
export function mergeStreamChunk(
    prev: ComponentTree,
    msg: UIStreamDataMessage,
): ComponentTree {
    // Case 2 & 3: error chunk. Find the existing anchor and decorate it.
    if (msg.error != null) {
        const decorator =
            msg.error.phase === "reconnecting" ? decorateReconnecting : decorateFailed;
        // Find the anchor first (so we can decorate the *current* state)
        const placeholder: ComponentNode = {
            type: "metric", // generic placeholder; decorateFailed/Reconnecting will overwrite
            id: msg.stream_id,
        };
        // If components were sent alongside the error, prefer them as the
        // base. Otherwise use the placeholder.
        const base =
            msg.components && msg.components.length > 0
                ? (msg.components[0] as ComponentNode)
                : placeholder;
        // Ensure the base has the correct id
        const baseWithId: ComponentNode = { ...base, id: msg.stream_id };
        const decorated = decorator(baseWithId, msg.error);
        const replaced = replaceById(prev, msg.stream_id, decorated);
        if (replaced !== null) return replaced;
        // First-chunk-as-error (rare but possible if a stream fails before
        // any data arrives — e.g. attach to a mid-RECONNECTING stream).
        return [...prev, decorated];
    }

    // Case 1: normal data chunk. Replace anchor or append.
    if (msg.components && msg.components.length > 0) {
        // Ensure the top-level component has the right id (defense in depth —
        // the server already assigns it via assign_stream_id_to_components).
        const replacement: ComponentNode = {
            ...(msg.components[0] as ComponentNode),
            id: msg.stream_id,
        };
        const replaced = replaceById(prev, msg.stream_id, replacement);
        if (replaced !== null) return replaced;
        // First chunk: append
        return [...prev, replacement];
    }

    // Empty chunk with no error and no components — defensive no-op.
    return prev;
}
