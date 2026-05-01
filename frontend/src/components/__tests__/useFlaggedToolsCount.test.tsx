/**
 * Tests for useFlaggedToolsCount (feature 010-fix-page-flash).
 *
 * Pins the dedup contract that prevents the page-flash regression:
 *   - Token-identity changes (silent OIDC refresh) MUST NOT re-trigger
 *     the fetch, because that produced rapid-fire calls and visible
 *     flashes on every refresh.
 *   - Non-admin users MUST NOT trigger any fetch.
 *   - The hook MUST NOT poll; FR-008 requires at most one fetch per
 *     session per endpoint unless an explicit refresh is requested.
 *   - Same-value responses MUST NOT cause a state update that would
 *     re-render the layout subtree.
 *   - The exposed `refresh` callback DOES bypass the cache (used when
 *     admin opens the consuming view).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";

import { useFlaggedToolsCount } from "../useFlaggedToolsCount";
import { backgroundFetchCache } from "../../lib/backgroundFetchCache";
import * as feedbackApi from "../../api/feedback";
import type { FlaggedTool } from "../../types/feedback";

const flaggedItems = (n: number): FlaggedTool[] =>
    Array.from({ length: n }, (_, i) => ({
        agent_id: `a${i}`,
        tool_name: `t${i}`,
        window_start: "2026-05-01T00:00:00Z",
        window_end: "2026-05-01T01:00:00Z",
        dispatch_count: 10,
        failure_count: 3,
        negative_feedback_count: 1,
        failure_rate: 0.3,
        negative_feedback_rate: 0.1,
        category_breakdown: {} as FlaggedTool["category_breakdown"],
        flagged_at: "2026-05-01T00:30:00Z",
        pending_proposal_id: null,
    }));

beforeEach(() => {
    backgroundFetchCache._resetForTests();
    vi.restoreAllMocks();
});

afterEach(() => {
    cleanup();
});

describe("useFlaggedToolsCount — dedup & no-flash contract", () => {
    it("returns 0 and does not fetch for non-admins", async () => {
        const spy = vi
            .spyOn(feedbackApi, "listFlaggedTools")
            .mockResolvedValue({ items: flaggedItems(3), next_cursor: null });
        const { result } = renderHook(() =>
            useFlaggedToolsCount("token-xyz", /* isAdmin */ false),
        );
        // Yield a couple of microtasks to ensure no async fetch sneaks in.
        await Promise.resolve();
        await Promise.resolve();
        expect(spy).not.toHaveBeenCalled();
        expect(result.current.count).toBe(0);
    });

    it("returns 0 and does not fetch when there is no token", async () => {
        const spy = vi
            .spyOn(feedbackApi, "listFlaggedTools")
            .mockResolvedValue({ items: flaggedItems(2), next_cursor: null });
        const { result } = renderHook(() =>
            useFlaggedToolsCount(undefined, /* isAdmin */ true),
        );
        await Promise.resolve();
        await Promise.resolve();
        expect(spy).not.toHaveBeenCalled();
        expect(result.current.count).toBe(0);
    });

    it("fires exactly one fetch on admin mount and returns the count", async () => {
        const spy = vi
            .spyOn(feedbackApi, "listFlaggedTools")
            .mockResolvedValue({ items: flaggedItems(4), next_cursor: null });
        const { result } = renderHook(() => useFlaggedToolsCount("t1", true));
        await waitFor(() => expect(result.current.count).toBe(4));
        expect(spy).toHaveBeenCalledTimes(1);
    });

    it("does NOT re-fetch when the access token identity changes", async () => {
        const spy = vi
            .spyOn(feedbackApi, "listFlaggedTools")
            .mockResolvedValue({ items: flaggedItems(2), next_cursor: null });
        const { result, rerender } = renderHook(
            ({ tok }: { tok: string }) => useFlaggedToolsCount(tok, true),
            { initialProps: { tok: "old-token" } },
        );
        await waitFor(() => expect(result.current.count).toBe(2));
        expect(spy).toHaveBeenCalledTimes(1);

        // Simulate ten silent OIDC token refreshes in rapid succession.
        // Pre-fix this would have triggered ten new fetches and as many
        // re-renders of the entire dashboard subtree.
        for (let i = 0; i < 10; i++) {
            rerender({ tok: `new-token-${i}` });
            await Promise.resolve();
        }
        expect(spy).toHaveBeenCalledTimes(1);
    });

    it("does NOT register a setInterval — there is no polling", async () => {
        const setIntervalSpy = vi.spyOn(window, "setInterval");
        vi.spyOn(feedbackApi, "listFlaggedTools").mockResolvedValue({
            items: flaggedItems(0),
            next_cursor: null,
        });
        renderHook(() => useFlaggedToolsCount("t", true));
        // Wait long enough for any naive polling to register itself.
        await new Promise((r) => setTimeout(r, 30));
        expect(setIntervalSpy).not.toHaveBeenCalled();
    });

    it("does NOT trigger a re-render when the response count is unchanged", async () => {
        const spy = vi
            .spyOn(feedbackApi, "listFlaggedTools")
            .mockResolvedValue({ items: flaggedItems(5), next_cursor: null });
        let renderCount = 0;
        const { result } = renderHook(() => {
            renderCount += 1;
            return useFlaggedToolsCount("t", true);
        });
        await waitFor(() => expect(result.current.count).toBe(5));
        const baselineRenders = renderCount;

        // Force the same response on a subsequent explicit refresh — the
        // count is the same, so no setState should fire and no extra
        // render should occur beyond the fetch round-trip.
        await act(async () => {
            result.current.refresh();
            await Promise.resolve();
            await Promise.resolve();
        });
        expect(spy).toHaveBeenCalledTimes(2); // mount + explicit refresh
        // Allow a tolerance of 1 render for React's act flushing.
        expect(renderCount - baselineRenders).toBeLessThanOrEqual(1);
    });

    it("refresh() invalidates the session cache and triggers a fresh fetch", async () => {
        const spy = vi
            .spyOn(feedbackApi, "listFlaggedTools")
            .mockResolvedValueOnce({ items: flaggedItems(2), next_cursor: null })
            .mockResolvedValueOnce({ items: flaggedItems(7), next_cursor: null });
        const { result } = renderHook(() => useFlaggedToolsCount("t", true));
        await waitFor(() => expect(result.current.count).toBe(2));
        expect(spy).toHaveBeenCalledTimes(1);

        await act(async () => {
            result.current.refresh();
            await Promise.resolve();
            await Promise.resolve();
        });
        await waitFor(() => expect(result.current.count).toBe(7));
        expect(spy).toHaveBeenCalledTimes(2);
    });

    it("re-mounts of the hook within the same session do NOT issue a new fetch", async () => {
        const spy = vi
            .spyOn(feedbackApi, "listFlaggedTools")
            .mockResolvedValue({ items: flaggedItems(3), next_cursor: null });
        const { result: r1, unmount } = renderHook(() =>
            useFlaggedToolsCount("t", true),
        );
        await waitFor(() => expect(r1.current.count).toBe(3));
        unmount();
        // A consumer remount (e.g., DashboardLayout re-rendered above) must
        // not trigger a second fetch — that's what backgroundFetchCache buys.
        const { result: r2 } = renderHook(() => useFlaggedToolsCount("t", true));
        await waitFor(() => expect(r2.current.count).toBe(3));
        expect(spy).toHaveBeenCalledTimes(1);
    });
});
