/**
 * Frontend reconnecting overlay tests (001-tool-stream-ui US5 T089).
 *
 * Verifies that mergeStreamChunk correctly decorates a component when a
 * `phase: "reconnecting"` chunk arrives, that a successful recovery chunk
 * removes the decoration in a single render, and that a `phase: "failed"`
 * chunk surfaces the right markers for the manual retry button vs the
 * sign-in-again button.
 */
import { describe, it, expect } from "vitest";
import { mergeStreamChunk } from "../utils/streamMerge";
import type { UIStreamDataMessage } from "../types/streaming";

const dataChunk = (seq: number, value: string): UIStreamDataMessage => ({
    type: "ui_stream_data",
    stream_id: "stream-x",
    session_id: "chat-1",
    seq,
    components: [{ type: "metric", id: "stream-x", value }],
});

const reconnectingChunk = (
    seq: number,
    attempt: number,
): UIStreamDataMessage => ({
    type: "ui_stream_data",
    stream_id: "stream-x",
    session_id: "chat-1",
    seq,
    components: [],
    error: {
        code: "upstream_unavailable",
        message: "blip",
        phase: "reconnecting",
        attempt,
        next_retry_at_ms: Date.now() + 5000,
        retryable: false,
    },
});

const failedChunk = (
    code: "upstream_unavailable" | "unauthenticated" | "unauthorized",
    retryable: boolean,
): UIStreamDataMessage => ({
    type: "ui_stream_data",
    stream_id: "stream-x",
    session_id: "chat-1",
    seq: 99,
    components: [],
    error: {
        code,
        message: code === "unauthenticated" ? "session expired" : "down",
        phase: "failed",
        retryable,
    },
});

describe("reconnecting overlay", () => {
    it("decorates existing data without removing it", () => {
        let tree: Array<Record<string, unknown>> = [];
        // Initial good data
        tree = mergeStreamChunk(tree, dataChunk(1, "10C"));
        // Reconnecting attempt 1
        tree = mergeStreamChunk(tree, reconnectingChunk(2, 1));
        expect(tree).toHaveLength(1);
        const node = tree[0] as Record<string, unknown>;
        expect(node["id"]).toBe("stream-x");
        expect(node["_streamReconnecting"]).toBeDefined();
        expect((node["_streamReconnecting"] as Record<string, unknown>)["attempt"]).toBe(1);
    });

    it("recovery chunk overwrites the overlay in one render", () => {
        let tree: Array<Record<string, unknown>> = [];
        tree = mergeStreamChunk(tree, dataChunk(1, "10C"));
        tree = mergeStreamChunk(tree, reconnectingChunk(2, 1));
        // Recovery
        tree = mergeStreamChunk(tree, dataChunk(3, "12C"));
        expect(tree).toHaveLength(1);
        const node = tree[0] as Record<string, unknown>;
        expect(node["value"]).toBe("12C");
        expect(node["_streamReconnecting"]).toBeUndefined();
    });

    it("multiple reconnect attempts increment the attempt counter", () => {
        let tree: Array<Record<string, unknown>> = [];
        tree = mergeStreamChunk(tree, dataChunk(1, "10C"));
        tree = mergeStreamChunk(tree, reconnectingChunk(2, 1));
        tree = mergeStreamChunk(tree, reconnectingChunk(3, 2));
        tree = mergeStreamChunk(tree, reconnectingChunk(4, 3));
        const node = tree[0] as Record<string, unknown>;
        expect((node["_streamReconnecting"] as Record<string, unknown>)["attempt"]).toBe(3);
    });

    it("failed chunk with retryable=true marks for manual retry button", () => {
        let tree: Array<Record<string, unknown>> = [];
        tree = mergeStreamChunk(tree, dataChunk(1, "10C"));
        tree = mergeStreamChunk(tree, failedChunk("upstream_unavailable", true));
        const node = tree[0] as Record<string, unknown>;
        const failed = node["_streamFailed"] as Record<string, unknown>;
        expect(failed).toBeDefined();
        expect(failed["retryable"]).toBe(true);
        expect(failed["code"]).toBe("upstream_unavailable");
    });

    it("failed unauthenticated chunk marks for re-authentication (not retry)", () => {
        let tree: Array<Record<string, unknown>> = [];
        tree = mergeStreamChunk(tree, dataChunk(1, "10C"));
        tree = mergeStreamChunk(tree, failedChunk("unauthenticated", false));
        const node = tree[0] as Record<string, unknown>;
        const failed = node["_streamFailed"] as Record<string, unknown>;
        expect(failed).toBeDefined();
        expect(failed["retryable"]).toBe(false);
        expect(failed["code"]).toBe("unauthenticated");
    });
});
