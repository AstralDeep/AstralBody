import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";

import { Tooltip } from "../Tooltip";
import { TooltipProvider } from "../TooltipProvider";

function renderWithProvider(ui: React.ReactNode) {
    return render(<TooltipProvider>{ui}</TooltipProvider>);
}

describe("Tooltip", () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    it("renders no tooltip frame when text is empty (FR-008)", () => {
        renderWithProvider(
            <Tooltip text="">
                <button>Hi</button>
            </Tooltip>,
        );
        fireEvent.mouseEnter(screen.getByRole("button"));
        act(() => { vi.advanceTimersByTime(2000); });
        expect(screen.queryByRole("tooltip")).toBeNull();
    });

    it("renders no tooltip frame when text is whitespace-only", () => {
        renderWithProvider(
            <Tooltip text="   ">
                <button>Hi</button>
            </Tooltip>,
        );
        fireEvent.mouseEnter(screen.getByRole("button"));
        act(() => { vi.advanceTimersByTime(2000); });
        expect(screen.queryByRole("tooltip")).toBeNull();
    });

    it("opens after 500 ms of hover", () => {
        renderWithProvider(
            <Tooltip text="hello">
                <button>Hi</button>
            </Tooltip>,
        );
        fireEvent.mouseEnter(screen.getByRole("button"));
        // Just under 500 ms — still hidden
        act(() => { vi.advanceTimersByTime(499); });
        expect(screen.queryByRole("tooltip")).toBeNull();
        // Cross the 500 ms threshold
        act(() => { vi.advanceTimersByTime(2); });
        expect(screen.getByRole("tooltip")).toHaveTextContent("hello");
    });

    it("opens immediately on keyboard focus", () => {
        renderWithProvider(
            <Tooltip text="focus me">
                <button>Hi</button>
            </Tooltip>,
        );
        fireEvent.focus(screen.getByRole("button"));
        expect(screen.getByRole("tooltip")).toHaveTextContent("focus me");
    });

    it("closes within 200 ms of pointer leave", () => {
        renderWithProvider(
            <Tooltip text="close me">
                <button>Hi</button>
            </Tooltip>,
        );
        const btn = screen.getByRole("button");
        fireEvent.mouseEnter(btn);
        act(() => { vi.advanceTimersByTime(600); });
        expect(screen.getByRole("tooltip")).toBeInTheDocument();
        fireEvent.mouseLeave(btn);
        act(() => { vi.advanceTimersByTime(199); });
        expect(screen.getByRole("tooltip")).toBeInTheDocument();
        act(() => { vi.advanceTimersByTime(2); });
        expect(screen.queryByRole("tooltip")).toBeNull();
    });

    it("sets aria-describedby when open", () => {
        renderWithProvider(
            <Tooltip text="aria">
                <button>Hi</button>
            </Tooltip>,
        );
        fireEvent.focus(screen.getByRole("button"));
        const btn = screen.getByRole("button");
        expect(btn.getAttribute("aria-describedby")).toBeTruthy();
        fireEvent.blur(btn);
        expect(btn.getAttribute("aria-describedby")).toBeFalsy();
    });
});
