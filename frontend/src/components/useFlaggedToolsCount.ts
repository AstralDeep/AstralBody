/**
 * useFlaggedToolsCount — admin-only flagged-tools badge data source.
 *
 * Returns the count of flagged tools to surface as a badge on the
 * "Tool quality" item inside <SettingsMenu>. Returns 0 for non-admins
 * and unauthenticated users.
 *
 * Feature 010-fix-page-flash: this hook USED TO poll
 * `/api/admin/feedback/quality/flagged?limit=100` every 60s from the
 * globally mounted dashboard shell, with the OIDC access token on its
 * useEffect dep array. Each silent token refresh tore down and
 * recreated the interval, fired an immediate fetch, and re-rendered
 * the entire dashboard subtree — visibly flashing the screen on every
 * page load and on every chat switch / new query that happened to
 * coincide with a refresh. Now:
 *   - The fetch is wrapped in `backgroundFetchCache` so a given
 *     session issues at most one request to this endpoint
 *     (FR-004 / FR-008) unless explicitly refreshed.
 *   - There is no `setInterval`. The badge picks up fresh data when
 *     the consuming view (FeedbackAdminPanel) is opened — see the
 *     `refresh` callback returned by this hook — which counts as an
 *     "explicit user action" per the spec.
 *   - The token is held in a ref so identity-only changes during
 *     silent refresh do not retrigger anything.
 *
 * Server-side authz remains the source of truth: non-admin requests
 * reject server-side and we tolerate the failure silently here.
 *
 * Lives in its own module (not co-located in DashboardLayout.tsx) so
 * tests can exercise it via `renderHook` without pulling DashboardLayout's
 * full render tree (which transitively imports plotly and breaks jsdom).
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { listFlaggedTools } from "../api/feedback";
import { backgroundFetchCache } from "../lib/backgroundFetchCache";

const FLAGGED_TOOLS_CACHE_KEY = "admin-feedback-flagged?limit=100";

export interface UseFlaggedToolsCountResult {
    count: number;
    /**
     * Invalidate the session cache for the flagged-tools endpoint and
     * issue a fresh fetch. Intended for use on explicit user actions —
     * e.g., when the admin opens the consuming FeedbackAdminPanel — so
     * the badge reflects current backend state on close. Does nothing
     * for non-admin / unauthenticated callers.
     */
    refresh: () => void;
}

export function useFlaggedToolsCount(
    token: string | undefined,
    isAdmin: boolean,
): UseFlaggedToolsCountResult {
    const [count, setCount] = useState(0);
    // Hold the token in a ref so identity-only changes (silent OIDC
    // refresh) do NOT change the `load` callback's identity. The ref
    // is written inside an effect (not during render) per the
    // react-hooks/refs rule; effects flush before the load effect
    // below runs in the same commit.
    const tokenRef = useRef(token);
    useEffect(() => {
        tokenRef.current = token;
    }, [token]);
    const lastCountRef = useRef(0);
    const mountedRef = useRef(true);
    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
        };
    }, []);

    const load = useCallback(
        async (forceRefresh: boolean) => {
            const tok = tokenRef.current;
            if (!tok || !isAdmin) return;
            try {
                const r = await backgroundFetchCache.getOrFetch(
                    FLAGGED_TOOLS_CACHE_KEY,
                    () => listFlaggedTools(tok, { limit: 100 }),
                    forceRefresh ? { refresh: true } : undefined,
                );
                if (!mountedRef.current) return;
                const newCount = r.items.length;
                // Only update state when the count actually changes — a
                // no-op setCount still re-renders the subtree, which when
                // combined with framer-motion layout animations produces
                // visible flashes.
                if (newCount !== lastCountRef.current) {
                    lastCountRef.current = newCount;
                    setCount(newCount);
                }
            } catch {
                /* ignore — server-side authz is the source of truth */
            }
        },
        [isAdmin],
    );

    useEffect(() => {
        if (!isAdmin) return;
        // Fire one cache-backed read on mount / first time the user is an
        // admin. Subsequent renders hit the cache and do nothing.
        void load(false);
    }, [isAdmin, load]);

    const refresh = useCallback(() => {
        backgroundFetchCache.invalidate(FLAGGED_TOOLS_CACHE_KEY);
        void load(true);
    }, [load]);

    return {
        count: token && isAdmin ? count : 0,
        refresh,
    };
}
