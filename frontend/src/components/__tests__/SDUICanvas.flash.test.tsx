/**
 * Tests for SDUICanvas's mount-set / streaming-reconciliation behavior
 * (feature 010-fix-page-flash, FR-006).
 *
 * Pins the contract that:
 *   - Components present at first paint receive `initial={false}` so
 *     they do not animate in (eliminates the page-load flash on
 *     historical chat reload).
 *   - Components added *after* first paint receive the entry-animation
 *     `initial` object so streaming additions animate as intended.
 *   - Existing components keep `initial={false}` even after new ones
 *     are streamed in — they MUST NOT remount or re-key.
 *
 * Strategy: replace framer-motion with a passthrough that exposes the
 * `initial` prop as a `data-initial` attribute we can read in the DOM.
 * This avoids pulling plotly into the test bundle and keeps the test
 * focused on the prop-shape contract that prevents the flash.
 */
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Mocks — keep this set tight so the SDUICanvas import surface stays small.
// ---------------------------------------------------------------------------
type MotionPropsLike = Record<string, unknown> & {
    initial?: unknown;
    children?: React.ReactNode;
};

vi.mock("framer-motion", () => {
    // Memoize per-tag so the Proxy returns the SAME component instance
    // for repeated `motion.div` accesses. Without this, every render
    // produces a fresh component, React unmounts + remounts on each
    // pass, and the captured-`initial` useState below resets — making
    // the mock falsely report the latest render's `initial` rather
    // than the first one.
    const cache = new Map<string, React.ComponentType<MotionPropsLike>>();
    const passthrough = (tag: string) => {
        const cached = cache.get(tag);
        if (cached) return cached;
        const C = React.forwardRef<HTMLElement, MotionPropsLike>((props, ref) => {
            // Strip framer-only props so they don't end up as DOM attrs.
            const {
                initial,
                animate: _animate,
                exit: _exit,
                transition: _transition,
                layout: _layout,
                whileHover: _whileHover,
                whileTap: _whileTap,
                ...rest
            } = props;
            void _animate; void _exit; void _transition; void _layout;
            void _whileHover; void _whileTap;
            // Capture `initial` from the FIRST render of this element and
            // never update it — that mirrors framer-motion, which only
            // honors `initial` on mount and ignores it on later renders.
            // Encoded as a data-attr so tests can read it from the DOM.
            const [firstInitial] = React.useState(() => initial);
            const dataInitial = firstInitial === false ? "false" : "animate";
            // eslint-disable-next-line react-hooks/refs
            return React.createElement(tag, { ...rest, ref, "data-initial": dataInitial });
        });
        cache.set(tag, C as unknown as React.ComponentType<MotionPropsLike>);
        return C as unknown as React.ComponentType<MotionPropsLike>;
    };
    return {
        motion: new Proxy({} as Record<string, unknown>, {
            get: (_t, prop: string) => passthrough(prop),
        }),
        AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    };
});

// Stub the heavy renderer — we only care about the canvas's own
// `<motion.div>` props, not what's inside each component card.
vi.mock("../DynamicRenderer", () => ({
    default: () => <div data-testid="dynamic-renderer" />,
}));

import SDUICanvas from "../SDUICanvas";
import type { SavedComponent } from "../../hooks/useWebSocket";

const makeComponent = (id: string, type = "metric"): SavedComponent => ({
    id,
    title: `T-${id}`,
    component_type: type,
    component_data: { type, content: "x" },
    saved_at: 0,
} as unknown as SavedComponent);

const baseProps = {
    onDeleteComponent: vi.fn(),
    onCombineComponents: vi.fn(),
    onCondenseComponents: vi.fn(),
    onCancelCombine: vi.fn(),
    isCombining: false,
    combineError: null,
    onSendMessage: vi.fn(),
    activeChatId: "chat-1",
};

beforeEach(() => {
    vi.clearAllMocks();
});

afterEach(() => {
    cleanup();
});

