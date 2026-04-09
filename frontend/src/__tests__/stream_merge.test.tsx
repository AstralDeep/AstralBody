/**
 * Unit tests for `mergeStreamChunk` (001-tool-stream-ui frontend US1 T037).
 *
 * Verifies the invariants documented in
 * specs/001-tool-stream-ui/contracts/frontend-events.md §1:
 * 1. Identity preservation: siblings returned as `===` references.
 * 2. Replace-by-id: a chunk targeting an existing component overwrites it.
 * 3. First-chunk append: a chunk targeting an unknown id appends.
 * 4. Container nesting preserved.
 * 5. Reconnecting overlay decoration (decorate stub adds marker, US5 adds visual).
 * 6. Failed variant decoration (same).
 */
import { describe, it, expect } from "vitest";
import { mergeStreamChunk } from "../utils/streamMerge";
import type { UIStreamDataMessage } from "../types/streaming";

const makeMsg = (overrides: Partial<UIStreamDataMessage> = {}): UIStreamDataMessage => ({
    type: "ui_stream_data",
    stream_id: "stream-abc",
    session_id: "chat-1",
    seq: 1,
    components: [{ type: "metric", id: "stream-abc", value: "12C" }],
    ...overrides,
});

describe("mergeStreamChunk", () => {
    describe("first-chunk append", () => {
        it("appends to an empty tree", () => {
            const result = mergeStreamChunk([], makeMsg());
            expect(result).toHaveLength(1);
            expect(result[0]).toMatchObject({ id: "stream-abc", value: "12C" });
        });

        it("appends when no anchor exists", () => {
            const prev = [{ type: "card", id: "card-1", title: "Static" }];
            const result = mergeStreamChunk(prev, makeMsg());
            expect(result).toHaveLength(2);
            expect(result[0]).toBe(prev[0]); // identity preserved
            expect(result[1]).toMatchObject({ id: "stream-abc", value: "12C" });
        });
    });

    describe("replace-by-id", () => {
        it("overwrites the matching anchor", () => {
            const prev = [
                { type: "card", id: "card-1" },
                { type: "metric", id: "stream-abc", value: "10C" },
                { type: "alert", id: "alert-1" },
            ];
            const result = mergeStreamChunk(prev, makeMsg({ seq: 2 }));
            expect(result).toHaveLength(3);
            expect(result[1]).toMatchObject({ id: "stream-abc", value: "12C" });
        });

        it("preserves sibling identity (=== references)", () => {
            const card = { type: "card", id: "card-1" };
            const alert = { type: "alert", id: "alert-1" };
            const prev = [
                card,
                { type: "metric", id: "stream-abc", value: "10C" },
                alert,
            ];
            const result = mergeStreamChunk(prev, makeMsg({ seq: 2 }));
            // Siblings MUST be the same object instances
            expect(result[0]).toBe(card);
            expect(result[2]).toBe(alert);
            // Only the streaming component changed
            expect(result[1]).not.toBe(prev[1]);
        });

        it("does not duplicate when called twice with same id", () => {
            let tree: Array<Record<string, unknown>> = [];
            tree = mergeStreamChunk(tree, makeMsg({ seq: 1 }));
            tree = mergeStreamChunk(tree, makeMsg({
                seq: 2,
                components: [{ type: "metric", id: "stream-abc", value: "13C" }],
            }));
            expect(tree).toHaveLength(1);
            expect(tree[0]).toMatchObject({ value: "13C" });
        });
    });

    describe("container nesting", () => {
        it("recurses into children to find the anchor", () => {
            const prev = [{
                type: "container",
                id: "outer",
                children: [
                    { type: "metric", id: "stream-abc", value: "10C" },
                    { type: "text", id: "text-1", content: "label" },
                ],
            }];
            const result = mergeStreamChunk(prev, makeMsg({ seq: 2 }));
            const updatedContainer = result[0] as { children: Array<Record<string, unknown>> };
            expect(updatedContainer.children[0]).toMatchObject({
                id: "stream-abc",
                value: "12C",
            });
            // The sibling text inside the container is still the same instance
            const prevContainer = prev[0] as { children: Array<Record<string, unknown>> };
            expect(updatedContainer.children[1]).toBe(prevContainer.children[1]);
        });
    });

    describe("error chunks", () => {
        it("decorates the existing anchor with reconnecting marker", () => {
            const prev = [{ type: "metric", id: "stream-abc", value: "10C" }];
            const result = mergeStreamChunk(prev, makeMsg({
                seq: 2,
                components: [],
                error: {
                    code: "upstream_unavailable",
                    message: "blip",
                    phase: "reconnecting",
                    attempt: 1,
                    next_retry_at_ms: Date.now() + 1000,
                    retryable: false,
                },
            }));
            const decorated = result[0] as Record<string, unknown>;
            expect(decorated["id"]).toBe("stream-abc");
            // Stub decorator adds the marker; US5 turns it into visual.
            expect(decorated["_streamReconnecting"]).toBeDefined();
        });

        it("decorates with failed marker on terminal failure", () => {
            const prev = [{ type: "metric", id: "stream-abc", value: "10C" }];
            const result = mergeStreamChunk(prev, makeMsg({
                seq: 2,
                components: [],
                error: {
                    code: "upstream_unavailable",
                    message: "down",
                    phase: "failed",
                    retryable: true,
                },
            }));
            const decorated = result[0] as Record<string, unknown>;
            expect(decorated["id"]).toBe("stream-abc");
            expect(decorated["_streamFailed"]).toBeDefined();
        });
    });
});
