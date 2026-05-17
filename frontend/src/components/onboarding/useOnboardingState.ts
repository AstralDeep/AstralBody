/**
 * React hook for the user's onboarding state (feature 005).
 *
 * Wraps the three user-side endpoints (GET / PUT / POST replay).
 * The hook is intentionally low-level — it does not manage UI state;
 * `OnboardingContext` composes it with the step list and exposes the
 * higher-level `next/back/skip/complete/replay` actions.
 *
 * Feature 010-fix-page-flash: this hook is consumed by
 * `OnboardingProvider`, which is mounted at the root of the
 * authenticated shell. Previously its initial-load `useEffect`
 * depended on `accessToken` directly, so every silent OIDC token
 * refresh re-fired `refresh()`, ran setLoading(true)/setState(...)
 * through React Context, and re-rendered the entire app subtree —
 * a primary cause of the visible screen flash. The fix:
 *   - Hold `accessToken` in a ref so identity changes never re-fire
 *     the effect.
 *   - Trigger the initial fetch the first time a non-empty token is
 *     observed (gate via `firstLoadDoneRef`); subsequent silent
 *     refreshes are no-ops.
 *   - Route the GET through `backgroundFetchCache` so concurrent
 *     callers and re-mounts share a single in-flight promise and
 *     subsequent reads return the cached value (FR-004 / FR-008).
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { API_URL } from "../../config";
import { backgroundFetchCache } from "../../lib/backgroundFetchCache";
import type { OnboardingState, OnboardingStatus } from "./types";

const ONBOARDING_STATE_CACHE_KEY = "onboarding-state";

const NOT_STARTED: OnboardingState = {
    status: "not_started",
    last_step_id: null,
    last_step_slug: null,
    started_at: null,
    completed_at: null,
    skipped_at: null,
    dismissed_at: null,
    dismiss_count: 0,
};

interface UpdatePayload {
    status: Exclude<OnboardingStatus, "not_started">;
    last_step_id?: number | null;
}

export interface UseOnboardingStateResult {
    state: OnboardingState;
    loading: boolean;
    error: string | null;
    refresh: () => Promise<void>;
    update: (p: UpdatePayload) => Promise<OnboardingState | null>;
    replay: () => Promise<void>;
    dismiss: () => Promise<OnboardingState | null>;
}

export function useOnboardingState(
    accessToken: string | null | undefined,
): UseOnboardingStateResult {
    const [state, setState] = useState<OnboardingState>(NOT_STARTED);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const tokenRef = useRef(accessToken);
    tokenRef.current = accessToken;

    const buildHeaders = useCallback((): Record<string, string> => {
        const headers: Record<string, string> = {
            "Content-Type": "application/json",
        };
        if (tokenRef.current) {
            headers["Authorization"] = `Bearer ${tokenRef.current}`;
        }
        return headers;
    }, []);

    const fetchOnboardingState = useCallback(async (): Promise<OnboardingState> => {
        const r = await fetch(`${API_URL}/api/onboarding/state`, {
            headers: buildHeaders(),
        });
        if (!r.ok) {
            throw new Error(`onboarding/state ${r.status}`);
        }
        return (await r.json()) as OnboardingState;
    }, [buildHeaders]);

    const refresh = useCallback(async () => {
        if (!tokenRef.current) return;
        setLoading(true);
        setError(null);
        try {
            // Force-refresh via the session cache: this is called from
            // the explicit-action paths (post-mutation, replay, etc.)
            // where we want fresh data, not the cached value.
            const body = await backgroundFetchCache.getOrFetch(
                ONBOARDING_STATE_CACHE_KEY,
                fetchOnboardingState,
                { refresh: true },
            );
            setState(body);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setLoading(false);
        }
    }, [fetchOnboardingState]);

    const update = useCallback(
        async (p: UpdatePayload): Promise<OnboardingState | null> => {
            if (!tokenRef.current) return null;
            try {
                const r = await fetch(`${API_URL}/api/onboarding/state`, {
                    method: "PUT",
                    headers: buildHeaders(),
                    body: JSON.stringify({
                        status: p.status,
                        last_step_id: p.last_step_id ?? null,
                    }),
                });
                if (!r.ok) {
                    throw new Error(`onboarding/state PUT ${r.status}`);
                }
                const body = (await r.json()) as OnboardingState;
                // Mutation: replace the cache so the next consumer reads
                // the fresh value rather than a now-stale GET.
                backgroundFetchCache.invalidate(ONBOARDING_STATE_CACHE_KEY);
                setState(body);
                return body;
            } catch (e) {
                setError(e instanceof Error ? e.message : String(e));
                return null;
            }
        },
        [buildHeaders],
    );

    const replay = useCallback(async () => {
        if (!tokenRef.current) return;
        try {
            await fetch(`${API_URL}/api/onboarding/replay`, {
                method: "POST",
                headers: buildHeaders(),
            });
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
    }, [buildHeaders]);

    const dismiss = useCallback(async (): Promise<OnboardingState | null> => {
        if (!tokenRef.current) return null;
        try {
            const r = await fetch(`${API_URL}/api/onboarding/dismiss`, {
                method: "POST",
                headers: buildHeaders(),
            });
            if (!r.ok) {
                throw new Error(`onboarding/dismiss POST ${r.status}`);
            }
            const body = (await r.json()) as OnboardingState;
            backgroundFetchCache.invalidate(ONBOARDING_STATE_CACHE_KEY);
            setState(body);
            return body;
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
            return null;
        }
    }, [buildHeaders]);

    // Initial-load gate: fire exactly once when we first observe a
    // non-empty access token. Subsequent silent OIDC refreshes change
    // the token identity but do NOT re-trigger the fetch. The cache
    // ensures any concurrent caller (e.g., the duplicate effect that
    // used to live in OnboardingContext) shares the same in-flight
    // promise rather than firing a second request.
    const firstLoadDoneRef = useRef(false);
    useEffect(() => {
        if (firstLoadDoneRef.current) return;
        if (!accessToken) return;
        firstLoadDoneRef.current = true;
        let cancelled = false;
        void (async () => {
            setLoading(true);
            setError(null);
            try {
                const body = await backgroundFetchCache.getOrFetch(
                    ONBOARDING_STATE_CACHE_KEY,
                    fetchOnboardingState,
                );
                if (!cancelled) setState(body);
            } catch (e) {
                if (!cancelled) {
                    setError(e instanceof Error ? e.message : String(e));
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => {
            cancelled = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [accessToken]);

    return { state, loading, error, refresh, update, replay, dismiss };
}
