/**
 * TutorialOverlay — full-screen dialog that highlights tutorial targets.
 *
 * Behavior:
 *   - Renders nothing when the OnboardingContext says we're not visible.
 *   - On a target with `target_kind="static"`: scrolls the matching
 *     `[data-tutorial-target="…"]` element into view, draws a soft cutout
 *     spotlight around it, and anchors the step card next to it.
 *   - On a target with `target_kind="sdui"`: same behavior, looking up
 *     the element by `data-tutorial-target` (set by DynamicRenderer when
 *     the SDUI component carries an `id`).
 *   - On `target_kind="none"`: centers the step card on screen.
 *   - Escape and the X button call `dismiss()` (no-op transition; matches
 *     the FR-013 / replay design where backstop is a real "skip").
 *   - Hand-rolled focus trap restricts Tab cycling to elements inside
 *     the dialog and restores focus on close (FR-010).
 *   - Reflows reposition the spotlight (`ResizeObserver`).
 */
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";

import { useOnboarding } from "./OnboardingContext";
import { TutorialStep } from "./TutorialStep";

interface Rect {
    top: number;
    left: number;
    width: number;
    height: number;
}

const PADDING = 8;
const CARD_GAP = 12;
const CARD_WIDTH = 448; // matches max-w-md (~28rem)

function findTargetElement(targetKey: string | null): HTMLElement | null {
    if (!targetKey) return null;
    const el = document.querySelector<HTMLElement>(
        `[data-tutorial-target="${CSS.escape(targetKey)}"]`,
    );
    return el ?? null;
}

function getRect(el: HTMLElement | null): Rect | null {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {
        top: r.top - PADDING,
        left: r.left - PADDING,
        width: r.width + PADDING * 2,
        height: r.height + PADDING * 2,
    };
}

function pickCardPosition(rect: Rect | null): React.CSSProperties {
    if (!rect) {
        return {
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
        };
    }
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const cardWidth = Math.min(CARD_WIDTH, vw - 32);

    // Prefer placing the card to the right of the target if there's room,
    // otherwise below, otherwise above.
    const fitsRight = rect.left + rect.width + CARD_GAP + cardWidth + 16 < vw;
    const fitsBelow = rect.top + rect.height + CARD_GAP + 200 < vh;

    if (fitsRight) {
        return {
            top: Math.max(16, Math.min(rect.top, vh - 220)),
            left: rect.left + rect.width + CARD_GAP,
        };
    }
    if (fitsBelow) {
        return {
            top: rect.top + rect.height + CARD_GAP,
            left: Math.max(16, Math.min(rect.left, vw - cardWidth - 16)),
        };
    }
    return {
        top: Math.max(16, rect.top - 220),
        left: Math.max(16, Math.min(rect.left, vw - cardWidth - 16)),
    };
}

