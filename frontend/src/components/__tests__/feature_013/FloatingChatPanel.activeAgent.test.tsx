/**
 * Feature 013 / US2 — active-agent indicator + unavailable banner.
 *
 * Covers:
 *   - FR-006: header shows the active agent's name on render before any
 *     message is sent.
 *   - FR-007: assistant message bubbles attribute the reply to the agent.
 *   - FR-009: when the bound agent is unavailable, the unavailable banner
 *     renders, send is disabled with a tooltip, and the action buttons
 *     fire the parent callbacks.
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Lightweight mocks of the same heavy imports used in
// FloatingChatPanel.flash.test.tsx so the panel mounts in jsdom.
// ---------------------------------------------------------------------------
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

const idleStatus: ChatStatus = { status: "idle", message: "" };

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const renderPanel = (overrides: Partial<React.ComponentProps<typeof FloatingChatPanel>> = {}) => {
    const props: React.ComponentProps<typeof FloatingChatPanel> = {
        messages: [],
        chatStatus: idleStatus,
        onSendMessage: vi.fn(),
        onCancelTask: vi.fn(),
        isConnected: true,
        activeChatId: "chat-1",
        toolsAvailableForUser: true,
        onOpenAgentSettings: vi.fn(),
        ...overrides,
    };
    return render(<FloatingChatPanel {...props} />);
};

describe("FloatingChatPanel — active agent indicator (FR-006)", () => {
    it("renders the agent name in the header before any message is sent", () => {
        renderPanel({
            activeAgent: { id: "agent-x", name: "Grants Helper", available: true },
        });
        const name = screen.getByTestId("active-agent-name");
        expect(name.textContent).toBe("Grants Helper");
        // No unavailable tag when the agent is reachable.
        expect(screen.queryByTestId("active-agent-unavailable-tag")).toBeNull();
        expect(screen.queryByTestId("agent-unavailable-banner")).toBeNull();
    });

    it("falls back to the neutral 'Chat' label when no agent is bound", () => {
        renderPanel({ activeAgent: null });
        expect(screen.queryByTestId("active-agent-name")).toBeNull();
        // The "Chat" fallback header is text content, not a testid.
        expect(screen.getByTestId("chat-header").textContent).toMatch(/chat/i);
    });
});

describe("FloatingChatPanel — assistant attribution (FR-007)", () => {
    it("attributes assistant bubbles to the active agent", () => {
        renderPanel({
            activeAgent: { id: "agent-x", name: "Grants Helper", available: true },
            messages: [
                { role: "user", content: "hi" },
                { role: "assistant", content: "hello!" },
            ],
        });
        const tags = screen.getAllByTestId("assistant-agent-attribution");
        expect(tags.length).toBe(1);
        expect(tags[0].textContent).toBe("Grants Helper");
    });

    it("omits attribution when no agent is bound", () => {
        renderPanel({
            activeAgent: null,
            messages: [{ role: "assistant", content: "hello" }],
        });
        expect(screen.queryByTestId("assistant-agent-attribution")).toBeNull();
    });
});

describe("FloatingChatPanel — unavailable agent (FR-009 / Q3 clarification)", () => {
    it("renders the unavailable banner and tags the header when the agent is gone", () => {
        renderPanel({
            activeAgent: { id: "agent-x", name: "Grants Helper", available: false },
        });
        expect(screen.getByTestId("agent-unavailable-banner")).toBeTruthy();
        expect(screen.getByTestId("active-agent-unavailable-tag")).toBeTruthy();
        expect(screen.getByTestId("agent-unavailable-banner").textContent)
            .toMatch(/Grants Helper/);
    });

    it("disables the send button with an explanatory tooltip", () => {
        renderPanel({
            activeAgent: { id: "agent-x", name: "Grants Helper", available: false },
            messages: [{ role: "user", content: "hi" }],
        });
        const send = screen.getByTestId("chat-send-button") as HTMLButtonElement;
        expect(send.disabled).toBe(true);
        expect(send.title).toMatch(/no longer available/i);
    });

    it("invokes onStartNewChat / onOpenAgentSettings from the banner action buttons", () => {
        const onStartNewChat = vi.fn();
        const onOpenAgentSettings = vi.fn();
        renderPanel({
            activeAgent: { id: "agent-x", name: "Grants Helper", available: false },
            onStartNewChat,
            onOpenAgentSettings,
        });
        fireEvent.click(screen.getByTestId("agent-unavailable-new-chat"));
        fireEvent.click(screen.getByTestId("agent-unavailable-pick-agent"));
        expect(onStartNewChat).toHaveBeenCalledTimes(1);
        expect(onOpenAgentSettings).toHaveBeenCalledTimes(1);
    });

    it("does NOT render the unavailable banner when the agent is reachable", () => {
        renderPanel({
            activeAgent: { id: "agent-x", name: "Grants Helper", available: true },
        });
        expect(screen.queryByTestId("agent-unavailable-banner")).toBeNull();
    });

    it("does NOT render the unavailable banner when no agent is bound", () => {
        renderPanel({ activeAgent: null });
        expect(screen.queryByTestId("agent-unavailable-banner")).toBeNull();
    });
});
