/**
 * OnboardingContext — orchestrates the tutorial state machine for the user.
 *
 * Responsibilities:
 *   - Decide whether to auto-launch the tutorial on first sign-in
 *     (state.status === "not_started", per FR-001).
 *   - Resume the user at the correct step on browser reload (FR-013).
 *   - Drive next/back/skip/complete transitions and persist them
 *     through the backend.
 *   - Expose `replay()` (FR-005) — launches the overlay at step 1
 *     without mutating persisted state (research.md Decision 8).
 *
 * The context does NOT render the overlay — it only owns the state.
 * The overlay (`TutorialOverlay`) reads `useOnboarding()` and renders.
 */
import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";

import { useOnboardingState } from "./useOnboardingState";
import { useTutorialSteps } from "./useTutorialSteps";
import type { OnboardingState, TutorialStep } from "./types";

interface OnboardingContextValue {
    /** Persisted server-side state for the user. */
    state: OnboardingState;
    /** All steps the caller can see (filtered by role on the backend). */
    steps: TutorialStep[];
    /** Step currently rendered, or null when the overlay is hidden. */
    currentStep: TutorialStep | null;
    /**
     * Target key of the currently-rendered step, or null when the overlay
     * is hidden / the active step has no target. Mirrors `currentStep`
     * but exposed as a primitive so consumers (notably the feature 007
     * SettingsMenu) can react to "the tutorial is now pointing at X"
     * without needing the whole step object. Equivalent to
     * `currentStep?.target_key ?? null` — see feature 007 research.md
     * § Decision 3.
     */
    currentStepTargetKey: string | null;
    /** True while the overlay should be visible. */
    visible: boolean;
    loading: boolean;
    next: () => Promise<void>;
    back: () => void;
    skip: () => Promise<void>;
    complete: () => Promise<void>;
    /** Open the overlay at step 1 without mutating persisted state. */
    replay: () => Promise<void>;
    /** Hide the overlay without recording a state change (used by Escape). */
    dismiss: () => void;
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

interface OnboardingProviderProps {
    accessToken: string | null | undefined;
    children: React.ReactNode;
}

export function OnboardingProvider({
    accessToken,
    children,
}: OnboardingProviderProps) {
    const onboardingState = useOnboardingState(accessToken);
    const { state, update, replay: replayApi, refresh: refreshState } = onboardingState;

    const [activated, setActivated] = useState<boolean>(false);
    const stepsResource = useTutorialSteps(accessToken, activated);
    const { steps } = stepsResource;

    const [visible, setVisible] = useState<boolean>(false);
    const [stepIndex, setStepIndex] = useState<number>(0);
    /** Replay mode short-circuits state mutations until dismiss. */
    const [replayMode, setReplayMode] = useState<boolean>(false);
    const autoLaunchedRef = useRef<boolean>(false);

    // ----------------------------------------------------------------------
    // Auto-launch on first sign-in: status==="not_started" + steps loaded
    // ----------------------------------------------------------------------
    useEffect(() => {
        if (autoLaunchedRef.current) return;
        if (onboardingState.loading) return;
        if (!accessToken) return;
        if (state.status === "not_started") {
            autoLaunchedRef.current = true;
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setActivated(true);
        }
    }, [state.status, onboardingState.loading, accessToken]);

    // ----------------------------------------------------------------------
    // Resume-on-reload: when status==="in_progress", show overlay at the
    // first step whose display_order >= the persisted last_step_id's order.
    // ----------------------------------------------------------------------
    useEffect(() => {
        if (autoLaunchedRef.current) return;
        if (onboardingState.loading) return;
        if (!accessToken) return;
        if (state.status === "in_progress" && steps.length > 0) {
            autoLaunchedRef.current = true;
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setActivated(true);
        }
    }, [state.status, onboardingState.loading, accessToken, steps.length]);

    // ----------------------------------------------------------------------
    // Once steps load and we're activated, become visible & resolve index.
    // Only triggers during initial auto-launch / replay; never re-launches
    // after a terminal transition (`completed` / `skipped`).
    // ----------------------------------------------------------------------
    const initialLaunchDoneRef = useRef<boolean>(false);
    useEffect(() => {
        if (initialLaunchDoneRef.current) return;
        if (!activated) return;
        if (steps.length === 0) return;
        if (visible) return;
        // After a terminal status, never auto-show. Replay mode bypasses
        // this since `replay()` activates explicitly.
        if (!replayMode && (state.status === "completed" || state.status === "skipped")) {
            return;
        }
        let idx = 0;
        if (!replayMode && state.last_step_id != null) {
            const found = steps.findIndex((s) => s.id === state.last_step_id);
            if (found >= 0) {
                idx = found;
            } else {
                idx = 0;
            }
        }
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setStepIndex(idx);
        setVisible(true);
        initialLaunchDoneRef.current = true;
    }, [activated, steps, visible, state.last_step_id, state.status, replayMode]);

    // When `replay()` runs, allow the launcher to fire again on the next pass.
    useEffect(() => {
        if (replayMode) {
            initialLaunchDoneRef.current = false;
        }
    }, [replayMode]);

    const currentStep = useMemo<TutorialStep | null>(() => {
        if (!visible) return null;
        if (steps.length === 0) return null;
        return steps[Math.max(0, Math.min(stepIndex, steps.length - 1))] ?? null;
    }, [visible, steps, stepIndex]);

    // ----------------------------------------------------------------------
    // State transitions
    // ----------------------------------------------------------------------

    const ensureInProgress = useCallback(
        async (lastStepId: number | null) => {
            if (replayMode) return; // replay must not mutate persisted state
            if (state.status === "in_progress") return;
            if (state.status === "completed" || state.status === "skipped") return;
            await update({ status: "in_progress", last_step_id: lastStepId });
        },
        [replayMode, state.status, update],
    );

    const next = useCallback(async () => {
        if (!visible || steps.length === 0) return;
        const cur = steps[stepIndex];
        if (!cur) return;
        if (stepIndex < steps.length - 1) {
            const nextStep = steps[stepIndex + 1];
            setStepIndex((i) => i + 1);
            if (!replayMode) {
                await ensureInProgress(nextStep.id);
                await update({ status: "in_progress", last_step_id: nextStep.id });
            }
            return;
        }
        // On the last step — advance flips us to "completed".
        if (replayMode) {
            setVisible(false);
            setReplayMode(false);
            return;
        }
        await update({ status: "completed", last_step_id: cur.id });
        setVisible(false);
    }, [visible, steps, stepIndex, replayMode, ensureInProgress, update]);

    const back = useCallback(() => {
        if (stepIndex <= 0) return;
        setStepIndex((i) => Math.max(0, i - 1));
    }, [stepIndex]);

    const skip = useCallback(async () => {
        const cur = steps[stepIndex] ?? null;
        if (replayMode) {
            setVisible(false);
            setReplayMode(false);
            return;
        }
        await update({
            status: "skipped",
            last_step_id: cur?.id ?? state.last_step_id ?? null,
        });
        setVisible(false);
    }, [replayMode, steps, stepIndex, state.last_step_id, update]);

    const complete = useCallback(async () => {
        const cur = steps[stepIndex] ?? null;
        if (replayMode) {
            setVisible(false);
            setReplayMode(false);
            return;
        }
        await update({
            status: "completed",
            last_step_id: cur?.id ?? state.last_step_id ?? null,
        });
        setVisible(false);
    }, [replayMode, steps, stepIndex, state.last_step_id, update]);

    const replay = useCallback(async () => {
        await replayApi();
        setReplayMode(true);
        setActivated(true);
        setStepIndex(0);
        setVisible(true);
    }, [replayApi]);

    const dismiss = useCallback(() => {
        setVisible(false);
        if (replayMode) setReplayMode(false);
    }, [replayMode]);

    // Refresh state when the access token first arrives or changes
    useEffect(() => {
        if (accessToken) {
            void refreshState();
        }
    }, [accessToken, refreshState]);

    const currentStepTargetKey = useMemo<string | null>(
        () => (visible ? currentStep?.target_key ?? null : null),
        [visible, currentStep],
    );

    const value = useMemo<OnboardingContextValue>(
        () => ({
            state,
            steps,
            currentStep,
            currentStepTargetKey,
            visible,
            loading: onboardingState.loading,
            next,
            back,
            skip,
            complete,
            replay,
            dismiss,
        }),
        [state, steps, currentStep, currentStepTargetKey, visible, onboardingState.loading, next, back, skip, complete, replay, dismiss],
    );

    return (
        <OnboardingContext.Provider value={value}>
            {children}
        </OnboardingContext.Provider>
    );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useOnboarding(): OnboardingContextValue {
    const ctx = useContext(OnboardingContext);
    if (!ctx) {
        throw new Error("useOnboarding must be used within an OnboardingProvider");
    }
    return ctx;
}
