/**
 * Tests for TextOnlyBanner (feature 008-llm-text-only-chat).
 *
 * Covers:
 * - FR-007a: persistent banner mounts when toolsAvailableForUser is false.
 * - FR-005: banner unmounts on the next render that has tools available.
 * - The CTA fires the onOpenAgentSettings callback so the user can
 *   navigate to the agents modal in DashboardLayout.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import TextOnlyBanner from "../TextOnlyBanner";

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

describe("TextOnlyBanner", () => {
    it("renders the banner when toolsAvailableForUser is false (FR-007a)", () => {
        render(
            <TextOnlyBanner
                toolsAvailableForUser={false}
                onOpenAgentSettings={vi.fn()}
            />,
        );
        const banner = screen.getByTestId("text-only-banner");
        expect(banner).toBeTruthy();
        // Copy mentions text-only mode and offers the CTA.
        expect(banner.textContent).toMatch(/text-only mode/i);
        expect(screen.getByTestId("text-only-banner-cta")).toBeTruthy();
    });

    it("does not render the banner when toolsAvailableForUser is true (FR-005)", () => {
        render(
            <TextOnlyBanner
                toolsAvailableForUser={true}
                onOpenAgentSettings={vi.fn()}
            />,
        );
        expect(screen.queryByTestId("text-only-banner")).toBeNull();
    });

    it("unmounts the banner when toolsAvailableForUser flips to true", async () => {
        const { rerender } = render(
            <TextOnlyBanner
                toolsAvailableForUser={false}
                onOpenAgentSettings={vi.fn()}
            />,
        );
        expect(screen.getByTestId("text-only-banner")).toBeTruthy();

        rerender(
            <TextOnlyBanner
                toolsAvailableForUser={true}
                onOpenAgentSettings={vi.fn()}
            />,
        );
        // Framer Motion's exit animation runs through AnimatePresence,
        // so the banner element is briefly retained for the fade-out.
        // Assert it is fully removed once the transition settles —
        // FR-005 requires the banner to disappear on the next turn that
        // has tools, not necessarily on the same render frame.
        await waitFor(() => {
            expect(screen.queryByTestId("text-only-banner")).toBeNull();
        });
    });

    it("fires onOpenAgentSettings when the CTA is clicked (FR-007a)", async () => {
        const onOpen = vi.fn();
        const user = userEvent.setup();
        render(
            <TextOnlyBanner
                toolsAvailableForUser={false}
                onOpenAgentSettings={onOpen}
            />,
        );
        await user.click(screen.getByTestId("text-only-banner-cta"));
        expect(onOpen).toHaveBeenCalledTimes(1);
    });
});
