/**
 * Tests for SettingsMenu (feature 007-sidebar-settings-menu).
 *
 * Covers FRs: 001 (single trigger + grouped menu), 002 (reachable everywhere),
 * 003-005 (groups: Account / Help / Admin tools), 006 (admin-gated visibility),
 * 007 (item activates same callback as original button), 008 (dismissal),
 * 010 (tutorial auto-open/auto-close), 012 (full WAI-ARIA menu pattern),
 * 014 (callback omission + empty-group rule).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock useOnboarding so SettingsMenu's tutorial-integration effect can be
// driven from tests without spinning up the full onboarding fetch stack.
vi.mock("../../onboarding/OnboardingContext", () => ({
    useOnboarding: vi.fn(),
}));

import { SettingsMenu, type SettingsMenuProps } from "../SettingsMenu";
import { useOnboarding } from "../../onboarding/OnboardingContext";

const mockedUseOnboarding = vi.mocked(useOnboarding);

function setOnboarding(targetKey: string | null) {
    mockedUseOnboarding.mockReturnValue({
        currentStepTargetKey: targetKey,
        // The real type has many more fields; SettingsMenu only reads
        // currentStepTargetKey. The cast keeps the test ergonomic.
    } as unknown as ReturnType<typeof useOnboarding>);
}

function renderMenu(overrides: Partial<SettingsMenuProps> = {}) {
    const props: SettingsMenuProps = {
        onOpenAuditLog: vi.fn(),
        onOpenLlmSettings: vi.fn(),
        onOpenFeedbackAdmin: vi.fn(),
        onOpenTutorialAdmin: vi.fn(),
        onReplayTutorial: vi.fn(),
        onOpenUserGuide: vi.fn(),
        isAdmin: true,
        ...overrides,
    };
    const utils = render(<SettingsMenu {...props} />);
    return { ...utils, props };
}

beforeEach(() => {
    setOnboarding(null);
});

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// T005 — render & activate
// ---------------------------------------------------------------------------
describe("SettingsMenu — render & activate (T005)", () => {
    it("renders the trigger with WAI-ARIA menu attributes", () => {
        renderMenu();
        const trigger = screen.getByRole("button", { name: /settings/i });
        expect(trigger.getAttribute("aria-haspopup")).toBe("menu");
        expect(trigger.getAttribute("aria-expanded")).toBe("false");
    });

    it("clicking the trigger opens the menu and lists six items", async () => {
        const user = userEvent.setup();
        renderMenu();
        const trigger = screen.getByRole("button", { name: /settings/i });
        await user.click(trigger);
        expect(trigger.getAttribute("aria-expanded")).toBe("true");
        expect(screen.getByRole("menu")).toBeTruthy();
        const items = screen.getAllByRole("menuitem");
        expect(items).toHaveLength(6);
        const labels = items.map((el) => el.textContent?.trim());
        expect(labels).toEqual(
            expect.arrayContaining([
                "Audit log",
                "LLM settings",
                "Take the tour",
                "User guide",
                "Tool quality",
                "Tutorial admin",
            ]),
        );
    });

    it("clicking a menu item invokes its callback once and closes the menu", async () => {
        const user = userEvent.setup();
        const { props } = renderMenu();
        await user.click(screen.getByRole("button", { name: /settings/i }));
        await user.click(screen.getByRole("menuitem", { name: /audit log/i }));
        expect(props.onOpenAuditLog).toHaveBeenCalledTimes(1);
        expect(props.onOpenLlmSettings).not.toHaveBeenCalled();
        expect(screen.queryByRole("menu")).toBeNull();
        expect(
            screen.getByRole("button", { name: /settings/i }).getAttribute("aria-expanded"),
        ).toBe("false");
    });
});

// ---------------------------------------------------------------------------
// T006 — dismissal & keyboard
// ---------------------------------------------------------------------------
describe("SettingsMenu — dismissal & keyboard (T006)", () => {
    it("clicking outside the popover closes it without invoking any callback", async () => {
        const user = userEvent.setup();
        const { container, props } = renderMenu();
        const outside = document.createElement("button");
        outside.textContent = "outside";
        container.parentElement!.appendChild(outside);
        await user.click(screen.getByRole("button", { name: /settings/i }));
        expect(screen.getByRole("menu")).toBeTruthy();
        await user.click(outside);
        expect(screen.queryByRole("menu")).toBeNull();
        expect(props.onOpenAuditLog).not.toHaveBeenCalled();
    });

    it("Escape closes the menu and returns focus to the trigger", async () => {
        const user = userEvent.setup();
        renderMenu();
        const trigger = screen.getByRole("button", { name: /settings/i });
        await user.click(trigger);
        expect(screen.getByRole("menu")).toBeTruthy();
        await user.keyboard("{Escape}");
        expect(screen.queryByRole("menu")).toBeNull();
        expect(document.activeElement).toBe(trigger);
    });

    it("opens with Enter and focuses the first item", async () => {
        const user = userEvent.setup();
        renderMenu();
        const trigger = screen.getByRole("button", { name: /settings/i });
        trigger.focus();
        await user.keyboard("{Enter}");
        const items = screen.getAllByRole("menuitem");
        expect(items.length).toBeGreaterThan(0);
        expect(document.activeElement).toBe(items[0]);
    });

    it("opens with Space and focuses the first item", async () => {
        const user = userEvent.setup();
        renderMenu();
        const trigger = screen.getByRole("button", { name: /settings/i });
        trigger.focus();
        await user.keyboard(" ");
        const items = screen.getAllByRole("menuitem");
        expect(document.activeElement).toBe(items[0]);
    });

    it("Arrow keys move focus between items with wrap-around", async () => {
        const user = userEvent.setup();
        renderMenu();
        const trigger = screen.getByRole("button", { name: /settings/i });
        trigger.focus();
        await user.keyboard("{Enter}");
        const items = screen.getAllByRole("menuitem");
        expect(document.activeElement).toBe(items[0]);
        await user.keyboard("{ArrowDown}");
        expect(document.activeElement).toBe(items[1]);
        await user.keyboard("{ArrowUp}");
        expect(document.activeElement).toBe(items[0]);
        // wrap from first → last
        await user.keyboard("{ArrowUp}");
        expect(document.activeElement).toBe(items[items.length - 1]);
        // wrap from last → first
        await user.keyboard("{ArrowDown}");
        expect(document.activeElement).toBe(items[0]);
    });

    it("Home / End jump to first / last item", async () => {
        const user = userEvent.setup();
        renderMenu();
        const trigger = screen.getByRole("button", { name: /settings/i });
        trigger.focus();
        await user.keyboard("{Enter}");
        const items = screen.getAllByRole("menuitem");
        await user.keyboard("{End}");
        expect(document.activeElement).toBe(items[items.length - 1]);
        await user.keyboard("{Home}");
        expect(document.activeElement).toBe(items[0]);
    });

    it("Tab cycles within menu items (focus trap)", async () => {
        const user = userEvent.setup();
        renderMenu();
        const trigger = screen.getByRole("button", { name: /settings/i });
        trigger.focus();
        await user.keyboard("{Enter}");
        const items = screen.getAllByRole("menuitem");
        // Tab acts like ArrowDown — moves focus to next item, traps at end
        await user.keyboard("{Tab}");
        expect(document.activeElement).toBe(items[1]);
        // Shift+Tab acts like ArrowUp
        await user.keyboard("{Shift>}{Tab}{/Shift}");
        expect(document.activeElement).toBe(items[0]);
    });

    it("Enter on a focused item activates that item's callback", async () => {
        const user = userEvent.setup();
        const { props } = renderMenu();
        const trigger = screen.getByRole("button", { name: /settings/i });
        trigger.focus();
        await user.keyboard("{Enter}");
        const items = screen.getAllByRole("menuitem");
        // Focused on items[0] which is Audit log (first user-scope item)
        await user.keyboard("{Enter}");
        expect(props.onOpenAuditLog).toHaveBeenCalledTimes(1);
        expect(screen.queryByRole("menu")).toBeNull();
        // ensure no other callbacks were invoked
        expect(props.onOpenLlmSettings).not.toHaveBeenCalled();
        // Re-open and try Space on the second item
        trigger.focus();
        await user.keyboard("{Enter}");
        await user.keyboard("{ArrowDown}");
        await user.keyboard(" ");
        expect(props.onOpenLlmSettings).toHaveBeenCalledTimes(1);
        expect(items.length).toBeGreaterThan(0); // sanity
    });
});

// ---------------------------------------------------------------------------
// T007 — callback-omission + empty-group hiding (FR-014)
// ---------------------------------------------------------------------------
describe("SettingsMenu — callback omission (T007)", () => {
    it("omits the menuitem when its callback is undefined", async () => {
        const user = userEvent.setup();
        renderMenu({ onOpenAuditLog: undefined });
        await user.click(screen.getByRole("button", { name: /settings/i }));
        expect(screen.queryByRole("menuitem", { name: /audit log/i })).toBeNull();
        // Other items still render
        expect(screen.getByRole("menuitem", { name: /llm settings/i })).toBeTruthy();
    });

    it("hides a group entirely when every callback in that group is undefined", async () => {
        const user = userEvent.setup();
        renderMenu({
            onOpenAuditLog: undefined,
            onOpenLlmSettings: undefined,
        });
        await user.click(screen.getByRole("button", { name: /settings/i }));
        // No Account heading should appear (heading hidden when group empty).
        expect(screen.queryByText(/^account$/i)).toBeNull();
        // Audit log + LLM settings absent.
        expect(screen.queryByRole("menuitem", { name: /audit log/i })).toBeNull();
        expect(screen.queryByRole("menuitem", { name: /llm settings/i })).toBeNull();
        // Help section still renders.
        expect(screen.getByRole("menuitem", { name: /take the tour/i })).toBeTruthy();
        expect(screen.getByRole("menuitem", { name: /user guide/i })).toBeTruthy();
    });
});

// ---------------------------------------------------------------------------
// T016 / T017 — admin gating (FR-005, FR-006, SC-003) + admin-empty-section
// ---------------------------------------------------------------------------
describe("SettingsMenu — admin gating (T016)", () => {
    it("renders Admin tools section with both items when isAdmin=true", async () => {
        const user = userEvent.setup();
        renderMenu({ isAdmin: true });
        await user.click(screen.getByRole("button", { name: /settings/i }));
        // Heading rendered
        expect(screen.getByText(/^admin tools$/i)).toBeTruthy();
        // Both admin items rendered
        expect(screen.getByRole("menuitem", { name: /tool quality/i })).toBeTruthy();
        expect(screen.getByRole("menuitem", { name: /tutorial admin/i })).toBeTruthy();
    });

    it("omits the Admin tools section heading and items entirely when isAdmin=false", async () => {
        const user = userEvent.setup();
        renderMenu({ isAdmin: false });
        await user.click(screen.getByRole("button", { name: /settings/i }));
        // Heading absent
        expect(screen.queryByText(/^admin tools$/i)).toBeNull();
        // Both admin items absent
        expect(screen.queryByRole("menuitem", { name: /tool quality/i })).toBeNull();
        expect(screen.queryByRole("menuitem", { name: /tutorial admin/i })).toBeNull();
        // Other groups still render
        expect(screen.getByRole("menuitem", { name: /audit log/i })).toBeTruthy();
        expect(screen.getByRole("menuitem", { name: /take the tour/i })).toBeTruthy();
    });
});

describe("SettingsMenu — admin empty section (T017)", () => {
    it("hides the Admin tools heading when isAdmin=true but both admin callbacks are undefined", async () => {
        const user = userEvent.setup();
        renderMenu({
            isAdmin: true,
            onOpenFeedbackAdmin: undefined,
            onOpenTutorialAdmin: undefined,
        });
        await user.click(screen.getByRole("button", { name: /settings/i }));
        expect(screen.queryByText(/^admin tools$/i)).toBeNull();
        expect(screen.queryByRole("menuitem", { name: /tool quality/i })).toBeNull();
        expect(screen.queryByRole("menuitem", { name: /tutorial admin/i })).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// T020 — section headings (FR-003, FR-004, FR-005)
// ---------------------------------------------------------------------------
describe("SettingsMenu — section headings (T020)", () => {
    it("renders Account, Help, and Admin tools headings in that order with all items", async () => {
        const user = userEvent.setup();
        renderMenu({ isAdmin: true });
        await user.click(screen.getByRole("button", { name: /settings/i }));
        const menu = screen.getByRole("menu");
        const groups = menu.querySelectorAll('[role="group"]');
        expect(groups.length).toBe(3);
        // Each group has aria-labelledby pointing to a label whose text
        // matches one of the section names. Walk the groups in DOM order
        // and assert the heading text sequence is Account → Help → Admin tools.
        const labels: string[] = [];
        groups.forEach((g) => {
            const id = g.getAttribute("aria-labelledby");
            if (id) {
                const labelEl = menu.querySelector(`#${CSS.escape(id)}`);
                if (labelEl) labels.push(labelEl.textContent?.trim() ?? "");
            }
        });
        expect(labels).toEqual(["Account", "Help", "Admin tools"]);
    });

    it("each heading is associated with its menu items via aria-labelledby", async () => {
        const user = userEvent.setup();
        renderMenu({ isAdmin: true });
        await user.click(screen.getByRole("button", { name: /settings/i }));
        const menu = screen.getByRole("menu");
        const groups = menu.querySelectorAll('[role="group"]');
        groups.forEach((g) => {
            const id = g.getAttribute("aria-labelledby");
            expect(id).toBeTruthy();
            // The id resolves to a non-empty label inside the menu.
            expect(menu.querySelector(`#${CSS.escape(id!)}`)?.textContent?.trim().length).toBeGreaterThan(0);
            // Each group has at least one menuitem child.
            expect(g.querySelectorAll('[role="menuitem"]').length).toBeGreaterThan(0);
        });
    });
});

// ---------------------------------------------------------------------------
// Flagged-tools badge — preserves the affordance from feature 004
// ---------------------------------------------------------------------------
describe("SettingsMenu — flagged-tools badge", () => {
    it("renders a badge on the Tool quality item when flaggedToolsCount > 0", async () => {
        const user = userEvent.setup();
        renderMenu({ isAdmin: true, flaggedToolsCount: 3 });
        await user.click(screen.getByRole("button", { name: /settings/i }));
        const toolQuality = screen.getByRole("menuitem", { name: /tool quality/i });
        expect(toolQuality.textContent).toMatch(/3 flagged/);
    });

    it("caps the badge at '99+' for counts above 99", async () => {
        const user = userEvent.setup();
        renderMenu({ isAdmin: true, flaggedToolsCount: 250 });
        await user.click(screen.getByRole("button", { name: /settings/i }));
        const toolQuality = screen.getByRole("menuitem", { name: /tool quality/i });
        expect(toolQuality.textContent).toMatch(/99\+ flagged/);
    });

    it("omits the badge when flaggedToolsCount is 0 or undefined", async () => {
        const user = userEvent.setup();
        renderMenu({ isAdmin: true, flaggedToolsCount: 0 });
        await user.click(screen.getByRole("button", { name: /settings/i }));
        const toolQuality = screen.getByRole("menuitem", { name: /tool quality/i });
        expect(toolQuality.textContent).not.toMatch(/flagged/);
    });

    it("never renders the badge for non-admins (item itself is hidden)", async () => {
        const user = userEvent.setup();
        renderMenu({ isAdmin: false, flaggedToolsCount: 5 });
        await user.click(screen.getByRole("button", { name: /settings/i }));
        expect(screen.queryByRole("menuitem", { name: /tool quality/i })).toBeNull();
        expect(screen.queryByText(/flagged/i)).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// Accessibility polish — aria-orientation
// ---------------------------------------------------------------------------
describe("SettingsMenu — a11y polish", () => {
    it("declares aria-orientation=vertical on the menu container", async () => {
        const user = userEvent.setup();
        renderMenu();
        await user.click(screen.getByRole("button", { name: /settings/i }));
        const menu = screen.getByRole("menu");
        expect(menu.getAttribute("aria-orientation")).toBe("vertical");
    });
});

// ---------------------------------------------------------------------------
// Collapsed variant (icon rail) — FR-002 viewport coverage
// ---------------------------------------------------------------------------
describe("SettingsMenu — collapsed variant", () => {
    it("renders an icon-only trigger with a tooltip when variant=collapsed", async () => {
        const user = userEvent.setup();
        renderMenu({ variant: "collapsed" });
        const trigger = screen.getByRole("button", { name: /settings/i });
        // Collapsed trigger uses the `title` attribute for the tooltip
        // and renders no visible label text.
        expect(trigger.getAttribute("title")).toBe("Settings");
        expect(trigger.textContent?.trim()).toBe("");
        await user.click(trigger);
        // Popover still works the same way as expanded variant.
        expect(screen.getByRole("menu")).toBeTruthy();
        const items = screen.getAllByRole("menuitem");
        expect(items.length).toBeGreaterThan(0);
    });
});

// ---------------------------------------------------------------------------
// T008 — tutorial auto-open / auto-close (FR-010)
// ---------------------------------------------------------------------------
describe("SettingsMenu — tutorial integration (T008)", () => {
    it("auto-opens when currentStepTargetKey matches a menu item key", () => {
        setOnboarding("sidebar.audit");
        renderMenu();
        expect(screen.queryByRole("menu")).toBeTruthy();
        expect(
            screen.getByRole("button", { name: /settings/i }).getAttribute("aria-expanded"),
        ).toBe("true");
    });

    it("auto-closes when currentStepTargetKey transitions to an off-menu key", () => {
        setOnboarding("sidebar.audit");
        const { rerender } = renderMenu();
        expect(screen.queryByRole("menu")).toBeTruthy();
        // Transition to an off-menu target (e.g., Agents button)
        setOnboarding("sidebar.agents");
        act(() => {
            rerender(
                <SettingsMenu
                    isAdmin
                    onOpenAuditLog={vi.fn()}
                    onOpenLlmSettings={vi.fn()}
                    onOpenFeedbackAdmin={vi.fn()}
                    onOpenTutorialAdmin={vi.fn()}
                    onReplayTutorial={vi.fn()}
                    onOpenUserGuide={vi.fn()}
                />,
            );
        });
        expect(screen.queryByRole("menu")).toBeNull();
    });

    it("auto-closes when currentStepTargetKey transitions to null", () => {
        setOnboarding("sidebar.user-guide");
        const { rerender } = renderMenu();
        expect(screen.queryByRole("menu")).toBeTruthy();
        setOnboarding(null);
        act(() => {
            rerender(
                <SettingsMenu
                    isAdmin
                    onOpenAuditLog={vi.fn()}
                    onOpenLlmSettings={vi.fn()}
                    onOpenFeedbackAdmin={vi.fn()}
                    onOpenTutorialAdmin={vi.fn()}
                    onReplayTutorial={vi.fn()}
                    onOpenUserGuide={vi.fn()}
                />,
            );
        });
        expect(screen.queryByRole("menu")).toBeNull();
    });
});
