/**
 * Frontend stream_attach test (001-tool-stream-ui US4 T070).
 *
 * When the orchestrator deduplicates a subscribe (FR-009a) and the new
 * client attaches to an existing subscription that happens to be mid-
 * RECONNECTING, the next chunk that arrives may be a `phase: "reconnecting"`
 * chunk rather than a fresh data chunk. The merge layer must handle this
 * gracefully — it must NOT crash on a missing prior component, AND it must
 * place the reconnecting overlay correctly.
 */
import { describe, it, expect } from "vitest";
import { mergeStreamChunk } from "../utils/streamMerge";
import type { UIStreamDataMessage } from "../types/streaming";

describe("stream attach (FR-009a)", () => {
    it("first chunk after attach can be a reconnecting chunk", () => {
        // No prior anchor in the tree (this client just attached)
        let tree: Array<Record<string, unknown>> = [];

        const reconnecting: UIStreamDataMessage = {
            type: "ui_stream_data",
            stream_id: "stream-attached",
            session_id: "chat-1",
            seq: 5,  // server is mid-stream
            components: [],
            error: {
                code: "upstream_unavailable",
                message: "blip",
                phase: "reconnecting",
                attempt: 2,
                next_retry_at_ms: Date.now() + 5000,
                retryable: false,
            },
        };
        tree = mergeStreamChunk(tree, reconnecting);
        // Merge should append a placeholder decorated with reconnecting marker
        expect(tree).toHaveLength(1);
        const node = tree[0] as Record<string, unknown>;
        expect(node["id"]).toBe("stream-attached");
        expect(node["_streamReconnecting"]).toBeDefined();
    });

    it("recovery chunk after attach replaces the reconnecting decoration", () => {
        let tree: Array<Record<string, unknown>> = [];
        // Attach into mid-RECONNECTING
        tree = mergeStreamChunk(tree, {
            type: "ui_stream_data",
            stream_id: "stream-attached",
            session_id: "chat-1",
            seq: 5,
            components: [],
            error: {
                code: "upstream_unavailable",
                message: "blip",
                phase: "reconnecting",
                attempt: 2,
                retryable: false,
            },
        });
        // Recovery
        tree = mergeStreamChunk(tree, {
            type: "ui_stream_data",
            stream_id: "stream-attached",
            session_id: "chat-1",
            seq: 6,
            components: [{ type: "metric", id: "stream-attached", value: "12C" }],
        });
        expect(tree).toHaveLength(1);
        const node = tree[0] as Record<string, unknown>;
        expect(node["id"]).toBe("stream-attached");
        expect(node["value"]).toBe("12C");
        // Reconnecting marker is gone
        expect(node["_streamReconnecting"]).toBeUndefined();
    });
});
