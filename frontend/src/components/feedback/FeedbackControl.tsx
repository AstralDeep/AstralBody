/**
 * FeedbackControl — per-component thumbs / category / comment popover.
 *
 * Rendered as an overlay on each top-level rendered component when the
 * component carries a `_source_correlation_id`. When the originating
 * dispatch is unknown (e.g., static layouts), we still render the
 * control but submit without a correlation_id — the feedback is recorded
 * for audit but excluded from per-tool quality signals (per spec edge case).
 */
import React, { useCallback, useEffect, useRef, useState, type ReactElement } from "react";

import { useFeedback } from "../../hooks/useFeedback";
import {
    CATEGORIES,
    type Category,
    type Sentiment,
} from "../../types/feedback";

const CATEGORY_LABELS: Record<Category, string> = {
    "wrong-data": "Wrong data",
    irrelevant: "Irrelevant",
    "layout-broken": "Layout broken",
    "too-slow": "Too slow",
    other: "Other",
    unspecified: "(no category)",
};

export interface FeedbackControlProps {
    correlationId: string | null;
    componentId: string | null;
    sourceAgent: string | null;
    sourceTool: string | null;
    token: string | null;
    ws?: WebSocket | null;
    /** Optional class name appended to the trigger button. */
    className?: string;
}

export function FeedbackControl(props: FeedbackControlProps): ReactElement {
    const { correlationId, componentId, sourceAgent, sourceTool, token, ws, className } = props;
    const [open, setOpen] = useState(false);
    const [sentiment, setSentiment] = useState<Sentiment | null>(null);
    const [category, setCategory] = useState<Category>("unspecified");
    const [comment, setComment] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const popoverRef = useRef<HTMLDivElement | null>(null);

    const { submit, toast, clearToast } = useFeedback({ token, ws });

    // Auto-dismiss the toast after 4s.
    useEffect(() => {
        if (!toast) return;
        const t = window.setTimeout(clearToast, 4000);
        return () => window.clearTimeout(t);
    }, [toast, clearToast]);

    // Click-outside to close the popover.
    useEffect(() => {
        if (!open) return;
        const onDocClick = (ev: MouseEvent) => {
            if (popoverRef.current && !popoverRef.current.contains(ev.target as Node)) {
                setOpen(false);
            }
        };
        window.setTimeout(() => document.addEventListener("click", onDocClick), 0);
        return () => document.removeEventListener("click", onDocClick);
    }, [open]);

    const reset = useCallback(() => {
        setSentiment(null);
        setCategory("unspecified");
        setComment("");
    }, []);

    const handleSubmit = useCallback(async () => {
        if (!sentiment) return;
        setSubmitting(true);
        try {
            await submit({
                correlation_id: correlationId,
                component_id: componentId,
                source_agent: sourceAgent,
                source_tool: sourceTool,
                sentiment,
                category,
                comment: comment.trim() ? comment.trim() : null,
            });
            setOpen(false);
            reset();
        } catch (err) {
            console.warn("feedback submit failed", err);
        } finally {
            setSubmitting(false);
        }
    }, [sentiment, category, comment, correlationId, componentId, sourceAgent, sourceTool, submit, reset]);

    return (
        <div className="feedback-control" data-feedback-control style={{ position: "relative" }}>
            <button
                type="button"
                className={`feedback-trigger ${className ?? ""}`.trim()}
                aria-label="Provide feedback on this component"
                onClick={(e) => {
                    e.stopPropagation();
                    setOpen((v) => !v);
                }}
                style={triggerStyle}
            >
                💬
            </button>

            {open && (
                <div ref={popoverRef} role="dialog" aria-label="Component feedback" style={popoverStyle}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
                        <button
                            type="button"
                            aria-label="Thumbs up"
                            onClick={() => setSentiment("positive")}
                            style={{
                                ...sentimentBtnStyle,
                                background: sentiment === "positive" ? "#1c4532" : "#1f2937",
                                borderColor: sentiment === "positive" ? "#48bb78" : "#374151",
                            }}
                        >
                            👍
                        </button>
                        <button
                            type="button"
                            aria-label="Thumbs down"
                            onClick={() => setSentiment("negative")}
                            style={{
                                ...sentimentBtnStyle,
                                background: sentiment === "negative" ? "#742a2a" : "#1f2937",
                                borderColor: sentiment === "negative" ? "#f56565" : "#374151",
                            }}
                        >
                            👎
                        </button>
                    </div>

                    <label style={labelStyle}>What was wrong (optional)?</label>
                    <select
                        value={category}
                        onChange={(e) => setCategory(e.target.value as Category)}
                        style={selectStyle}
                    >
                        {CATEGORIES.map((c) => (
                            <option key={c} value={c}>
                                {CATEGORY_LABELS[c]}
                            </option>
                        ))}
                    </select>

                    <label style={labelStyle}>Comment (optional)</label>
                    <textarea
                        value={comment}
                        onChange={(e) => setComment(e.target.value)}
                        rows={3}
                        maxLength={2048}
                        placeholder="What went wrong, or what would have helped?"
                        style={textareaStyle}
                    />

                    <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
                        <button type="button" onClick={() => { setOpen(false); reset(); }} style={cancelBtnStyle}>
                            Cancel
                        </button>
                        <button
                            type="button"
                            onClick={handleSubmit}
                            disabled={!sentiment || submitting}
                            style={{
                                ...submitBtnStyle,
                                opacity: sentiment && !submitting ? 1 : 0.6,
                                cursor: sentiment && !submitting ? "pointer" : "not-allowed",
                            }}
                        >
                            {submitting ? "Sending…" : "Send feedback"}
                        </button>
                    </div>
                </div>
            )}

            {toast && (
                <div role="status" style={{
                    ...toastStyle,
                    background: toast.kind === "error"
                        ? "#742a2a"
                        : toast.kind === "quarantined" ? "#5b3d09" : "#1c4532",
                }}>
                    {toast.message}
                </div>
            )}
        </div>
    );
}

