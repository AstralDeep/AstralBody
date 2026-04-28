/**
 * React hook for the user's onboarding state (feature 005).
 *
 * Wraps the three user-side endpoints (GET / PUT / POST replay).
 * The hook is intentionally low-level — it does not manage UI state;
 * `OnboardingContext` composes it with the step list and exposes the
 * higher-level `next/back/skip/complete/replay` actions.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { API_URL } from "../../config";
import type { OnboardingState, OnboardingStatus } from "./types";

const NOT_STARTED: OnboardingState = {
    status: "not_started",
    last_step_id: null,
    last_step_slug: null,
    started_at: null,
    completed_at: null,
    skipped_at: null,
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

    const refresh = useCallback(async () => {
        if (!tokenRef.current) return;
        setLoading(true);
        setError(null);
        try {
            const r = await fetch(`${API_URL}/api/onboarding/state`, {
                headers: buildHeaders(),
            });
            if (!r.ok) {
                throw new Error(`onboarding/state ${r.status}`);
            }
            const body = (await r.json()) as OnboardingState;
            setState(body);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setLoading(false);
        }
    }, [buildHeaders]);

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

    useEffect(() => {
        if (accessToken) {
            void refresh();
        }
    }, [accessToken, refresh]);

    return { state, loading, error, refresh, update, replay };
}
