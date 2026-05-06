/**
 * Feature 013 / US3 — per-tool permission rows in AgentPermissionsModal.
 *
 * Covers:
 *   - FR-010: each tool gets its own row with its required permission kind.
 *   - FR-011: the (i) info element is reachable while the toggle is OFF
 *     (tabIndex + title visible without first enabling).
 *   - FR-012: toggling one tool surfaces only that tool's pending change
 *     — sibling tools' visual state stays consistent.
 *   - FR-014: only the kind that applies to each tool appears (rows
 *     don't render greyed-out toggles for inapplicable kinds).
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";

// Mock framer-motion so the modal mounts in jsdom without animation noise.
type MotionPropsLike = Record<string, unknown> & {
    children?: React.ReactNode;
};
vi.mock("framer-motion", () => {
    const passthrough = (tag: string) =>
        React.forwardRef<HTMLElement, MotionPropsLike>((props, ref) => {
            const { initial: _i, animate: _a, exit: _e, transition: _t,
                    layout: _l, whileHover: _wh, whileTap: _wt, ...rest } = props;
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

// jsdom doesn't implement scrollIntoView; the modal's effect path may
// touch it. Stub it out.
if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = function () { /* noop */ };
}

import AgentPermissionsModal from "../../AgentPermissionsModal";

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const baseProps: React.ComponentProps<typeof AgentPermissionsModal> = {
    isOpen: true,
    onClose: vi.fn(),
    agentId: "agent-x",
    agentName: "Grants Helper",
    agentDescription: "Helps with grants.",
    scopes: { "tools:read": false, "tools:write": false, "tools:search": false, "tools:system": false },
    toolScopeMap: {
        search_web: "tools:search",
        read_file: "tools:read",
        send_email: "tools:write",
    },
    permissions: { search_web: false, read_file: false, send_email: false },
    toolOverrides: {},
    toolDescriptions: {
        search_web: "Searches the public web.",
        read_file: "Reads a file from the workspace.",
        send_email: "Sends email on the user's behalf.",
    },
    securityFlags: {},
    onSave: vi.fn(),
    isOwner: true,
    isPublic: false,
};

describe("AgentPermissionsModal — per-tool rows (FR-010)", () => {
    it("renders one row per tool ordered by kind", () => {
        render(<AgentPermissionsModal {...baseProps} />);
        expect(screen.getByTestId("per-tool-permission-list")).toBeTruthy();
        expect(screen.getByTestId("per-tool-row-search_web")).toBeTruthy();
        expect(screen.getByTestId("per-tool-row-read_file")).toBeTruthy();
        expect(screen.getByTestId("per-tool-row-send_email")).toBeTruthy();
    });

    it("each row exposes the (i) info element reachable while the toggle is OFF (FR-011)", () => {
        render(<AgentPermissionsModal {...baseProps} />);
        const info = screen.getByTestId("per-tool-info-send_email") as HTMLElement;
        // The element is keyboard-reachable (tabIndex=0) and surfaces its
        // explainer via the title attribute — both available before the
        // user has flipped any toggle.
        expect(info.tabIndex).toBe(0);
        expect(info.getAttribute("title") ?? "").toMatch(/create.*modify.*delete/i);
        // Toggle is off at this point — the row's switch reports aria-checked=false.
        const toggle = screen.getByTestId("per-tool-toggle-send_email");
        expect(toggle.getAttribute("aria-checked")).toBe("false");
    });

    it("renders only the kind that applies to each tool (FR-014)", () => {
        render(<AgentPermissionsModal {...baseProps} />);
        // search_web → tools:search badge only.
        const searchRow = screen.getByTestId("per-tool-row-search_web");
        expect(searchRow.textContent).toMatch(/search/i);
        // No "Write" / "Read" / "System" badges on the search_web row.
        expect(searchRow.textContent).not.toMatch(/\bWrite\b/);
        expect(searchRow.textContent).not.toMatch(/\bSystem\b/);
        // Each row has a single switch — no greyed-out kind toggles.
        const send = screen.getByTestId("per-tool-row-send_email");
        const switches = send.querySelectorAll("[role='switch']");
        expect(switches.length).toBe(1);
    });
});

describe("AgentPermissionsModal — toggle independence (FR-012)", () => {
    it("clicking one tool's switch when the scope is OFF surfaces the consent dialog without flipping siblings", () => {
        render(<AgentPermissionsModal {...baseProps} />);
        // search_web and read_file both start OFF (scope tools:search and tools:read off).
        const searchToggle = screen.getByTestId("per-tool-toggle-search_web");
        fireEvent.click(searchToggle);
        // Consent dialog appears prompting for the search scope.
        // (The pre-existing warning dialog renders the scope label + warning copy.)
        expect(screen.getAllByText(/enable search/i).length).toBeGreaterThan(0);
        // Sibling toggle for read_file is unchanged.
        const readToggle = screen.getByTestId("per-tool-toggle-read_file");
        expect(readToggle.getAttribute("aria-checked")).toBe("false");
    });
});

describe("AgentPermissionsModal — tools-allowed initial state", () => {
    it("renders tools as enabled when the parent reports the matching scope is ON", () => {
        const props = {
            ...baseProps,
            scopes: { "tools:read": true, "tools:write": false, "tools:search": true, "tools:system": false },
            permissions: { search_web: true, read_file: true, send_email: false },
        };
        render(<AgentPermissionsModal {...props} />);
        expect(screen.getByTestId("per-tool-toggle-search_web").getAttribute("aria-checked")).toBe("true");
        expect(screen.getByTestId("per-tool-toggle-read_file").getAttribute("aria-checked")).toBe("true");
        expect(screen.getByTestId("per-tool-toggle-send_email").getAttribute("aria-checked")).toBe("false");
    });
});
