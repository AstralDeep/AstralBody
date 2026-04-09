/**
 * Category 6: Frontend SDUI Rendering Fidelity Tests.
 *
 * Tests DynamicRenderer with JSON component payloads matching
 * the backend primitives. Uses mocked context providers.
 */
import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock framer-motion to avoid animation snapshot instability
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

// Mock lucide-react icons
vi.mock("lucide-react", () => ({
    AlertCircle: () => <span data-testid="icon-alert-circle" />,
    CheckCircle: () => <span data-testid="icon-check-circle" />,
    Info: () => <span data-testid="icon-info" />,
    AlertTriangle: () => <span data-testid="icon-alert-triangle" />,
    ExternalLink: () => <span data-testid="icon-external-link" />,
    ChevronRight: () => <span data-testid="icon-chevron-right" />,
    UploadCloud: () => <span data-testid="icon-upload" />,
    Download: () => <span data-testid="icon-download" />,
    Wrench: () => <span data-testid="icon-wrench" />,
    PanelTopOpen: () => <span data-testid="icon-panel" />,
}));

// Mock sonner
vi.mock("sonner", () => ({
    toast: { success: vi.fn(), error: vi.fn() },
}));

// Mock react-markdown
vi.mock("react-markdown", () => ({
    default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// Mock remark-math and rehype-katex
vi.mock("remark-math", () => ({ default: () => {} }));
vi.mock("rehype-katex", () => ({ default: () => {} }));
vi.mock("katex/dist/katex.min.css", () => ({}));

// Mock contexts
vi.mock("../hooks/useSmartAuth", () => ({
    useSmartAuth: () => ({ user: null, isAuthenticated: false, getToken: () => "mock-token" }),
}));

vi.mock("../contexts/ThemeContext", () => ({
    useTheme: () => ({
        colors: { primary: "#6366F1", secondary: "#8B5CF6" },
        setColor: vi.fn(),
    }),
}));

vi.mock("../contexts/AgentPermissionContext", () => ({
    useAgentPermissions: () => ({
        isToolAllowed: () => true,
    }),
}));

// Mock plotly
vi.mock("react-plotly.js", () => ({
    default: () => <div data-testid="plotly-chart" />,
}));

import DynamicRenderer from "../components/DynamicRenderer";

describe("SDUI Component Rendering via DynamicRenderer", () => {
    // ── FR-001: Text ──────────────────────────────────────────────
    it("FR-001: renders text component with h1 variant", () => {
        const { container } = render(
            <DynamicRenderer components={[{ type: "text", content: "Hello World", variant: "h1" }]} />
        );
        expect(screen.getByText("Hello World")).toBeTruthy();
        expect(container).toMatchSnapshot();
    });

    it("FR-001b: renders text with body variant", () => {
        render(
            <DynamicRenderer components={[{ type: "text", content: "Body text here", variant: "body" }]} />
        );
        expect(screen.getByText("Body text here")).toBeTruthy();
    });

    // ── FR-002: Card ──────────────────────────────────────────────
    it("FR-002: renders card with title and children", () => {
        const { container } = render(
            <DynamicRenderer
                components={[{
                    type: "card",
                    title: "Test Card",
                    content: [{ type: "text", content: "Inner content", variant: "body" }],
                }]}
            />
        );
        expect(screen.getByText("Test Card")).toBeTruthy();
        expect(screen.getByText("Inner content")).toBeTruthy();
        expect(container).toMatchSnapshot();
    });

    // ── FR-003: Table ─────────────────────────────────────────────
    it("FR-003: renders table with headers and rows", () => {
        const { container } = render(
            <DynamicRenderer
                components={[{
                    type: "table",
                    headers: ["Name", "Status", "Score"],
                    rows: [
                        ["Alice", "Critical", "95"],
                        ["Bob", "Moderate", "72"],
                    ],
                }]}
            />
        );
        expect(screen.getAllByText("Name").length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText("Alice").length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText("Critical").length).toBeGreaterThanOrEqual(1);
        expect(container).toMatchSnapshot();
    });

    // ── FR-004: Metric ────────────────────────────────────────────
    it("FR-004: renders metric card with value", () => {
        const { container } = render(
            <DynamicRenderer
                components={[{
                    type: "metric",
                    title: "CPU Usage",
                    value: "78%",
                    subtitle: "Last 5 minutes",
                    progress: 0.78,
                }]}
            />
        );
        expect(screen.getByText("CPU Usage")).toBeTruthy();
        expect(screen.getByText("78%")).toBeTruthy();
        expect(container).toMatchSnapshot();
    });

    // ── FR-005: Alert variants ────────────────────────────────────
    it.each(["info", "success", "warning", "error"] as const)(
        "FR-005: renders alert variant %s",
        (variant) => {
            render(
                <DynamicRenderer
                    components={[{
                        type: "alert",
                        message: `This is a ${variant} alert`,
                        title: `${variant} Title`,
                        variant,
                    }]}
                />
            );
            expect(screen.getByText(`This is a ${variant} alert`)).toBeTruthy();
        }
    );

    // ── FR-006: Progress bar ──────────────────────────────────────
    it("FR-006: renders progress bar", () => {
        const { container } = render(
            <DynamicRenderer
                components={[{
                    type: "progress",
                    value: 0.65,
                    label: "Upload Progress",
                    show_percentage: true,
                }]}
            />
        );
        expect(screen.getByText("Upload Progress")).toBeTruthy();
        expect(container).toMatchSnapshot();
    });

    // ── FR-007: Grid ──────────────────────────────────────────────
    it("FR-007: renders grid layout", () => {
        const { container } = render(
            <DynamicRenderer
                components={[{
                    type: "grid",
                    columns: 3,
                    children: [
                        { type: "text", content: "Cell 1", variant: "body" },
                        { type: "text", content: "Cell 2", variant: "body" },
                        { type: "text", content: "Cell 3", variant: "body" },
                    ],
                }]}
            />
        );
        expect(screen.getByText("Cell 1")).toBeTruthy();
        expect(screen.getByText("Cell 2")).toBeTruthy();
        expect(container).toMatchSnapshot();
    });

    // ── FR-008: List ──────────────────────────────────────────────
    it("FR-008: renders unordered list", () => {
        render(
            <DynamicRenderer
                components={[{
                    type: "list",
                    items: ["Item A", "Item B", "Item C"],
                    ordered: false,
                }]}
            />
        );
        expect(screen.getByText("Item A")).toBeTruthy();
    });

    // ── FR-009: Code block ────────────────────────────────────────
    it("FR-009: renders code block with language", () => {
        const { container } = render(
            <DynamicRenderer
                components={[{
                    type: "code",
                    code: "print('hello')",
                    language: "python",
                }]}
            />
        );
        expect(screen.getByText("python")).toBeTruthy();
        expect(screen.getByText("print('hello')")).toBeTruthy();
        expect(container).toMatchSnapshot();
    });

    // ── FR-010: Bar chart ─────────────────────────────────────────
    it("FR-010: renders bar chart", () => {
        render(
            <DynamicRenderer
                components={[{
                    type: "bar_chart",
                    title: "Sales Data",
                    labels: ["Jan", "Feb", "Mar"],
                    datasets: [{ label: "Revenue", data: [100, 200, 150] }],
                }]}
            />
        );
        expect(screen.getByText("Sales Data")).toBeTruthy();
    });

    // ── FR-011: Line chart ────────────────────────────────────────
    it("FR-011: renders line chart with SVG", () => {
        render(
            <DynamicRenderer
                components={[{
                    type: "line_chart",
                    title: "Trend Data",
                    labels: ["Q1", "Q2", "Q3", "Q4"],
                    datasets: [{ label: "Growth", data: [10, 25, 15, 30] }],
                }]}
            />
        );
        expect(screen.getByText("Trend Data")).toBeTruthy();
    });

    // ── FR-012: Pie chart ─────────────────────────────────────────
    it("FR-012: renders pie chart with legend", () => {
        render(
            <DynamicRenderer
                components={[{
                    type: "pie_chart",
                    title: "Distribution",
                    labels: ["Alpha", "Beta", "Gamma"],
                    data: [40, 30, 30],
                }]}
            />
        );
        expect(screen.getByText("Distribution")).toBeTruthy();
    });

    // ── FR-013: Divider ───────────────────────────────────────────
    it("FR-013: renders divider", () => {
        const { container } = render(
            <DynamicRenderer components={[{ type: "divider" }]} />
        );
        expect(container.querySelector("hr")).toBeTruthy();
    });

    // ── FR-014: Button ────────────────────────────────────────────
    it("FR-014: renders button with label", () => {
        render(
            <DynamicRenderer
                components={[{
                    type: "button",
                    label: "Click Me",
                    action: "submit",
                    variant: "primary",
                }]}
            />
        );
        expect(screen.getByText("Click Me")).toBeTruthy();
    });

    // ── FR-015: Container ─────────────────────────────────────────
    it("FR-015: renders container with nested children", () => {
        render(
            <DynamicRenderer
                components={[{
                    type: "container",
                    children: [
                        { type: "text", content: "Child 1", variant: "body" },
                        { type: "text", content: "Child 2", variant: "body" },
                    ],
                }]}
            />
        );
        expect(screen.getByText("Child 1")).toBeTruthy();
        expect(screen.getByText("Child 2")).toBeTruthy();
    });

    // ── FR-016: Collapsible ───────────────────────────────────────
    it("FR-016: renders collapsible section", () => {
        render(
            <DynamicRenderer
                components={[{
                    type: "collapsible",
                    title: "More Details",
                    content: [{ type: "text", content: "Hidden content", variant: "body" }],
                    default_open: true,
                }]}
            />
        );
        expect(screen.getByText("More Details")).toBeTruthy();
    });

    // ── FR-017: Inline markdown inside string props ───────────────
    it("FR-017: renders **bold** inside a Card title as <strong>", () => {
        const { container } = render(
            <DynamicRenderer
                components={[{
                    type: "card",
                    title: "System **Status** Report",
                    content: [],
                }]}
            />
        );
        const strong = container.querySelector("h3 strong");
        expect(strong).toBeTruthy();
        expect(strong?.textContent).toBe("Status");
    });

    it("FR-017: renders `code` and *italic* inside a Progress label", () => {
        const { container } = render(
            <DynamicRenderer
                components={[{
                    type: "progress",
                    value: 0.5,
                    label: "Saving `config.json` *now*",
                }]}
            />
        );
        expect(container.querySelector("code")?.textContent).toBe("config.json");
        expect(container.querySelector("em")?.textContent).toBe("now");
    });

    it("FR-017: does NOT introduce a <div> inside a <p> for inline markdown", () => {
        // Regression: react-markdown wraps in a <div>; using it for inline contexts
        // (Metric.title is rendered inside a <p>) caused invalid HTML and hydration
        // warnings. The custom inline parser must not produce any block element.
        const { container } = render(
            <DynamicRenderer
                components={[{
                    type: "metric",
                    title: "**CPU** Usage",
                    value: "42%",
                    subtitle: "all *cores*",
                }]}
            />
        );
        const ps = container.querySelectorAll("p");
        ps.forEach((p) => {
            expect(p.querySelector("div")).toBeNull();
        });
    });
});
