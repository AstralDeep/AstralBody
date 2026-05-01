/**
 * Tests for FloatingChatPanel's mount-set / streaming behavior
 * (feature 010-fix-page-flash, FR-006).
 *
 * Pins the contract that:
 *   - The panel container itself receives `initial={false}` on first
 *     paint so the chat shell does not fade in over historical chat
 *     content (US2 — eliminates flash on chat switch).
 *   - Messages present at first render receive `initial={false}` and
 *     do NOT animate in (US2).
 *   - Messages added after first render DO animate in (US3 — streaming
 *     replies are visually distinguished from history).
 */
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Mock framer-motion: encode `initial` into a `data-initial` attribute.
// ---------------------------------------------------------------------------
type MotionPropsLike = Record<string, unknown> & {
    initial?: unknown;
    children?: React.ReactNode;
};

vi.mock("framer-motion", () => {
    // Memoize per-tag so the Proxy returns the SAME component instance
    // across renders; otherwise the captured-`initial` useState below
    // resets on every render and the mock falsely reports the latest
    // initial instead of the first.
    const cache = new Map<string, React.ComponentType<MotionPropsLike>>();
    const passthrough = (tag: string) => {
        const cached = cache.get(tag);
        if (cached) return cached;
        const C = React.forwardRef<HTMLElement, MotionPropsLike>((props, ref) => {
            const {
                initial,
                animate: _animate,
                exit: _exit,
                transition: _transition,
                layout: _layout,
                whileHover: _whileHover,
                whileTap: _whileTap,
                ...rest
            } = props;
            void _animate; void _exit; void _transition; void _layout;
            void _whileHover; void _whileTap;
            // Capture `initial` from the FIRST render of this element and
            // never update it — mirrors framer-motion's behavior, which
            // only honors `initial` on mount.
            const [firstInitial] = React.useState(() => initial);
            const dataInitial = firstInitial === false ? "false" : "animate";
            // eslint-disable-next-line react-hooks/refs
            return React.createElement(tag, { ...rest, ref, "data-initial": dataInitial });
        });
        cache.set(tag, C as unknown as React.ComponentType<MotionPropsLike>);
        return C as unknown as React.ComponentType<MotionPropsLike>;
    };
    return {
        motion: new Proxy({} as Record<string, unknown>, {
            get: (_t, prop: string) => passthrough(prop),
        }),
        AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    };
});

// Mock heavyweight imports we don't exercise.
vi.mock("react-markdown", () => ({
    default: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));
vi.mock("remark-gfm", () => ({ default: () => {} }));
vi.mock("../TextOnlyBanner", () => ({
    default: () => <div data-testid="text-only-banner" />,
}));
// Sonner toast — keep it inert in tests.
vi.mock("sonner", () => ({ toast: { error: vi.fn(), message: vi.fn() } }));

import FloatingChatPanel from "../FloatingChatPanel";
import type { ChatStatus } from "../../hooks/useWebSocket";

const baseStatus: ChatStatus = { status: "idle", message: "" };
const baseProps = {
    chatStatus: baseStatus,
    onSendMessage: vi.fn(),
    onCancelTask: vi.fn(),
    isConnected: true,
    activeChatId: "chat-1",
    accessToken: "tok",
    deviceCapabilities: {
        hasMicrophone: false,
        hasGeolocation: false,
        speechServerAvailable: false,
    },
    toolsAvailableForUser: true,
    onOpenAgentSettings: vi.fn(),
};

beforeEach(() => {
    vi.clearAllMocks();
});

afterEach(() => {
    cleanup();
});

describe("FloatingChatPanel — first-paint silence (US2)", () => {
    it("the panel container renders with initial={false} on first mount", () => {
        const { container } = render(
            <FloatingChatPanel {...baseProps} messages={[]} />,
        );
        // The panel wrapper has the distinctive 'fixed bottom-4 right-4' class.
        const panel = container.querySelector(
            "[data-initial].fixed.bottom-4.right-4",
        ) as HTMLElement | null;
        expect(panel).not.toBeNull();
        expect(panel!.dataset.initial).toBe("false");
    });

    it("messages present at first render receive initial={false}", () => {
        const messages = [
            { role: "user", content: "hello" },
            { role: "assistant", content: "hi back" },
            { role: "user", content: "how are you" },
        ];
        const { container } = render(
            <FloatingChatPanel {...baseProps} messages={messages} />,
        );
        // Chat-message rows live inside the messages scroll container; they
        // each carry a `flex gap-2` class. Querying for the data-initial
        // attribute on those rows tells us whether they animated in.
        const rows = Array.from(
            container.querySelectorAll<HTMLElement>("[data-initial]"),
        ).filter((el) => el.className.includes("flex gap-2"));
        expect(rows.length).toBe(messages.length);
        for (const row of rows) {
            expect(row.dataset.initial).toBe("false");
        }
    });
});

describe("FloatingChatPanel — streaming additions (US3)", () => {
    it("messages added after mount receive the entry-animation initial", () => {
        const initial = [
            { role: "user", content: "first" },
            { role: "assistant", content: "second" },
        ];
        const { container, rerender } = render(
            <FloatingChatPanel {...baseProps} messages={initial} />,
        );
        // Sanity: both initial messages calm.
        const initialRows = Array.from(
            container.querySelectorAll<HTMLElement>("[data-initial]"),
        ).filter((el) => el.className.includes("flex gap-2"));
        expect(initialRows.map((r) => r.dataset.initial)).toEqual([
            "false",
            "false",
        ]);

        // Stream a new message in.
        rerender(
            <FloatingChatPanel
                {...baseProps}
                messages={[...initial, { role: "assistant", content: "third" }]}
            />,
        );
        const afterRows = Array.from(
            container.querySelectorAll<HTMLElement>("[data-initial]"),
        ).filter((el) => el.className.includes("flex gap-2"));
        expect(afterRows.length).toBe(3);
        // First two stay calm; third animates.
        expect(afterRows[0].dataset.initial).toBe("false");
        expect(afterRows[1].dataset.initial).toBe("false");
        expect(afterRows[2].dataset.initial).toBe("animate");
    });

    it("multiple streamed additions never re-flash existing messages", () => {
        const initial = [{ role: "user", content: "q1" }];
        const { container, rerender } = render(
            <FloatingChatPanel {...baseProps} messages={initial} />,
        );
        const acc = [...initial];
        for (let i = 0; i < 5; i++) {
            acc.push({ role: "assistant", content: `r${i}` });
            rerender(<FloatingChatPanel {...baseProps} messages={acc} />);
        }
        const rows = Array.from(
            container.querySelectorAll<HTMLElement>("[data-initial]"),
        ).filter((el) => el.className.includes("flex gap-2"));
        expect(rows.length).toBe(acc.length);
        // The first message (present at first paint) never gets an
        // entry animation, no matter how many additions arrive after.
        expect(rows[0].dataset.initial).toBe("false");
        // Every later message animated in.
        for (let i = 1; i < rows.length; i++) {
            expect(rows[i].dataset.initial).toBe("animate");
        }
    });
});
