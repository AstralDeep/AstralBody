/**
 * json-render registry — maps catalog component types to React implementations.
 * These are the premium, Astral-themed visual components.
 */
import React from "react";
import { defineRegistry } from "@json-render/react";
import { catalog } from "./catalog";
import { motion } from "framer-motion";
import {
    AlertCircle,
    CheckCircle,
    Info,
    AlertTriangle,
} from "lucide-react";

export const { registry } = defineRegistry(catalog, {
    components: {
        // ── Container ──────────────────────────────────────────
        container: ({ props, children }) => (
            <div
                id={props.id || undefined}
                className="flex flex-col gap-4"
                style={props.style as React.CSSProperties}
            >
                {children}
            </div>
        ),

        // ── Text ───────────────────────────────────────────────
        text: ({ props }) => {
            const variant = props.variant || "body";
            const classes: Record<string, string> = {
                h1: "text-2xl font-bold text-white",
                h2: "text-xl font-semibold text-white",
                h3: "text-lg font-medium text-white",
                body: "text-sm text-astral-text leading-relaxed",
                caption: "text-xs text-astral-muted",
            };
            const Tag = variant === "h1" ? "h1" : variant === "h2" ? "h2" : variant === "h3" ? "h3" : "p";
            return <Tag className={classes[variant] || classes.body}>{props.content}</Tag>;
        },

        // ── Card ───────────────────────────────────────────────
        card: ({ props, children }) => (
            <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                id={props.id || undefined}
                className="glass-card p-5"
            >
                {props.title && (
                    <h3 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
                        <span className="w-1 h-4 rounded-full bg-astral-primary inline-block" />
                        {props.title}
                    </h3>
                )}
                <div className="space-y-3">{children}</div>
            </motion.div>
        ),

        // ── Table ──────────────────────────────────────────────
        table: ({ props }) => (
            <div className="overflow-x-auto rounded-lg border border-white/5">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="bg-astral-primary/10 border-b border-white/5">
                            {props.headers.map((h: string, i: number) => (
                                <th
                                    key={i}
                                    className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-astral-muted"
                                >
                                    {h}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {props.rows.map((row: any[], ri: number) => (
                            <tr
                                key={ri}
                                className="border-b border-white/5 hover:bg-white/5 transition-colors"
                            >
                                {row.map((cell: any, ci: number) => (
                                    <td key={ci} className="px-4 py-3 text-astral-text">
                                        {typeof cell === "string" &&
                                            ["Critical", "Severe"].includes(cell) ? (
                                            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/20 text-red-400">
                                                {cell}
                                            </span>
                                        ) : typeof cell === "string" &&
                                            ["Moderate"].includes(cell) ? (
                                            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-500/20 text-yellow-400">
                                                {cell}
                                            </span>
                                        ) : typeof cell === "string" &&
                                            ["Mild"].includes(cell) ? (
                                            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/20 text-green-400">
                                                {cell}
                                            </span>
                                        ) : (
                                            String(cell)
                                        )}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        ),

        // ── Metric Card ────────────────────────────────────────
        metric: ({ props }) => {
            const variantColors: Record<string, string> = {
                default: "from-astral-primary/20 to-astral-primary/5",
                warning: "from-yellow-500/20 to-yellow-500/5",
                error: "from-red-500/20 to-red-500/5",
                success: "from-green-500/20 to-green-500/5",
            };
            const bg = variantColors[props.variant || "default"] || variantColors.default;

            return (
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className={`rounded-xl p-4 bg-gradient-to-br ${bg} border border-white/5`}
                >
                    <p className="text-xs text-astral-muted font-medium uppercase tracking-wider mb-1">
                        {props.title}
                    </p>
                    <p className="text-2xl font-bold text-white">{props.value}</p>
                    {props.subtitle && (
                        <p className="text-xs text-astral-muted mt-1">{props.subtitle}</p>
                    )}
                    {props.progress != null && (
                        <div className="mt-3 h-1.5 bg-white/10 rounded-full overflow-hidden">
                            <motion.div
                                initial={{ width: 0 }}
                                animate={{ width: `${Math.min(props.progress * 100, 100)}%` }}
                                transition={{ duration: 0.8, ease: "easeOut" }}
                                className={`h-full rounded-full ${(props.progress || 0) > 0.9
                                    ? "bg-red-500"
                                    : (props.progress || 0) > 0.7
                                        ? "bg-yellow-500"
                                        : "bg-astral-primary"
                                    }`}
                            />
                        </div>
                    )}
                </motion.div>
            );
        },

        // ── Alert ──────────────────────────────────────────────
        alert: ({ props }) => {
            const config: Record<string, { bg: string; border: string; icon: React.ReactNode; text: string }> = {
                info: { bg: "bg-blue-500/10", border: "border-blue-500/20", icon: <Info size={16} />, text: "text-blue-400" },
                success: { bg: "bg-green-500/10", border: "border-green-500/20", icon: <CheckCircle size={16} />, text: "text-green-400" },
                warning: { bg: "bg-yellow-500/10", border: "border-yellow-500/20", icon: <AlertTriangle size={16} />, text: "text-yellow-400" },
                error: { bg: "bg-red-500/10", border: "border-red-500/20", icon: <AlertCircle size={16} />, text: "text-red-400" },
            };
            const c = config[props.variant || "info"] || config.info;
            return (
                <div className={`${c.bg} ${c.border} border rounded-lg p-4 flex items-start gap-3`}>
                    <span className={c.text}>{c.icon}</span>
                    <div>
                        {props.title && <p className={`font-medium text-sm ${c.text}`}>{props.title}</p>}
                        <p className="text-sm text-astral-text/80">{props.message}</p>
                    </div>
                </div>
            );
        },

        // ── Progress Bar ───────────────────────────────────────
        progress: ({ props }) => (
            <div>
                {props.label && (
                    <div className="flex justify-between text-xs text-astral-muted mb-1">
                        <span>{props.label}</span>
                        {props.show_percentage !== false && <span>{Math.round(props.value * 100)}%</span>}
                    </div>
                )}
                <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                    <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.min(props.value * 100, 100)}%` }}
                        transition={{ duration: 0.6 }}
                        className="h-full bg-gradient-to-r from-astral-primary to-astral-secondary rounded-full"
                    />
                </div>
            </div>
        ),

        // ── Grid ───────────────────────────────────────────────
        grid: ({ props, children }) => (
            <div
                className="grid gap-4"
                style={{
                    gridTemplateColumns: `repeat(${props.columns || 2}, minmax(0, 1fr))`,
                    gap: `${props.gap || 16}px`,
                }}
            >
                {children}
            </div>
        ),

        // ── List ───────────────────────────────────────────────
        list: ({ props }) => {
            const Tag = props.ordered ? "ol" : "ul";
            return (
                <Tag className={`space-y-3 text-sm ${props.ordered ? "list-decimal" : "list-none"} list-inside text-astral-text`}>
                    {props.items.map((item: any, i: number) => (
                        <li key={i} className="leading-relaxed">
                            {typeof item === "string" ? (
                                <span dangerouslySetInnerHTML={{ __html: item.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white font-medium">$1</strong>') }} />
                            ) : (
                                // Rich Item Renderer
                                <div className="bg-white/5 border border-white/5 rounded-lg p-4 hover:bg-white/10 transition-colors">
                                    <div className="flex justify-between items-start gap-4">
                                        <div>
                                            {item.title && (
                                                <div className="font-semibold text-white mb-1">
                                                    {item.url ? (
                                                        <a
                                                            href={item.url}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="hover:text-astral-primary transition-colors flex items-center gap-2"
                                                        >
                                                            {item.title}
                                                            <span className="text-xs opacity-50">↗</span>
                                                        </a>
                                                    ) : (
                                                        item.title
                                                    )}
                                                </div>
                                            )}
                                            {item.subtitle && (
                                                <div className="text-xs text-astral-muted mb-2 font-medium uppercase tracking-wide">
                                                    {item.subtitle}
                                                </div>
                                            )}
                                            {item.description && (
                                                <div className="text-sm text-astral-text/90 line-clamp-3">
                                                    {item.description}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </li>
                    ))}
                </Tag>
            );
        },

        // ── Code Block ─────────────────────────────────────────
        code: ({ props }) => (
            <div className="rounded-lg bg-black/40 border border-white/5 overflow-hidden">
                {props.language && (
                    <div className="px-4 py-2 text-xs text-astral-muted border-b border-white/5 flex items-center justify-between">
                        <span>{props.language}</span>
                    </div>
                )}
                <pre className="p-4 text-sm overflow-x-auto" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                    <code className="text-green-400">{props.code}</code>
                </pre>
            </div>
        ),

        // ── Bar Chart ──────────────────────────────────────────
        bar_chart: ({ props }) => {
            const dataset = props.datasets[0];
            if (!dataset) return null;
            const data = dataset.data as number[];
            const maxVal = Math.max(...data, 1);
            return (
                <div>
                    <p className="text-sm font-medium text-white mb-3">{props.title}</p>
                    <div className="flex items-end gap-2 h-48">
                        {data.map((val: number, i: number) => (
                            <div key={i} className="flex-1 flex flex-col items-center">
                                <motion.div
                                    initial={{ height: 0 }}
                                    animate={{ height: `${(val / maxVal) * 100}%` }}
                                    transition={{ duration: 0.5, delay: i * 0.05 }}
                                    className="w-full rounded-t bg-gradient-to-t from-astral-primary to-astral-secondary min-h-[4px]"
                                    title={`${props.labels[i]}: ${val}`}
                                />
                                <span className="text-[10px] text-astral-muted mt-1 truncate w-full text-center">
                                    {props.labels[i]?.split(" ")[0]}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            );
        },

        // ── Line Chart ─────────────────────────────────────────
        line_chart: ({ props }) => {
            const dataset = props.datasets[0];
            if (!dataset) return null;
            const data = dataset.data as number[];
            const maxVal = Math.max(...data, 1);
            const minVal = Math.min(...data);
            const range = maxVal - minVal || 1;
            const w = 400;
            const h = 150;
            const points = data.map((v: number, i: number) => ({
                x: (i / Math.max(data.length - 1, 1)) * w,
                y: h - ((v - minVal) / range) * h,
            }));
            const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");

            return (
                <div>
                    <p className="text-sm font-medium text-white mb-3">{props.title}</p>
                    <svg viewBox={`-10 -10 ${w + 20} ${h + 40}`} className="w-full">
                        <path d={pathD} fill="none" stroke="#6366F1" strokeWidth="2" />
                        {points.map((p, i) => (
                            <g key={i}>
                                <circle cx={p.x} cy={p.y} r="3" fill="#6366F1" />
                                <text x={p.x} y={h + 20} textAnchor="middle" fill="#9CA3AF" fontSize="8">
                                    {props.labels[i]?.split(" ")[0]}
                                </text>
                            </g>
                        ))}
                    </svg>
                </div>
            );
        },

        // ── Pie Chart ──────────────────────────────────────────
        pie_chart: ({ props }) => {
            const total = props.data.reduce((a: number, b: number) => a + b, 0) || 1;
            const defaultColors = ["#6366F1", "#8B5CF6", "#06B6D4", "#10B981", "#F59E0B", "#EF4444", "#EC4899", "#3B82F6"];
            const colors = props.colors?.length ? props.colors : defaultColors;
            let cumAngle = 0;

            return (
                <div>
                    <p className="text-sm font-medium text-white mb-3">{props.title}</p>
                    <div className="flex items-center gap-6">
                        <svg viewBox="0 0 100 100" className="w-40 h-40">
                            {props.data.map((val: number, i: number) => {
                                const angle = (val / total) * 360;
                                const startAngle = cumAngle;
                                cumAngle += angle;
                                const r = 40;
                                const cx = 50;
                                const cy = 50;
                                const startRad = ((startAngle - 90) * Math.PI) / 180;
                                const endRad = ((startAngle + angle - 90) * Math.PI) / 180;
                                const x1 = cx + r * Math.cos(startRad);
                                const y1 = cy + r * Math.sin(startRad);
                                const x2 = cx + r * Math.cos(endRad);
                                const y2 = cy + r * Math.sin(endRad);
                                const largeArc = angle > 180 ? 1 : 0;
                                const d = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`;
                                return <path key={i} d={d} fill={colors[i % colors.length]} opacity="0.85" />;
                            })}
                        </svg>
                        <div className="space-y-2">
                            {props.labels.map((label: string, i: number) => (
                                <div key={i} className="flex items-center gap-2 text-xs">
                                    <span className="w-2.5 h-2.5 rounded-sm" style={{ background: colors[i % colors.length] }} />
                                    <span className="text-astral-muted">{label}</span>
                                    <span className="text-white font-medium">{props.data[i]}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            );
        },

        // ── Divider ────────────────────────────────────────────
        divider: () => <hr className="border-white/10 my-3" />,

        // ── Button ─────────────────────────────────────────────
        button: ({ props, emit }) => {
            const variants: Record<string, string> = {
                primary: "bg-astral-primary hover:bg-astral-primary/80 text-white",
                secondary: "bg-white/10 hover:bg-white/20 text-astral-text",
                danger: "bg-red-500/20 hover:bg-red-500/30 text-red-400",
            };
            return (
                <button
                    onClick={() => emit?.("press")}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${variants[props.variant || "primary"] || variants.primary
                        }`}
                >
                    {props.label}
                </button>
            );
        },
    },
});
