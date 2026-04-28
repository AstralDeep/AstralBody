/**
 * Tooltip — accessible hover/focus tooltip wrapper.
 *
 * Behavior matrix:
 *   - `text` is null/empty/whitespace      → render `children` as-is. No
 *                                            tooltip frame is created (FR-008).
 *   - Pointer hover                        → 500 ms open delay, 200 ms close.
 *   - Keyboard focus / focus-visible       → opens immediately.
 *   - Escape (handled by TooltipProvider)  → closes immediately.
 *   - Touch device                         → opens on long-press (500 ms),
 *                                            closes on next tap.
 *
 * Implementation notes:
 *   - Cloned children get `aria-describedby={id}` for screen-reader linking
 *     when the tooltip is visible.
 *   - Uses CSS to position relative to the wrapper element so we don't have
 *     to portal — keeps the markup simple and matches the dashboard's
 *     existing tooltip-less hover affordances.
 */
import {
    Children,
    cloneElement,
    isValidElement,
    useCallback,
    useEffect,
    useId,
    useRef,
    useState,
} from "react";

import { useTooltipController } from "./TooltipProvider";

const HOVER_OPEN_DELAY_MS = 500;
const HOVER_CLOSE_DELAY_MS = 200;
const LONG_PRESS_MS = 500;

export type TooltipPlacement = "top" | "bottom" | "left" | "right";

export interface TooltipProps {
    text?: string | null;
    placement?: TooltipPlacement;
    children: React.ReactNode;
    /** Disables the tooltip without unmounting. */
    disabled?: boolean;
}

function isEmpty(text: string | null | undefined): boolean {
    return !text || !text.trim();
}

function placementClasses(placement: TooltipPlacement): string {
    switch (placement) {
        case "bottom":
            return "top-full mt-1.5 left-1/2 -translate-x-1/2";
        case "left":
            return "right-full mr-1.5 top-1/2 -translate-y-1/2";
        case "right":
            return "left-full ml-1.5 top-1/2 -translate-y-1/2";
        case "top":
        default:
            return "bottom-full mb-1.5 left-1/2 -translate-x-1/2";
    }
}

export function Tooltip({
    text,
    placement = "top",
    children,
    disabled = false,
}: TooltipProps) {
    const tipId = useId();
    const { activeId, setActive, isTouch } = useTooltipController();
    const [open, setOpen] = useState(false);
    const openTimerRef = useRef<number | null>(null);
    const closeTimerRef = useRef<number | null>(null);
    const longPressTimerRef = useRef<number | null>(null);

    // Cooperative "only one tooltip open" — close ourselves if another wins.
    useEffect(() => {
        if (open && activeId !== null && activeId !== tipId) {
            setOpen(false);
        }
        if (!open && activeId === tipId) {
            // Provider says we're the active one; ensure we render.
            setOpen(true);
        }
    }, [open, activeId, tipId]);

    const clearTimers = useCallback(() => {
        if (openTimerRef.current != null) {
            window.clearTimeout(openTimerRef.current);
            openTimerRef.current = null;
        }
        if (closeTimerRef.current != null) {
            window.clearTimeout(closeTimerRef.current);
            closeTimerRef.current = null;
        }
        if (longPressTimerRef.current != null) {
            window.clearTimeout(longPressTimerRef.current);
            longPressTimerRef.current = null;
        }
    }, []);

    useEffect(() => () => clearTimers(), [clearTimers]);

    const tooltipDisabled = disabled || isEmpty(text);

    // ----- Pointer (mouse) handlers -----
    const handlePointerEnter = useCallback(() => {
        if (tooltipDisabled || isTouch) return;
        if (closeTimerRef.current != null) {
            window.clearTimeout(closeTimerRef.current);
            closeTimerRef.current = null;
        }
        if (open) return;
        openTimerRef.current = window.setTimeout(() => {
            setOpen(true);
            setActive(tipId);
        }, HOVER_OPEN_DELAY_MS);
    }, [tooltipDisabled, isTouch, open, setActive, tipId]);

    const handlePointerLeave = useCallback(() => {
        if (tooltipDisabled) return;
        if (openTimerRef.current != null) {
            window.clearTimeout(openTimerRef.current);
            openTimerRef.current = null;
        }
        closeTimerRef.current = window.setTimeout(() => {
            setOpen(false);
            setActive(null);
        }, HOVER_CLOSE_DELAY_MS);
    }, [tooltipDisabled, setActive]);

    // ----- Keyboard focus handlers -----
    const handleFocus = useCallback(() => {
        if (tooltipDisabled) return;
        clearTimers();
        setOpen(true);
        setActive(tipId);
    }, [tooltipDisabled, clearTimers, setActive, tipId]);

    const handleBlur = useCallback(() => {
        if (tooltipDisabled) return;
        clearTimers();
        setOpen(false);
        setActive(null);
    }, [tooltipDisabled, clearTimers, setActive]);

    // ----- Touch handlers (long-press) -----
    const handleTouchStart = useCallback(() => {
        if (tooltipDisabled || !isTouch) return;
        clearTimers();
        longPressTimerRef.current = window.setTimeout(() => {
            setOpen(true);
            setActive(tipId);
        }, LONG_PRESS_MS);
    }, [tooltipDisabled, isTouch, clearTimers, setActive, tipId]);

    const handleTouchEnd = useCallback(() => {
        if (tooltipDisabled || !isTouch) return;
        if (longPressTimerRef.current != null) {
            window.clearTimeout(longPressTimerRef.current);
            longPressTimerRef.current = null;
        }
    }, [tooltipDisabled, isTouch]);

    if (tooltipDisabled) {
        return <>{children}</>;
    }

    // We clone the focusable child so aria-describedby lands on the element
    // that actually receives keyboard focus (which is what screen readers
    // need). The eslint react-hooks/refs rule is over-conservative here:
    // we are not reading any ref's `.current` during render — `cloneElement`
    // simply forwards a possibly-present ref through to the same DOM node
    // it would have rendered to anyway.
    const onlyChild = Children.toArray(children).find((c) => isValidElement(c));
    if (!isValidElement(onlyChild)) {
        return <>{children}</>;
    }
    const childProps: Record<string, unknown> = {
        onMouseEnter: handlePointerEnter,
        onMouseLeave: handlePointerLeave,
        onFocus: handleFocus,
        onBlur: handleBlur,
        onTouchStart: handleTouchStart,
        onTouchEnd: handleTouchEnd,
    };
    if (open) {
        childProps["aria-describedby"] = tipId;
    }
    // eslint-disable-next-line react-hooks/refs
    const cloned = cloneElement(onlyChild, childProps);

    return (
        <span className="relative inline-flex" data-tooltip-host>
            {cloned}
            {open && !isEmpty(text) && (
                <span
                    role="tooltip"
                    id={tipId}
                    className={`absolute z-[10001] pointer-events-none
                                whitespace-pre-line text-[11px] leading-snug
                                bg-astral-bg/95 border border-white/10 text-white
                                rounded-md shadow-xl px-2.5 py-1.5 max-w-[260px]
                                ${placementClasses(placement)}`}
                >
                    {text}
                </span>
            )}
        </span>
    );
}
