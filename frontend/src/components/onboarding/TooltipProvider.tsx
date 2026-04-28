/**
 * TooltipProvider — single-source coordinator for all `Tooltip` instances.
 *
 * Owns:
 *   - The currently-visible tooltip id (so only one is open at a time).
 *   - The Escape key listener (closes the active tooltip).
 *   - Touch-device detection (passes a hint down to `Tooltip` instances
 *     so they swap hover for long-press).
 *
 * `Tooltip` calls `register/unregister` on mount; `setActive(id)` on
 * hover/focus; `setActive(null)` on dismiss. The provider re-broadcasts
 * the active id so other tooltips can hide themselves cooperatively.
 */
import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
} from "react";

interface TooltipContextValue {
    activeId: string | null;
    setActive: (id: string | null) => void;
    isTouch: boolean;
}

const TooltipContext = createContext<TooltipContextValue | null>(null);

function detectTouch(): boolean {
    if (typeof window === "undefined") return false;
    const win = window as unknown as { matchMedia?: (q: string) => MediaQueryList };
    if (typeof win.matchMedia === "function") {
        try {
            const mq = win.matchMedia("(hover: none) and (pointer: coarse)");
            if (mq && typeof mq.matches === "boolean") return mq.matches;
        } catch {
            /* ignore */
        }
    }
    if ("ontouchstart" in window) return true;
    const nav = (navigator as unknown as { maxTouchPoints?: number });
    return (nav.maxTouchPoints ?? 0) > 0;
}

export function TooltipProvider({ children }: { children: React.ReactNode }) {
    const [activeId, setActiveId] = useState<string | null>(null);
    const [isTouch, setIsTouch] = useState<boolean>(() => detectTouch());

    // Re-detect on resize / device-orientation changes
    useEffect(() => {
        if (typeof window === "undefined") return;
        const refresh = () => setIsTouch(detectTouch());
        window.addEventListener("resize", refresh);
        return () => window.removeEventListener("resize", refresh);
    }, []);

    // Single Escape listener that closes whichever tooltip is open
    useEffect(() => {
        if (!activeId) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                setActiveId(null);
            }
        };
        document.addEventListener("keydown", onKey, true);
        return () => document.removeEventListener("keydown", onKey, true);
    }, [activeId]);

    const setActive = useCallback((id: string | null) => {
        setActiveId(id);
    }, []);

    const value = useMemo<TooltipContextValue>(
        () => ({ activeId, setActive, isTouch }),
        [activeId, setActive, isTouch],
    );

    return (
        <TooltipContext.Provider value={value}>{children}</TooltipContext.Provider>
    );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTooltipController(): TooltipContextValue {
    const ctx = useContext(TooltipContext);
    if (!ctx) {
        // Soft fallback — tooltips are still functional without the provider,
        // but multi-tooltip coordination is local.
        return { activeId: null, setActive: () => {}, isTouch: detectTouch() };
    }
    return ctx;
}
