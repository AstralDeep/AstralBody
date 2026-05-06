/**
 * Tests for <ChatStepEntry> (feature 014-progress-notifications).
 *
 * Per the simplification handed down: the entry renders a single inline
 * `Calling '<tool-name>'` line in chronological order. No status badges,
 * no expand/collapse, no args/result display.
 */
import { describe, it, expect, afterEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { ChatStepEntry } from "../components/chat/ChatStepEntry";
import type { ChatStep, ChatStepStatus } from "../types/chatSteps";

afterEach(() => {
    cleanup();
});

const makeStep = (overrides: Partial<ChatStep> = {}): ChatStep => ({
    id: `step-${Math.random().toString(36).slice(2)}`,
    chat_id: "chat-1",
    turn_message_id: 1,
    kind: "tool_call",
    name: "search_grants",
    status: "in_progress",
    args_truncated: '{"q":"biomed"}',
    args_was_truncated: false,
    result_summary: null,
    result_was_truncated: false,
    error_message: null,
    started_at: 1000,
    ended_at: null,
    ...overrides,
});

describe("ChatStepEntry", () => {
    it("renders the tool name in a 'Calling' line", () => {
        render(<ChatStepEntry step={makeStep({ name: "fetch_nsf" })} />);
        const line = screen.getByTestId("chat-step-line");
        expect(line.textContent).toBe("Calling 'fetch_nsf'");
    });

    it.each<ChatStepStatus>(["in_progress", "completed", "errored", "cancelled", "interrupted"])(
        "renders the same line shape regardless of status (%s)",
        (status) => {
            render(<ChatStepEntry step={makeStep({ status, name: "x" })} />);
            expect(screen.getByTestId("chat-step-line").textContent).toBe("Calling 'x'");
        },
    );

    it("does not render any args, result, or error content", () => {
        render(<ChatStepEntry step={makeStep({
            args_truncated: "lots of stuff including a giant token",
            args_was_truncated: true,
            result_summary: "result preview",
            result_was_truncated: true,
            error_message: "something broke",
            status: "errored",
        })} />);
        const root = screen.getByTestId("chat-step-entry");
        expect(root.textContent).toBe("Calling 'search_grants'");
        expect(screen.queryByTestId("chat-step-args-truncated-badge")).toBeNull();
        expect(screen.queryByTestId("chat-step-result-truncated-badge")).toBeNull();
        expect(screen.queryByTestId("chat-step-error")).toBeNull();
        expect(screen.queryByTestId("chat-step-toggle")).toBeNull();
        expect(screen.queryByTestId("chat-step-body")).toBeNull();
    });

    it("exposes the step id and status as data attributes for selectors", () => {
        render(<ChatStepEntry step={makeStep({ id: "abc-123", status: "completed" })} />);
        const root = screen.getByTestId("chat-step-entry");
        expect(root.getAttribute("data-step-id")).toBe("abc-123");
        expect(root.getAttribute("data-status")).toBe("completed");
    });
});
