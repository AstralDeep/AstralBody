/**
 * Feature 013 / US4 — FloatingChatPanel ↔ ToolPicker integration.
 *
 * Covers:
 *   - The picker trigger is visible in the composer button cluster (FR-016).
 *   - The trigger badge reflects narrowing (count of selected tools).
 *   - Zero-selection disables the send button with an explanatory tooltip
 *     (FR-021 / Q1 clarification).
 *   - Picker hides when there's no active reachable agent OR no permitted
 *     tools.
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";

type MotionPropsLike = Record<string, unknown> & {
    children?: React.ReactNode;
};

vi.mock("framer-motion", () => {
    const passthrough = (tag: string) =>
        React.forwardRef<HTMLElement, MotionPropsLike>((props, ref) => {
            const { initial: _i, animate: _a, exit: _e, transition: _t, layout: _l,
                    whileHover: _wh, whileTap: _wt, ...rest } = props;
            void _i; void _a; void _e; void _t; void _l; void _wh; void _wt;
            return React.createElement(tag, { ...rest, ref });
        });
    return {
        motion: new Proxy({} as Record<string, unknown>, {
            get: (_t, prop: string) => passthrough(prop),
        }),
        AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    };
});

vi.mock("react-markdown", () => ({
    default: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));
vi.mock("remark-gfm", () => ({ default: () => {} }));
vi.mock("../../TextOnlyBanner", () => ({
    default: () => <div data-testid="text-only-banner" />,
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), message: vi.fn() } }));

import FloatingChatPanel from "../../FloatingChatPanel";
import type { ChatStatus } from "../../../hooks/useWebSocket";

const idle: ChatStatus = { status: "idle", message: "" };
const sampleAgent = { id: "agent-x", name: "Grants Helper", available: true };
const sampleTools = [
    { name: "search_web", description: "Searches the web." },
    { name: "send_email", description: "Sends email." },
    { name: "ping" },
];

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const renderPanel = (overrides: Partial<React.ComponentProps<typeof FloatingChatPanel>> = {}) =>
    render(<FloatingChatPanel
        messages={[]}
        chatStatus={idle}
        onSendMessage={vi.fn()}
        onCancelTask={vi.fn()}
        isConnected={true}
        activeChatId="chat-1"
        toolsAvailableForUser={true}
        onOpenAgentSettings={vi.fn()}
        activeAgent={sampleAgent}
        permittedTools={sampleTools}
        selectedTools={null}
        onToolSelectionChange={vi.fn()}
        onToolSelectionReset={vi.fn()}
        {...overrides}
    />);

describe("FloatingChatPanel — ToolPicker integration (FR-016)", () => {
    it("renders the tool picker trigger when an agent + tools are present", () => {
        renderPanel();
        expect(screen.getByTestId("tool-picker-trigger")).toBeTruthy();
    });

    it("renders the trigger even when no agent is BOUND, so long as tools are passed (in-chat agent toggling — Feature 013 follow-up)", () => {
        renderPanel({ activeAgent: null });
        // Picker is now decoupled from `activeAgent`; users need it
        // available to flip agents on/off in-chat.
        expect(screen.getByTestId("tool-picker-trigger")).toBeTruthy();
    });

    it("hides the trigger when the active agent is unavailable", () => {
        renderPanel({ activeAgent: { ...sampleAgent, available: false } });
        expect(screen.queryByTestId("tool-picker-trigger")).toBeNull();
    });

    it("hides the trigger when there are no tools AND no agents", () => {
        renderPanel({ permittedTools: [], agents: [] });
        expect(screen.queryByTestId("tool-picker-trigger")).toBeNull();
    });

    it("opens the popover on click", () => {
        renderPanel();
        expect(screen.queryByTestId("tool-picker-popover")).toBeNull();
        fireEvent.click(screen.getByTestId("tool-picker-trigger"));
        expect(screen.getByTestId("tool-picker-popover")).toBeTruthy();
    });
});

describe("FloatingChatPanel — narrowing badge (FR-018)", () => {
    it("shows a count badge when the user has narrowed the selection", () => {
        renderPanel({ selectedTools: ["search_web"] });
        const badge = screen.getByTestId("tool-picker-badge");
        expect(badge.textContent).toBe("1");
    });

    it("does NOT show a badge when selection is null (default — full set)", () => {
        renderPanel({ selectedTools: null });
        expect(screen.queryByTestId("tool-picker-badge")).toBeNull();
    });
});

describe("FloatingChatPanel — zero-selection blocks send (FR-021)", () => {
    it("disables send and surfaces the explanatory tooltip when selection is []", () => {
        renderPanel({
            selectedTools: [],
            messages: [{ role: "user", content: "hi" }],
        });
        const send = screen.getByTestId("chat-send-button") as HTMLButtonElement;
        expect(send.disabled).toBe(true);
        expect(send.title).toMatch(/no tools selected/i);
    });

    it("does NOT disable send when selection is null (full default)", () => {
        renderPanel({ selectedTools: null });
        // Type into the input so the empty-input-disabled rule doesn't dominate.
        const input = screen.getByPlaceholderText(/ask anything/i);
        fireEvent.change(input, { target: { value: "hello" } });
        const send = screen.getByTestId("chat-send-button") as HTMLButtonElement;
        expect(send.disabled).toBe(false);
    });
});
