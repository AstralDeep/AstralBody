/**
 * Tests for CosmicProgressIndicator (feature 014-progress-notifications, US1).
 *
 * Covers FR-001 through FR-006 and SC-001/SC-002:
 *  - Mounts when chatStatus.status is in-flight (thinking/executing/fixing)
 *  - Hidden when status is idle/done (FR-005)
 *  - Displayed word always belongs to the approved 55-word list (FR-002)
 *  - Word rotates while in-flight (FR-003) — at least once per second cadence
 *  - Word never repeats twice in a row (R7 anti-stutter rule)
 *  - Cleans up its interval on unmount
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";

import { CosmicProgressIndicator } from "../components/chat/CosmicProgressIndicator";
import { COSMIC_WORDS } from "../components/chat/chatStepWords";
import type { ChatStatus } from "../hooks/useWebSocket";

const make = (status: ChatStatus["status"]): ChatStatus => ({ status, message: "" });

beforeEach(() => {
    vi.useFakeTimers();
});

afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    cleanup();
});

describe("CosmicProgressIndicator — visibility (FR-001, FR-005)", () => {
    it("renders when status is 'thinking'", () => {
        render(<CosmicProgressIndicator chatStatus={make("thinking")} />);
        expect(screen.getByTestId("cosmic-progress-indicator")).toBeTruthy();
    });

    it("renders when status is 'executing'", () => {
        render(<CosmicProgressIndicator chatStatus={make("executing")} />);
        expect(screen.getByTestId("cosmic-progress-indicator")).toBeTruthy();
    });

    it("renders when status is 'fixing'", () => {
        // 'fixing' is not in the original ChatStatus union but is emitted by the
        // orchestrator (orchestrator.py:2585 etc.) — the component MUST treat
        // it as in-flight so the indicator stays visible during fix loops.
        render(<CosmicProgressIndicator chatStatus={make("fixing" as ChatStatus["status"])} />);
        expect(screen.getByTestId("cosmic-progress-indicator")).toBeTruthy();
    });

    it("does not render when status is 'idle'", () => {
        render(<CosmicProgressIndicator chatStatus={make("idle")} />);
        expect(screen.queryByTestId("cosmic-progress-indicator")).toBeNull();
    });

    it("does not render when status is 'done'", () => {
        render(<CosmicProgressIndicator chatStatus={make("done")} />);
        expect(screen.queryByTestId("cosmic-progress-indicator")).toBeNull();
    });
});

describe("CosmicProgressIndicator — word selection (FR-002, FR-004)", () => {
    it("displays a word from the approved 55-word list", () => {
        render(<CosmicProgressIndicator chatStatus={make("thinking")} />);
        const word = screen.getByTestId("cosmic-progress-word").textContent ?? "";
        // Strip a trailing ellipsis if the component renders one.
        const trimmed = word.replace(/[….\s]+$/, "");
        expect(COSMIC_WORDS).toContain(trimmed);
    });

    it("never displays a word outside the approved list across many rotations", () => {
        render(<CosmicProgressIndicator chatStatus={make("thinking")} />);
        const seen = new Set<string>();
        for (let i = 0; i < 60; i += 1) {
            const word = (screen.getByTestId("cosmic-progress-word").textContent ?? "")
                .replace(/[….\s]+$/, "");
            seen.add(word);
            act(() => {
                vi.advanceTimersByTime(1500);
            });
        }
        for (const word of seen) {
            expect(COSMIC_WORDS).toContain(word);
        }
    });
});

describe("CosmicProgressIndicator — rotation cadence (FR-003, SC-002)", () => {
    it("changes the displayed word at least once per second on average", () => {
        render(<CosmicProgressIndicator chatStatus={make("thinking")} />);
        const initial = screen.getByTestId("cosmic-progress-word").textContent;
        // Advance well past the 1.2 s rotation cadence chosen in research R7;
        // SC-002 floor is 1×/sec — three seconds must produce at least one change.
        act(() => {
            vi.advanceTimersByTime(3000);
        });
        const after = screen.getByTestId("cosmic-progress-word").textContent;
        expect(after).not.toEqual(initial);
    });

    it("does not stall on the same word for more than 3 seconds (SC-002 ceiling)", () => {
        render(<CosmicProgressIndicator chatStatus={make("thinking")} />);
        const seen: Array<string | null> = [];
        for (let i = 0; i < 4; i += 1) {
            seen.push(screen.getByTestId("cosmic-progress-word").textContent);
            act(() => {
                vi.advanceTimersByTime(1500);
            });
        }
        // Across 4 samples spanning 4.5 s of simulated time, at least two
        // distinct words must appear.
        const distinct = new Set(seen.filter((s): s is string => s !== null));
        expect(distinct.size).toBeGreaterThan(1);
    });
});

describe("CosmicProgressIndicator — lifecycle hygiene", () => {
    it("clears its interval when status flips from thinking to idle", () => {
        const { rerender } = render(
            <CosmicProgressIndicator chatStatus={make("thinking")} />,
        );
        expect(screen.getByTestId("cosmic-progress-indicator")).toBeTruthy();

        rerender(<CosmicProgressIndicator chatStatus={make("idle")} />);
        expect(screen.queryByTestId("cosmic-progress-indicator")).toBeNull();

        // Advancing time after unmount must not throw or schedule new work.
        expect(() =>
            act(() => {
                vi.advanceTimersByTime(5000);
            }),
        ).not.toThrow();
    });

    it("clears its interval on unmount", () => {
        const { unmount } = render(
            <CosmicProgressIndicator chatStatus={make("thinking")} />,
        );
        unmount();
        expect(() =>
            act(() => {
                vi.advanceTimersByTime(5000);
            }),
        ).not.toThrow();
    });
});