export function TutorialOverlay() {
    const onboarding = useOnboarding();
    const { visible, currentStep, steps, next, back, skip } = onboarding;

    const dialogRef = useRef<HTMLDivElement | null>(null);
    const [targetRect, setTargetRect] = useState<Rect | null>(null);
    const previousFocusRef = useRef<HTMLElement | null>(null);
    const titleId = useId();
    const bodyId = useId();

    // Capture and restore focus
    useEffect(() => {
        if (!visible) return;
        previousFocusRef.current = document.activeElement as HTMLElement | null;
        return () => {
            const prev = previousFocusRef.current;
            if (prev && typeof prev.focus === "function") {
                try {
                    prev.focus();
                } catch {
                    /* ignore */
                }
            }
        };
    }, [visible]);

    // Locate target + recompute on layout changes
    useLayoutEffect(() => {
        if (!visible || !currentStep) {
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setTargetRect(null);
            return;
        }
        if (currentStep.target_kind === "none" || !currentStep.target_key) {
            setTargetRect(null);
            return;
        }

        let raf = 0;
        const update = () => {
            const el = findTargetElement(currentStep.target_key);
            if (el && typeof el.scrollIntoView === "function") {
                try {
                    el.scrollIntoView({ block: "center", behavior: "smooth" });
                } catch {
                    /* ignore */
                }
            }
            setTargetRect(getRect(el));
        };
        update();
        const onResize = () => {
            cancelAnimationFrame(raf);
            raf = requestAnimationFrame(update);
        };
        window.addEventListener("resize", onResize);
        window.addEventListener("scroll", onResize, true);
        let observer: ResizeObserver | null = null;
        const targetEl = findTargetElement(currentStep.target_key);
        if (targetEl && typeof ResizeObserver !== "undefined") {
            observer = new ResizeObserver(onResize);
            observer.observe(targetEl);
        }
        return () => {
            window.removeEventListener("resize", onResize);
            window.removeEventListener("scroll", onResize, true);
            if (observer) observer.disconnect();
            cancelAnimationFrame(raf);
        };
    }, [visible, currentStep]);

    // Escape + Tab focus trap
    useEffect(() => {
        if (!visible) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                e.preventDefault();
                void skip();
                return;
            }
            if (e.key !== "Tab") return;
            const root = dialogRef.current;
            if (!root) return;
            const focusables = Array.from(
                root.querySelectorAll<HTMLElement>(
                    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
                ),
            ).filter((el) => !el.hasAttribute("disabled") && el.offsetParent !== null);
            if (focusables.length === 0) return;
            const first = focusables[0];
            const last = focusables[focusables.length - 1];
            const active = document.activeElement as HTMLElement | null;
            if (e.shiftKey) {
                if (active === first || !active || !root.contains(active)) {
                    e.preventDefault();
                    last.focus();
                }
            } else if (active === last) {
                e.preventDefault();
                first.focus();
            }
        };
        document.addEventListener("keydown", onKey);
        return () => document.removeEventListener("keydown", onKey);
    }, [visible, skip]);

    if (!visible || !currentStep) return null;

    const cardStyle = pickCardPosition(targetRect);
    const stepNumber = Math.max(0, steps.findIndex((s) => s.id === currentStep.id)) + 1;

    return (
        <div
            className="fixed inset-0 z-[10000] pointer-events-none"
            aria-hidden={false}
        >
            {/* Backdrop with cutout */}
            <div
                className="absolute inset-0 bg-black/60 pointer-events-auto"
                style={
                    targetRect
                        ? {
                              clipPath: `polygon(
                                0% 0%, 100% 0%, 100% 100%, 0% 100%, 0% 0%,
                                ${targetRect.left}px ${targetRect.top}px,
                                ${targetRect.left}px ${targetRect.top + targetRect.height}px,
                                ${targetRect.left + targetRect.width}px ${targetRect.top + targetRect.height}px,
                                ${targetRect.left + targetRect.width}px ${targetRect.top}px,
                                ${targetRect.left}px ${targetRect.top}px
                            )`,
                          }
                        : undefined
                }
                onClick={() => void skip()}
            />
            {/* Spotlight ring */}
            {targetRect && (
                <div
                    className="absolute pointer-events-none border-2 border-astral-primary/80
                               rounded-lg shadow-[0_0_0_3px_rgba(139,92,246,0.25)]"
                    style={{
                        top: targetRect.top,
                        left: targetRect.left,
                        width: targetRect.width,
                        height: targetRect.height,
                        transition: "all 200ms ease-out",
                    }}
                />
            )}
            {/* Step card */}
            <div
                ref={dialogRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                aria-describedby={bodyId}
                className="absolute pointer-events-auto"
                style={{
                    width: `min(${CARD_WIDTH}px, calc(100vw - 32px))`,
                    ...cardStyle,
                }}
            >
                <TutorialStep
                    step={currentStep}
                    stepNumber={stepNumber}
                    totalSteps={steps.length}
                    canGoBack={stepNumber > 1}
                    onNext={() => void next()}
                    onBack={back}
                    onSkip={() => void skip()}
                    titleId={titleId}
                    bodyId={bodyId}
                />
            </div>
        </div>
    );
}
