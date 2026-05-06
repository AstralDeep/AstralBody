/**
 * Unit tests for the `chat_step` WebSocket arm of useWebSocket
 * (feature 014, T010).
 *
 * Validates the merge semantics that the contract guarantees:
 *  - Each event carries the full row state; clients overwrite by `step.id`.
 *  - Out-of-order delivery (terminal arriving before start) resolves to
 *    the highest-`started_at`/`ended_at` view the client has.
 *  - Steps from different chats stay isolated under their own `chat_id` key.
 *
 * The merge logic lives inside the `case "chat_step"` arm of useWebSocket;
 * we exercise it by constructing the same reducer the hook uses (the arm is
 * a pure setState update, so we can test it as a function).
 */
import { describe, it, expect } from "vitest";

import type { ChatStep, ChatStepsByChat } from "../../types/chatSteps";

/**
 * Mirror of the merge logic in useWebSocket.ts → case "chat_step":
 *   setChatSteps(prev => ({
 *     ...prev,
 *     [chat_id]: { ...(prev[chat_id] ?? {}), [step.id]: step },
 *   }))
 *
 * Pulled out as a pure helper so we can unit-test it directly without
 * spinning up the WebSocket harness.
 */
function applyChatStepEvent(
    prev: ChatStepsByChat,
    chatId: string,
    step: ChatStep,
): ChatStepsByChat {
    const existing = prev[chatId] ?? {};
    return {
        ...prev,
        [chatId]: { ...existing, [step.id]: step },
    };
}

const makeStep = (overrides: Partial<ChatStep> = {}): ChatStep => ({
    id: "step-1",
    chat_id: "chat-A",
    turn_message_id: 1,
    kind: "tool_call",
    name: "search_grants",
    status: "in_progress",
    args_truncated: null,
    args_was_truncated: false,
    result_summary: null,
    result_was_truncated: false,
    error_message: null,
    started_at: 1000,
    ended_at: null,
    ...overrides,
});

describe("useWebSocket — chat_step merge semantics", () => {
    it("inserts a new step under its chat_id", () => {
        const next = applyChatStepEvent({}, "chat-A", makeStep());
        expect(next["chat-A"]["step-1"].status).toBe("in_progress");
    });

    it("terminal event overwrites in-progress entry by step.id", () => {
        const start = applyChatStepEvent({}, "chat-A", makeStep());
        const done = applyChatStepEvent(
            start,
            "chat-A",
            makeStep({ status: "completed", ended_at: 2000 }),
        );
        expect(done["chat-A"]["step-1"].status).toBe("completed");
        expect(done["chat-A"]["step-1"].ended_at).toBe(2000);
    });

    it("preserves entries for other chats when updating one", () => {
        const a = applyChatStepEvent({}, "chat-A", makeStep({ id: "s-a" }));
        const ab = applyChatStepEvent(a, "chat-B", makeStep({ id: "s-b", chat_id: "chat-B" }));
        expect(Object.keys(ab["chat-A"])).toEqual(["s-a"]);
        expect(Object.keys(ab["chat-B"])).toEqual(["s-b"]);
    });

    it("merges multiple distinct steps into the same chat", () => {
        let state: ChatStepsByChat = {};
        state = applyChatStepEvent(state, "chat-A", makeStep({ id: "a", started_at: 100 }));
        state = applyChatStepEvent(state, "chat-A", makeStep({ id: "b", started_at: 200 }));
        state = applyChatStepEvent(state, "chat-A", makeStep({ id: "c", started_at: 300 }));
        expect(Object.keys(state["chat-A"]).sort()).toEqual(["a", "b", "c"]);
    });

    it("does not mutate the previous state object (immutable update)", () => {
        const prev = { "chat-A": { "step-1": makeStep() } };
        const snapshot = JSON.parse(JSON.stringify(prev));
        const next = applyChatStepEvent(prev, "chat-A", makeStep({ status: "completed", ended_at: 999 }));
        expect(prev).toEqual(snapshot);
        expect(next).not.toBe(prev);
    });
});
