/**
 * DynamicRenderer — Renders backend UI primitives as premium React components.
 *
 * Instead of using json-render/react Renderer (which is too strict with Zod validation),
 * this uses a direct component mapping from the registry implementations.
 * This approach is more resilient to shape mismatches in backend data.
 */
import React, { Component, type ErrorInfo } from "react";
import { motion } from "framer-motion";
import {
    AlertCircle,
    CheckCircle,
    Info,
    AlertTriangle,
    ExternalLink,
} from "lucide-react";
import ReactMarkdown from "react-markdown";

interface DynamicRendererProps {
    components: any[];
}

// ─── Error Boundary ────────────────────────────────────────────────
class RenderErrorBoundary extends Component<
    { children: React.ReactNode; fallback?: React.ReactNode },
    { hasError: boolean; error?: Error }
> {
    constructor(props: any) {
        super(props);
        this.state = { hasError: false };
    }
    static getDerivedStateFromError(error: Error) {
        return { hasError: true, error };
    }
    componentDidCatch(error: Error, info: ErrorInfo) {
        console.error("DynamicRenderer error:", error, info);
    }
    render() {
        if (this.state.hasError) {
            return (
                <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                    <p className="font-medium">Render error</p>
                    <p className="text-red-400/70 mt-1">{this.state.error?.message}</p>
                </div>
            );
        }
        return this.props.children;
    }
}

// ─── Component Renderers ───────────────────────────────────────────

function renderComponent(comp: any, index: number): React.ReactNode {
    if (!comp || typeof comp !== "object") return null;
    const { type, ...props } = comp;
    console.log("Rendering component:", type, props);

    switch (type) {
        case "container":
            return <RenderContainer key={index} {...props} />;
        case "text":
            return <RenderText key={index} {...props} />;
        case "card":
            return <RenderCard key={index} {...props} />;
        case "table":
            return <RenderTable key={index} {...props} />;
        case "metric":
            return <RenderMetric key={index} {...props} />;
        case "alert":
            return <RenderAlert key={index} {...props} />;
        case "progress":
            return <RenderProgress key={index} {...props} />;
        case "grid":
            return <RenderGrid key={index} {...props} />;
        case "list":
            return <RenderList key={index} {...props} />;
        case "code":
            return <RenderCode key={index} {...props} />;
        case "bar_chart":
            return <RenderBarChart key={index} {...props} />;
        case "line_chart":
            return <RenderLineChart key={index} {...props} />;
        case "pie_chart":
            return <RenderPieChart key={index} {...props} />;
        case "plotly_chart":
            return <RenderGenericPlotly key={index} {...props} />;
        case "divider":
            return <hr key={index} className="border-white/10 my-3" />;
        case "button":
            return <RenderButton key={index} {...props} />;
        default:
            console.warn(`Unknown component type: ${type}`);
            return null;
    }
}

function renderChildren(items: any[]): React.ReactNode {
    if (!Array.isArray(items)) return null;
    return items.map((c, i) => renderComponent(c, i));
}

// ── Container ──────────────────────────────────────────────────────
function RenderContainer({ children, content }: any) {
    const kids = children || content || [];
    return <div className="flex flex-col gap-4">{renderChildren(kids)}</div>;
}

// ── Text ───────────────────────────────────────────────────────────
function RenderText({ content, variant = "body" }: any) {
    const classes: Record<string, string> = {
        h1: "text-2xl font-bold text-white",
        h2: "text-xl font-semibold text-white",
        h3: "text-lg font-medium text-white",
        body: "text-sm text-astral-text leading-relaxed",
        caption: "text-xs text-astral-muted",
        markdown: "prose prose-invert max-w-none text-sm text-astral-text leading-relaxed prose-headings:text-white prose-a:text-astral-primary hover:prose-a:text-astral-secondary prose-strong:text-white prose-code:text-astral-accent prose-code:bg-white/5 prose-code:px-1 prose-code:rounded prose-pre:bg-black/40 prose-pre:border prose-pre:border-white/5",
    };

    if (variant === "markdown") {
        return (
            <div className={classes.markdown}>
                <ReactMarkdown>{content}</ReactMarkdown>
            </div>
        );
    }

    const Tag = variant === "h1" ? "h1" : variant === "h2" ? "h2" : variant === "h3" ? "h3" : "p";
    return <Tag className={classes[variant] || classes.body}>{content}</Tag>;
}

