/**
 * React hook that loads the user-applicable tutorial step list.
 *
 * Fetched fresh on every activation so admin edits propagate without a
 * frontend redeploy (FR-016 / research.md Decision 9).
 */
import { useCallback, useEffect, useState } from "react";

import { API_URL } from "../../config";
import type { TutorialStep } from "./types";

export interface UseTutorialStepsResult {
    steps: TutorialStep[];
    loading: boolean;
    error: string | null;
    refresh: () => Promise<void>;
}

export function useTutorialSteps(
    accessToken: string | null | undefined,
    activated: boolean,
): UseTutorialStepsResult {
    const [steps, setSteps] = useState<TutorialStep[]>([]);
    const [loading, setLoading] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        if (!accessToken) return;
        setLoading(true);
        setError(null);
        try {
            const r = await fetch(`${API_URL}/api/tutorial/steps`, {
                headers: { Authorization: `Bearer ${accessToken}` },
            });
            if (!r.ok) {
                throw new Error(`tutorial/steps ${r.status}`);
            }
            const body = (await r.json()) as { steps: TutorialStep[] };
            setSteps(Array.isArray(body.steps) ? body.steps : []);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
            setSteps([]);
        } finally {
            setLoading(false);
        }
    }, [accessToken]);

    useEffect(() => {
        if (activated && accessToken) {
            void refresh();
        }
    }, [activated, accessToken, refresh]);

    return { steps, loading, error, refresh };
}
