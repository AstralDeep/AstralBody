/**
 * TutorialStep — renders the title/body/controls of a single tutorial step.
 *
 * Pure presentational; the parent overlay handles positioning, focus
 * trapping, and ARIA wiring.
 *
 * US-17: Added thin progress bar at the bottom, and "Not now" button
 * on the welcome (first) step for soft dismissal.
 */
import { ChevronLeft, ChevronRight, X } from "lucide-react";

import type { TutorialStep as TutorialStepType } from "./types";

export interface TutorialStepProps {
    step: TutorialStepType;
    stepNumber: number;
    totalSteps: number;
    canGoBack: boolean;
    onNext: () => void;
    onBack: () => void;
    onSkip: () => void;
    onDismissNotNow?: () => void;
    titleId: string;
    bodyId: string;
}

export function TutorialStep({
    step,
    stepNumber,
    totalSteps,
    canGoBack,
    onNext,
    onBack,
    onSkip,
    onDismissNotNow,
    titleId,
    bodyId,
}: TutorialStepProps) {
    const isFinal = stepNumber === totalSteps;
    const isFirst = stepNumber === 1;
    const progressPct = totalSteps > 0 ? (stepNumber / totalSteps) * 100 : 0;

    return (
        <div
            className="bg-astral-bg border border-white/10 rounded-xl shadow-2xl
                       p-6 max-w-md w-full text-white"
        >
            <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex-1">
                    <p className="text-[10px] uppercase tracking-widest text-astral-muted mb-1">
                        Step {stepNumber} of {totalSteps}
                    </p>
                    <h2 id={titleId} className="text-lg font-semibold leading-snug">
                        {step.title}
                    </h2>
                </div>
                <button
                    type="button"
                    onClick={onSkip}
                    aria-label="Skip tour"
                    className="text-astral-muted hover:text-white p-1 rounded-md
                               hover:bg-white/5 transition-colors"
                >
                    <X size={16} />
                </button>
            </div>
            <p
                id={bodyId}
                className="text-sm text-astral-muted leading-relaxed mb-5 whitespace-pre-line"
            >
                {step.body}
            </p>
            {/* Progress bar */}
            <div className="mb-4 h-1 bg-white/10 rounded-full overflow-hidden">
                <div
                    className="h-full bg-astral-primary rounded-full transition-all duration-300 ease-out"
                    style={{ width: `${progressPct}%` }}
                />
            </div>
            <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                    {isFirst && onDismissNotNow && (
                        <button
                            type="button"
                            onClick={onDismissNotNow}
                            className="text-xs text-astral-muted hover:text-white
                                       transition-colors px-2 py-1 rounded-md
                                       hover:bg-white/5"
                        >
                            Not now
                        </button>
                    )}
                    {!isFirst && (
                        <button
                            type="button"
                            onClick={onSkip}
                            className="text-xs text-astral-muted hover:text-white transition-colors"
                        >
                            Skip tour
                        </button>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <button
                        type="button"
                        onClick={onBack}
                        disabled={!canGoBack}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs
                                   bg-white/5 hover:bg-white/10 transition-colors
                                   disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                        <ChevronLeft size={14} />
                        Back
                    </button>
                    <button
                        type="button"
                        onClick={onNext}
                        autoFocus
                        className="flex items-center gap-1 px-4 py-1.5 rounded-lg text-xs
                                   bg-astral-primary hover:bg-astral-primary/90
                                   text-white font-medium transition-colors"
                    >
                        {isFirst ? "Start tour" : isFinal ? "Done" : "Next"}
                        {!isFinal && <ChevronRight size={14} />}
                    </button>
                </div>
            </div>
        </div>
    );
}
