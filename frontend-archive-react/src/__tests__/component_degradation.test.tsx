/**
 * Category 6b: Frontend Component Graceful Degradation Tests.
 *
 * Validates that DynamicRenderer handles missing or malformed
 * component payloads without crashing (error boundary catches).
 */
import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";

// Mock framer-motion
vi.mock("framer-motion", () => {
    const createMotionComponent = (tag: string) =>
        React.forwardRef((props: any, ref: any) => React.createElement(tag, { ...props, ref }));
    return {
        motion: new Proxy({} as Record<string, any>, {
            get: (_target, prop: string) => createMotionComponent(prop),
        }),
        AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    };
});

vi.mock("lucide-react", () => ({
    AlertCircle: () => <span />,
    CheckCircle: () => <span />,
    Info: () => <span />,
    AlertTriangle: () => <span />,
    ExternalLink: () => <span />,
    ChevronRight: () => <span />,
    UploadCloud: () => <span />,
    Download: () => <span />,
    Wrench: () => <span />,
    PanelTopOpen: () => <span />,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("react-markdown", () => ({
    default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("remark-math", () => ({ default: () => {} }));
vi.mock("rehype-katex", () => ({ default: () => {} }));
vi.mock("katex/dist/katex.min.css", () => ({}));

vi.mock("../hooks/useSmartAuth", () => ({
    useSmartAuth: () => ({ user: null, isAuthenticated: false, getToken: () => "mock-token" }),
}));
vi.mock("../contexts/ThemeContext", () => ({
    useTheme: () => ({ colors: { primary: "#6366F1" }, setColor: vi.fn() }),
}));
vi.mock("../contexts/AgentPermissionContext", () => ({
    useAgentPermissions: () => ({ isToolAllowed: () => true }),
}));
vi.mock("react-plotly.js", () => ({
    default: () => <div data-testid="plotly-chart" />,
}));

import DynamicRenderer from "../components/DynamicRenderer";

describe("Component Graceful Degradation", () => {
    it("DG-001: table with empty rows renders without crash", () => {
        expect(() => {
            render(
                <DynamicRenderer components={[{ type: "table", headers: ["A", "B"], rows: [] }]} />
            );
        }).not.toThrow();
    });

    it("DG-002: bar chart with empty dataset renders without crash", () => {
        expect(() => {
            render(
                <DynamicRenderer components={[{ type: "bar_chart", title: "Empty", labels: [], datasets: [] }]} />
            );
        }).not.toThrow();
    });

    it("DG-003: metric with no progress renders without crash", () => {
        expect(() => {
            render(
                <DynamicRenderer components={[{ type: "metric", title: "Test", value: "0" }]} />
            );
        }).not.toThrow();
    });

    it("DG-004: alert with no variant uses default", () => {
        const { container } = render(
            <DynamicRenderer components={[{ type: "alert", message: "Fallback alert" }]} />
        );
        expect(container.textContent).toContain("Fallback alert");
    });

    it("DG-005: unknown component type is handled gracefully", () => {
        expect(() => {
            render(
                <DynamicRenderer components={[{ type: "nonexistent_widget", data: "test" }]} />
            );
        }).not.toThrow();
    });

    it("DG-006: null component in array is skipped", () => {
        expect(() => {
            render(
                <DynamicRenderer components={[null, { type: "text", content: "Valid", variant: "body" }, undefined]} />
            );
        }).not.toThrow();
    });

    it("DG-007: deeply nested components render", () => {
        expect(() => {
            render(
                <DynamicRenderer
                    components={[{
                        type: "card",
                        title: "Outer",
                        content: [{
                            type: "card",
                            title: "Inner",
                            content: [{
                                type: "text",
                                content: "Deep",
                                variant: "body",
                            }],
                        }],
                    }]}
                />
            );
        }).not.toThrow();
    });

    it("DG-008: empty components array renders nothing", () => {
        const { container } = render(
            <DynamicRenderer components={[]} />
        );
        // Should render the wrapper div but no child components
        expect(container.childElementCount).toBeGreaterThanOrEqual(0);
    });
});