// ── Card ───────────────────────────────────────────────────────────
function RenderCard({ title, children, content }: any) {
    const kids = children || content || [];
    return (
        <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="glass-card p-5"
        >
            {title && (
                <h3 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
                    <span className="w-1 h-4 rounded-full bg-astral-primary inline-block" />
                    {title}
                </h3>
            )}
            <div className="space-y-3">{renderChildren(kids)}</div>
        </motion.div>
    );
}

// ── Table ──────────────────────────────────────────────────────────
function RenderTable({ headers, rows }: any) {
    if (!headers || !rows) return null;
    return (
        <div className="overflow-x-auto rounded-lg border border-white/5">
            <table className="w-full text-sm">
                <thead>
                    <tr className="bg-astral-primary/10 border-b border-white/5">
                        {headers.map((h: string, i: number) => (
                            <th key={i} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-astral-muted">{h}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row: any[], ri: number) => (
                        <tr key={ri} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                            {row.map((cell: any, ci: number) => (
                                <td key={ci} className="px-4 py-3 text-astral-text">
                                    {typeof cell === "string" && ["Critical", "Severe"].includes(cell)
                                        ? <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/20 text-red-400">{cell}</span>
                                        : typeof cell === "string" && ["Moderate"].includes(cell)
                                            ? <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-500/20 text-yellow-400">{cell}</span>
                                            : typeof cell === "string" && ["Mild", "Stable"].includes(cell)
                                                ? <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/20 text-green-400">{cell}</span>
                                                : String(cell)}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

// ── Metric ─────────────────────────────────────────────────────────
function RenderMetric({ title, value, subtitle, progress, variant = "default" }: any) {
    const variantColors: Record<string, string> = {
        default: "from-astral-primary/20 to-astral-primary/5",
        warning: "from-yellow-500/20 to-yellow-500/5",
        error: "from-red-500/20 to-red-500/5",
        success: "from-green-500/20 to-green-500/5",
    };
    const bg = variantColors[variant] || variantColors.default;
    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className={`rounded-xl p-4 bg-gradient-to-br ${bg} border border-white/5`}
        >
            <p className="text-xs text-astral-muted font-medium uppercase tracking-wider mb-1">{title}</p>
            <p className="text-2xl font-bold text-white">{value}</p>
            {subtitle && <p className="text-xs text-astral-muted mt-1">{subtitle}</p>}
            {progress != null && (
                <div className="mt-3 h-1.5 bg-white/10 rounded-full overflow-hidden">
                    <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.min(progress * 100, 100)}%` }}
                        transition={{ duration: 0.8, ease: "easeOut" }}
                        className={`h-full rounded-full ${progress > 0.9 ? "bg-red-500" : progress > 0.7 ? "bg-yellow-500" : "bg-astral-primary"}`}
                    />
                </div>
            )}
        </motion.div>
    );
}

// ── Alert ──────────────────────────────────────────────────────────
function RenderAlert({ message, title, variant = "info" }: any) {
    const config: Record<string, { bg: string; border: string; icon: React.ReactNode; text: string }> = {
        info: { bg: "bg-blue-500/10", border: "border-blue-500/20", icon: <Info size={16} />, text: "text-blue-400" },
        success: { bg: "bg-green-500/10", border: "border-green-500/20", icon: <CheckCircle size={16} />, text: "text-green-400" },
        warning: { bg: "bg-yellow-500/10", border: "border-yellow-500/20", icon: <AlertTriangle size={16} />, text: "text-yellow-400" },
        error: { bg: "bg-red-500/10", border: "border-red-500/20", icon: <AlertCircle size={16} />, text: "text-red-400" },
    };
    const c = config[variant] || config.info;
    return (
        <div className={`${c.bg} ${c.border} border rounded-lg p-4 flex items-start gap-3`}>
            <span className={c.text}>{c.icon}</span>
            <div>
                {title && <p className={`font-medium text-sm ${c.text}`}>{title}</p>}
                <p className="text-sm text-astral-text/80">{message}</p>
            </div>
        </div>
    );
}

// ── Progress ───────────────────────────────────────────────────────
function RenderProgress({ value, label, show_percentage }: any) {
    return (
        <div>
            {label && (
                <div className="flex justify-between text-xs text-astral-muted mb-1">
                    <span>{label}</span>
                    {show_percentage !== false && <span>{Math.round(value * 100)}%</span>}
                </div>
            )}
            <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(value * 100, 100)}%` }}
                    transition={{ duration: 0.6 }}
                    className="h-full bg-gradient-to-r from-astral-primary to-astral-secondary rounded-full"
                />
            </div>
        </div>
    );
}

// ── Grid ───────────────────────────────────────────────────────────
function RenderGrid({ columns = 2, gap = 16, children, content }: any) {
    const kids = children || content || [];
    return (
        <div
            className="grid"
            style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`, gap: `${gap}px` }}
        >
            {renderChildren(kids)}
        </div>
    );
}

// ── List ───────────────────────────────────────────────────────────
function RenderList({ items, ordered, variant = "default" }: any) {
    if (!items) return null;

    if (variant === "detailed") {
        return (
            <div className="space-y-3">
                {items.map((item: any, i: number) => (
                    <div key={i} className="p-3 bg-white/5 rounded-lg border border-white/5 hover:bg-white/10 transition-colors">
                        <div className="flex justify-between items-start gap-4">
                            <div className="space-y-1 w-full">
                                <h4 className="text-sm font-semibold text-white flex items-center justify-between">
                                    {item.url ? (
                                        <a href={item.url} target="_blank" rel="noopener noreferrer" className="hover:text-astral-primary hover:underline flex items-center gap-2">
                                            {item.title}
                                            <ExternalLink size={12} className="opacity-50" />
                                        </a>
                                    ) : (
                                        item.title
                                    )}
                                </h4>
                                {item.subtitle && (
                                    <p className="text-xs text-astral-muted">{item.subtitle}</p>
                                )}
                                {item.description && (
                                    <p className="text-sm text-astral-text/80 line-clamp-2">{item.description}</p>
                                )}
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        );
    }

    const Tag = ordered ? "ol" : "ul";
    return (
        <Tag className={`space-y-2 text-sm ${ordered ? "list-decimal" : "list-disc"} list-inside text-astral-text`}>
            {items.map((item: any, i: number) => (
                <li key={i} className="leading-relaxed">
                    {typeof item === "string" ? (
                        <span dangerouslySetInnerHTML={{ __html: item.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white font-medium">$1</strong>') }} />
                    ) : JSON.stringify(item)}
                </li>
            ))}
        </Tag>
    );
}

// ── Code ───────────────────────────────────────────────────────────
function RenderCode({ code, language }: any) {
    return (
        <div className="rounded-lg bg-black/40 border border-white/5 overflow-hidden">
            {language && (
                <div className="px-4 py-2 text-xs text-astral-muted border-b border-white/5">{language}</div>
            )}
            <pre className="p-4 text-sm overflow-x-auto" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                <code className="text-green-400">{code}</code>
            </pre>
        </div>
    );
}

// ... imports
import Plot from 'react-plotly.js';

// ... existing code ...

// ── Bar Chart ──────────────────────────────────────────────────────
function RenderBarChart({ title, labels, datasets }: any) {
    const dataset = datasets?.[0];
    if (!dataset) return null;
    const data = dataset.data as number[];

    return (
        <div className="w-full">
            <p className="text-sm font-medium text-white mb-3">{title}</p>
            <Plot
                data={[
                    {
                        x: labels,
                        y: data,
                        type: 'bar',
                        marker: { color: '#6366F1' },
                    },
                ]}
                layout={{
                    autosize: true,
                    height: 320,
                    margin: { l: 40, r: 20, t: 20, b: 40 },
                    paper_bgcolor: 'rgba(0,0,0,0)',
                    plot_bgcolor: 'rgba(0,0,0,0)',
                    font: { color: '#9CA3AF' },
                    xaxis: {
                        gridcolor: 'rgba(255,255,255,0.1)',
                        tickfont: { size: 10 },
                    },
                    yaxis: {
                        gridcolor: 'rgba(255,255,255,0.1)',
                        tickfont: { size: 10 },
                    },
                }}
                useResizeHandler={true}
                style={{ width: '100%', height: '100%' }}
                config={{ displayModeBar: false }}
            />
        </div>
    );
}

// ── Line Chart ─────────────────────────────────────────────────────
function RenderLineChart({ title, labels, datasets }: any) {
    const dataset = datasets?.[0];
    if (!dataset) return null;
    const data = dataset.data as number[];

    return (
        <div className="w-full">
            <p className="text-sm font-medium text-white mb-3">{title}</p>
            <Plot
                data={[
                    {
                        x: labels,
                        y: data,
                        type: 'scatter',
                        mode: 'lines+markers',
                        marker: { color: '#6366F1' },
                        line: { color: '#6366F1', width: 2 },
                    },
                ]}
                layout={{
                    autosize: true,
                    height: 320,
                    margin: { l: 40, r: 20, t: 20, b: 40 },
                    paper_bgcolor: 'rgba(0,0,0,0)',
                    plot_bgcolor: 'rgba(0,0,0,0)',
                    font: { color: '#9CA3AF' },
                    xaxis: {
                        gridcolor: 'rgba(255,255,255,0.1)',
                        tickfont: { size: 10 },
                    },
                    yaxis: {
                        gridcolor: 'rgba(255,255,255,0.1)',
                        tickfont: { size: 10 },
                    },
                }}
                useResizeHandler={true}
                style={{ width: '100%', height: '100%' }}
                config={{ displayModeBar: false }}
            />
        </div>
    );
}

// ── Pie Chart ──────────────────────────────────────────────────────
function RenderPieChart({ title, labels, data: pieData, colors }: any) {
    if (!pieData) return null;
    const defaultColors = ["#6366F1", "#8B5CF6", "#06B6D4", "#10B981", "#F59E0B", "#EF4444", "#EC4899", "#3B82F6"];
    const colorArr = colors?.length ? colors : defaultColors;

    return (
        <div className="w-full">
            <p className="text-sm font-medium text-white mb-3">{title}</p>
            <Plot
                data={[
                    {
                        values: pieData,
                        labels: labels,
                        type: 'pie',
                        marker: { colors: colorArr },
                        textinfo: 'label+percent',
                        hoverinfo: 'label+value+percent',
                        hole: 0.4,
                    },
                ]}
                layout={{
                    autosize: true,
                    height: 320,
                    margin: { l: 20, r: 20, t: 20, b: 20 },
                    paper_bgcolor: 'rgba(0,0,0,0)',
                    plot_bgcolor: 'rgba(0,0,0,0)',
                    font: { color: '#9CA3AF' },
                    showlegend: true,
                    legend: { orientation: 'h', y: -0.1 },
                }}
                useResizeHandler={true}
                style={{ width: '100%', height: '100%' }}
                config={{ displayModeBar: false }}
            />
        </div>
    );
}

// ── Generic Plotly Chart ───────────────────────────────────────────
function RenderGenericPlotly({ title, data, layout, config }: any) {
    console.log("RenderGenericPlotly", { title, data, layout });
    if (!data) return null;

    // Merge default layout with provided layout
    const mergedLayout = {
        autosize: true,
        height: 320,
        margin: { l: 40, r: 20, t: 30, b: 40 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#9CA3AF' },
        xaxis: {
            gridcolor: 'rgba(255,255,255,0.1)',
            tickfont: { size: 10 },
        },
        yaxis: {
            gridcolor: 'rgba(255,255,255,0.1)',
            tickfont: { size: 10 },
        },
        ...layout,
    };

    return (
        <div className="w-full">
            {title && <p className="text-sm font-medium text-white mb-3">{title}</p>}
            <Plot
                data={data}
                layout={mergedLayout}
                config={{ displayModeBar: false, ...config }}
                useResizeHandler={true}
                style={{ width: '100%', height: '100%' }}
            />
        </div>
    );
}

// ── Button ─────────────────────────────────────────────────────────
function RenderButton({ label, variant = "primary" }: any) {
    const variants: Record<string, string> = {
        primary: "bg-astral-primary hover:bg-astral-primary/80 text-white",
        secondary: "bg-white/10 hover:bg-white/20 text-astral-text",
        danger: "bg-red-500/20 hover:bg-red-500/30 text-red-400",
    };
    return (
        <button className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${variants[variant] || variants.primary}`}>
            {label}
        </button>
    );
}

// ─── Main DynamicRenderer ──────────────────────────────────────────
export default function DynamicRenderer({ components }: DynamicRendererProps) {
    if (!components || components.length === 0) return null;

    return (
        <RenderErrorBoundary>
            <div className="dynamic-renderer space-y-4">
                {components.map((comp, i) => (
                    <RenderErrorBoundary key={i}>
                        {renderComponent(comp, i)}
                    </RenderErrorBoundary>
                ))}
            </div>
        </RenderErrorBoundary>
    );
}
