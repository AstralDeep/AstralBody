/**
 * Feature 013 / US4 — ToolPicker popover behavior.
 *
 * Covers:
 *   - FR-016/FR-017: renders permitted tools as checkboxes with (i) tooltips.
 *   - FR-018: toggling a tool narrows the saved selection.
 *   - FR-019: a `null` selection is rendered as "all checked" (default).
 *   - FR-021: zero-selection warning surfaces inside the picker.
 *   - FR-025: Reset fires the callback.
 *   - Outside-click / Escape closes the popover.
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import ToolPicker from "../../ToolPicker";

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const sampleTools = [
    { name: "search_web", description: "Searches the public web." },
    { name: "send_email", description: "Sends email on the user's behalf." },
    { name: "ping" },
];

const renderPicker = (overrides: Partial<React.ComponentProps<typeof ToolPicker>> = {}) => {
    const props: React.ComponentProps<typeof ToolPicker> = {
        permittedTools: sampleTools,
        selectedTools: null,
        onChange: vi.fn(),
        onReset: vi.fn(),
        open: true,
        onClose: vi.fn(),
        ...overrides,
    };
    const utils = render(<ToolPicker {...props} />);
    return { ...utils, props };
};

describe("ToolPicker — closed state", () => {
    it("renders nothing when `open` is false", () => {
        renderPicker({ open: false });
        expect(screen.queryByTestId("tool-picker-popover")).toBeNull();
    });
});

describe("ToolPicker — default (no narrowing) state", () => {
    it("renders every permitted tool with description and (i) icon when applicable", () => {
        renderPicker({ selectedTools: null });
        expect(screen.getByTestId("tool-picker-popover")).toBeTruthy();
        expect(screen.getByTestId("tool-picker-list")).toBeTruthy();
        expect(screen.getByTestId("tool-picker-item-search_web")).toBeTruthy();
        expect(screen.getByTestId("tool-picker-item-send_email")).toBeTruthy();
        expect(screen.getByTestId("tool-picker-item-ping")).toBeTruthy();
        // Tools with descriptions surface the (i) tooltip; ping has none.
        expect(screen.getByTestId("tool-picker-info-search_web")).toBeTruthy();
        expect(screen.queryByTestId("tool-picker-info-ping")).toBeNull();
    });

    it("treats null selection as 'all checked' (FR-019 default)", () => {
        renderPicker({ selectedTools: null });
        const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
        expect(checkboxes.length).toBe(3);
        checkboxes.forEach(cb => expect(cb.checked).toBe(true));
    });
});

describe("ToolPicker — toggling materializes the selection (FR-018)", () => {
    it("first toggle off from null materializes 'all except this one'", () => {
        const onChange = vi.fn();
        renderPicker({ selectedTools: null, onChange });
        // Click the label of search_web (the visible part — sr-only checkbox is keyboard-only).
        fireEvent.click(screen.getByTestId("tool-picker-item-search_web"));
        expect(onChange).toHaveBeenCalledWith(["send_email", "ping"]);
    });

    it("toggling a tool out of an explicit selection narrows the array", () => {
        const onChange = vi.fn();
        renderPicker({ selectedTools: ["search_web", "send_email"], onChange });
        fireEvent.click(screen.getByTestId("tool-picker-item-send_email"));
        expect(onChange).toHaveBeenCalledWith(["search_web"]);
    });

    it("toggling a tool back in adds it to the explicit selection", () => {
        const onChange = vi.fn();
        renderPicker({ selectedTools: ["search_web"], onChange });
        fireEvent.click(screen.getByTestId("tool-picker-item-send_email"));
        expect(onChange).toHaveBeenCalledWith(["search_web", "send_email"]);
    });
});

describe("ToolPicker — zero-selection warning (FR-021)", () => {
    it("surfaces an in-popover warning when the explicit selection is empty", () => {
        renderPicker({ selectedTools: [] });
        expect(screen.getByTestId("tool-picker-zero-warning")).toBeTruthy();
    });

    it("does NOT surface the zero warning when selection is null (default)", () => {
        renderPicker({ selectedTools: null });
        expect(screen.queryByTestId("tool-picker-zero-warning")).toBeNull();
    });
});

describe("ToolPicker — reset (FR-025)", () => {
    it("fires onReset when the user clicks Reset", () => {
        const onReset = vi.fn();
        renderPicker({ selectedTools: ["search_web"], onReset });
        fireEvent.click(screen.getByTestId("tool-picker-reset"));
        expect(onReset).toHaveBeenCalledTimes(1);
    });
});

describe("ToolPicker — outside click / Escape closes the popover", () => {
    it("clicking outside the popover fires onClose", () => {
        const onClose = vi.fn();
        renderPicker({ onClose });
        fireEvent.mouseDown(document.body);
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("pressing Escape fires onClose", () => {
        const onClose = vi.fn();
        renderPicker({ onClose });
        fireEvent.keyDown(document, { key: "Escape" });
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("clicking inside the popover does NOT fire onClose", () => {
        const onClose = vi.fn();
        renderPicker({ onClose });
        fireEvent.mouseDown(screen.getByTestId("tool-picker-popover"));
        expect(onClose).not.toHaveBeenCalled();
    });
});

describe("ToolPicker — empty agent (no tools)", () => {
    it("renders an empty-state message when permittedTools is empty", () => {
        renderPicker({ permittedTools: [] });
        expect(screen.queryByTestId("tool-picker-list")).toBeNull();
        expect(screen.getByTestId("tool-picker-popover").textContent).toMatch(/no tools available/i);
    });
});

describe("ToolPicker — Agents section (Feature 013 follow-up)", () => {
    const sampleAgents = [
        { id: "agent-a", name: "Grants Helper", disabled: false },
        { id: "agent-b", name: "Email Bot", disabled: true },
    ];

    it("renders the Agents section when agents are passed", () => {
        renderPicker({ agents: sampleAgents });
        expect(screen.getByTestId("tool-picker-agents-section")).toBeTruthy();
        expect(screen.getByTestId("tool-picker-agent-agent-a")).toBeTruthy();
        expect(screen.getByTestId("tool-picker-agent-agent-b")).toBeTruthy();
    });

    it("omits the Agents section when no agents are passed", () => {
        renderPicker(); // default has no agents
        expect(screen.queryByTestId("tool-picker-agents-section")).toBeNull();
    });

    it("reflects the agent's enabled state via aria-checked", () => {
        renderPicker({ agents: sampleAgents });
        const enabledBtn = screen.getByTestId("tool-picker-agent-agent-a");
        const disabledBtn = screen.getByTestId("tool-picker-agent-agent-b");
        expect(enabledBtn.getAttribute("aria-checked")).toBe("true");
        expect(disabledBtn.getAttribute("aria-checked")).toBe("false");
    });

    it("calls onAgentToggle with the inverted state on click", () => {
        const onAgentToggle = vi.fn();
        renderPicker({ agents: sampleAgents, onAgentToggle });
        // agent-a is currently enabled — clicking should request disable.
        fireEvent.click(screen.getByTestId("tool-picker-agent-agent-a"));
        expect(onAgentToggle).toHaveBeenCalledWith("agent-a", false);
        // agent-b is currently disabled — clicking should request enable.
        fireEvent.click(screen.getByTestId("tool-picker-agent-agent-b"));
        expect(onAgentToggle).toHaveBeenCalledWith("agent-b", true);
    });

    it("shows the all-agents-disabled hint when no tools are available because all agents are off", () => {
        renderPicker({
            agents: [{ id: "agent-a", name: "Grants Helper", disabled: true }],
            permittedTools: [],
        });
        expect(screen.getByTestId("tool-picker-popover").textContent)
            .toMatch(/all agents are disabled/i);
    });
});
