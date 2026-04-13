/**
 * Regression test for the stream_subscribe wire-format bug (2026-04-13):
 * before this fix, the `saved_components_list` and `chat_loaded` auto-subscribe
 * paths always sent the legacy poll-format message (`interval_seconds`,
 * no `session_id`) regardless of whether the tool was push or poll. Push
 * tools like `live_system_metrics` never started streaming as a result.
 *
 * See specs/001-tool-stream-ui/contracts/frontend-events.md §6.
 */
import { describe, it, expect, vi } from "vitest";
import { sendStreamSubscribe } from "../hooks/useWebSocket";

function mockWs() {
    const sent: string[] = [];
    const ws = {
        send: vi.fn((payload: string) => { sent.push(payload); }),
    } as unknown as WebSocket;
    return { ws, sent };
}

describe("sendStreamSubscribe push/poll wire format", () => {
    it("push tools send session_id and NO interval_seconds", () => {
        const { ws, sent } = mockWs();
        sendStreamSubscribe(
            ws,
            "live_system_metrics",
            { default_interval: 2, kind: "push" },
            { interval_s: 5 },
            "chat-abc",
        );
        expect(sent).toHaveLength(1);
        const msg = JSON.parse(sent[0]);
        expect(msg).toMatchObject({
            type: "ui_event",
            action: "stream_subscribe",
            session_id: "chat-abc",
            payload: { tool_name: "live_system_metrics", params: { interval_s: 5 } },
        });
        expect(msg.payload).not.toHaveProperty("interval_seconds");
    });

    it("poll tools send interval_seconds and NO session_id", () => {
        const { ws, sent } = mockWs();
        sendStreamSubscribe(
            ws,
            "get_system_status",
            { default_interval: 2, kind: "poll" },
            {},
            "chat-abc",
        );
        const msg = JSON.parse(sent[0]);
        expect(msg).toMatchObject({
            type: "ui_event",
            action: "stream_subscribe",
            payload: { tool_name: "get_system_status", interval_seconds: 2, params: {} },
        });
        expect(msg).not.toHaveProperty("session_id");
    });

    it("defaults to poll format when kind is missing", () => {
        const { ws, sent } = mockWs();
        sendStreamSubscribe(ws, "legacy_tool", { default_interval: 3 }, {}, null);
        const msg = JSON.parse(sent[0]);
        expect(msg.payload).toHaveProperty("interval_seconds", 3);
    });
});
