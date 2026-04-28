/**
 * TutorialStep — renders the title/body/controls of a single tutorial step.
 *
 * Pure presentational; the parent overlay handles positioning, focus
 * trapping, and ARIA wiring. Buttons are big, keyboard-friendly, and use
 * the dashboard's existing color tokens.
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
    titleId,
    bodyId,
}: TutorialStepProps) {
    const isFinal = stepNumber === totalSteps;
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
            <div className="flex items-center justify-between gap-3">
                <button
                    type="button"
                    onClick={onSkip}
                    className="text-xs text-astral-muted hover:text-white transition-colors"
                >
                    Skip tour
                </button>
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
                        {isFinal ? "Done" : "Next"}
                        {!isFinal && <ChevronRight size={14} />}
                    </button>
                </div>
            </div>
        </div>
    );
}