function getInitialFlagsByComponentId(): Record<string, string> {
    const out: Record<string, string> = {};
    document.querySelectorAll<HTMLElement>("[data-component-id]").forEach((el) => {
        const id = el.dataset.componentId;
        if (id) out[id] = el.dataset.initial ?? "animate";
    });
    return out;
}

describe("SDUICanvas — entry-animation skip on first paint (US2)", () => {
    it("renders no canvas-card flash when components are present at first paint", () => {
        const components = [
            makeComponent("a"),
            makeComponent("b"),
            makeComponent("c"),
        ];
        render(<SDUICanvas {...baseProps} canvasComponents={components} />);
        const flags = getInitialFlagsByComponentId();
        expect(flags).toEqual({ a: "false", b: "false", c: "false" });
    });

    it("renders the empty-state block with initial={false} when canvas starts empty", () => {
        // The empty-state branch uses the `mountedRef.current ? {…} : false`
        // pattern. On first paint mountedRef is still false, so the test
        // verifies the rendered tree carries `data-initial="false"`.
        const { container } = render(
            <SDUICanvas {...baseProps} canvasComponents={[]} />,
        );
        // The first <motion.div> in the empty-state branch wraps the
        // suggestion grid. It's an unkeyed div — locate it by its
        // distinctive class fragment.
        const motionRoots = container.querySelectorAll(".space-y-6");
        expect(motionRoots.length).toBeGreaterThan(0);
        const firstPaintInitial = (motionRoots[0] as HTMLElement).dataset.initial;
        expect(firstPaintInitial).toBe("false");
    });
});

describe("SDUICanvas — streaming-reconciliation behavior (US3)", () => {
    it("animates only the newly streamed component; existing ones stay put", () => {
        const initial = [makeComponent("x"), makeComponent("y")];
        const { rerender } = render(
            <SDUICanvas {...baseProps} canvasComponents={initial} />,
        );
        // Sanity check the mount snapshot.
        expect(getInitialFlagsByComponentId()).toEqual({ x: "false", y: "false" });

        // Streamed addition: a new component arrives.
        rerender(
            <SDUICanvas
                {...baseProps}
                canvasComponents={[...initial, makeComponent("z")]}
            />,
        );
        const flags = getInitialFlagsByComponentId();
        expect(flags.x).toBe("false");
        expect(flags.y).toBe("false");
        expect(flags.z).toBe("animate"); // gets the entry animation
    });

    it("keeps existing components calm across multiple streamed additions", () => {
        const initial = [makeComponent("p")];
        const { rerender } = render(
            <SDUICanvas {...baseProps} canvasComponents={initial} />,
        );

        // Three streamed additions, one at a time.
        rerender(
            <SDUICanvas
                {...baseProps}
                canvasComponents={[...initial, makeComponent("q")]}
            />,
        );
        rerender(
            <SDUICanvas
                {...baseProps}
                canvasComponents={[
                    ...initial,
                    makeComponent("q"),
                    makeComponent("r"),
                ]}
            />,
        );
        rerender(
            <SDUICanvas
                {...baseProps}
                canvasComponents={[
                    ...initial,
                    makeComponent("q"),
                    makeComponent("r"),
                    makeComponent("s"),
                ]}
            />,
        );
        const flags = getInitialFlagsByComponentId();
        expect(flags.p).toBe("false"); // present at first paint, stays calm
        expect(flags.q).toBe("animate"); // arrived after mount
        expect(flags.r).toBe("animate");
        expect(flags.s).toBe("animate");
    });

    it("unchanged props re-renders do not flash the existing components", () => {
        const components = [makeComponent("k1"), makeComponent("k2")];
        const { rerender } = render(
            <SDUICanvas {...baseProps} canvasComponents={components} />,
        );
        // Pure re-render with the same props — common on parent state
        // changes — must not cause the existing cards to switch their
        // `initial` from `false` to the entry-animation object.
        rerender(<SDUICanvas {...baseProps} canvasComponents={components} />);
        rerender(<SDUICanvas {...baseProps} canvasComponents={components} />);
        const flags = getInitialFlagsByComponentId();
        expect(flags).toEqual({ k1: "false", k2: "false" });
    });
});