// ----- inline styles (intentionally minimal — no new theme assets) -----
const triggerStyle: React.CSSProperties = {
    background: "rgba(31, 41, 55, 0.85)",
    color: "#e5e7eb",
    border: "1px solid #374151",
    borderRadius: 999,
    width: 28,
    height: 28,
    fontSize: 13,
    cursor: "pointer",
    padding: 0,
    lineHeight: 1,
};

const popoverStyle: React.CSSProperties = {
    position: "absolute",
    right: 0,
    top: 36,
    width: 280,
    background: "#0b1020",
    color: "#e5e7eb",
    border: "1px solid #374151",
    borderRadius: 8,
    padding: 12,
    boxShadow: "0 12px 32px rgba(0,0,0,0.45)",
    zIndex: 9999,
    fontSize: 13,
};

const sentimentBtnStyle: React.CSSProperties = {
    border: "1px solid",
    borderRadius: 6,
    width: 44,
    height: 32,
    cursor: "pointer",
    fontSize: 16,
    color: "inherit",
};

const labelStyle: React.CSSProperties = {
    display: "block",
    fontSize: 11,
    color: "#9ca3af",
    marginTop: 6,
    marginBottom: 4,
};

const selectStyle: React.CSSProperties = {
    width: "100%",
    background: "#1f2937",
    color: "#e5e7eb",
    border: "1px solid #374151",
    borderRadius: 6,
    padding: "6px 8px",
};

const textareaStyle: React.CSSProperties = {
    width: "100%",
    background: "#1f2937",
    color: "#e5e7eb",
    border: "1px solid #374151",
    borderRadius: 6,
    padding: "6px 8px",
    resize: "vertical",
    fontFamily: "inherit",
};

const cancelBtnStyle: React.CSSProperties = {
    background: "transparent",
    color: "#9ca3af",
    border: "1px solid #374151",
    borderRadius: 6,
    padding: "6px 12px",
    cursor: "pointer",
};

const submitBtnStyle: React.CSSProperties = {
    background: "#3b82f6",
    color: "#fff",
    border: "1px solid #2563eb",
    borderRadius: 6,
    padding: "6px 12px",
};

const toastStyle: React.CSSProperties = {
    position: "absolute",
    right: 0,
    top: 36,
    color: "#e5e7eb",
    border: "1px solid #374151",
    borderRadius: 6,
    padding: "6px 10px",
    fontSize: 12,
    boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
    zIndex: 9998,
    maxWidth: 240,
};
