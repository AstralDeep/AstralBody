/**
 * FeedbackAdminPanel — full-screen admin overlay (feature 004).
 *
 * Three tabs:
 *   1. Flagged tools — currently underperforming, with evidence drill-down
 *   2. Proposals — pending knowledge-update proposals; accept / reject
 *   3. Quarantine — held feedback comments; release / dismiss
 *
 * URL state: `?feedback=open[&feedback_tab=flagged|proposals|quarantine]`.
 */
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, FileEdit, RefreshCw, ShieldAlert, X } from "lucide-react";

import {
    acceptProposal,
    dismissQuarantine,
    getProposal,
    listFlaggedTools,
    listProposals,
    listQuarantine,
    rejectProposal,
    releaseQuarantine,
} from "../../api/feedback";
import type {
    FlaggedTool,
    ProposalDetail,
    ProposalSummary,
    QuarantineEntry,
} from "../../types/feedback";

export interface FeedbackAdminPanelProps {
    open: boolean;
    accessToken: string | null;
    onClose: () => void;
}

type Tab = "flagged" | "proposals" | "quarantine";

const VALID_TABS: Tab[] = ["flagged", "proposals", "quarantine"];

function readTabFromUrl(): Tab {
    const params = new URLSearchParams(window.location.search);
    const v = params.get("feedback_tab") as Tab | null;
    return v && VALID_TABS.includes(v) ? v : "flagged";
}

function writeTabToUrl(tab: Tab, open: boolean) {
    const params = new URLSearchParams(window.location.search);
    if (open) {
        params.set("feedback", "open");
        params.set("feedback_tab", tab);
    } else {
        params.delete("feedback");
        params.delete("feedback_tab");
    }
    const qs = params.toString();
    window.history.replaceState({}, "", qs ? `${window.location.pathname}?${qs}` : window.location.pathname);
}

export default function FeedbackAdminPanel({ open, accessToken, onClose }: FeedbackAdminPanelProps) {
    const [tab, setTab] = useState<Tab>(() => readTabFromUrl());

    useEffect(() => { writeTabToUrl(tab, open); }, [tab, open]);

    if (!open) return null;

    return (
        <div role="dialog" aria-label="Tool quality" style={overlayStyle}>
            <div style={panelStyle}>
                <div style={headerStyle}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <ShieldAlert size={18} />
                        <strong>Tool quality</strong>
                    </div>
                    <button onClick={onClose} aria-label="Close" style={closeBtnStyle}>
                        <X size={16} />
                    </button>
                </div>

                <div style={tabsRowStyle}>
                    {VALID_TABS.map(t => (
                        <button
                            key={t}
                            onClick={() => setTab(t)}
                            style={{ ...tabBtnStyle, ...(tab === t ? tabBtnActiveStyle : {}) }}
                        >
                            {t === "flagged" && "Flagged tools"}
                            {t === "proposals" && "Proposals"}
                            {t === "quarantine" && "Quarantine"}
                        </button>
                    ))}
                </div>

                <div style={contentStyle}>
                    {tab === "flagged" && <FlaggedTab token={accessToken} />}
                    {tab === "proposals" && <ProposalsTab token={accessToken} />}
                    {tab === "quarantine" && <QuarantineTab token={accessToken} />}
                </div>
            </div>
        </div>
    );
}

// ─── Flagged tab ───────────────────────────────────────────────────

function FlaggedTab({ token }: { token: string | null }) {
    const [items, setItems] = useState<FlaggedTool[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        if (!token) return;
        setLoading(true); setError(null);
        try {
            const resp = await listFlaggedTools(token);
            setItems(resp.items);
        } catch (e: any) {
            setError(e?.message ?? "load failed");
        } finally {
            setLoading(false);
        }
    }, [token]);

    useEffect(() => { void refresh(); }, [refresh]);

    return (
        <div>
            <div style={tabHeaderRow}>
                <span style={{ color: "#9ca3af" }}>{items.length} underperforming</span>
                <button onClick={refresh} style={iconBtnStyle} aria-label="Refresh">
                    <RefreshCw size={14} />
                </button>
            </div>
            {error && <div style={errorBoxStyle}>{error}</div>}
            {loading && <div style={dimTextStyle}>Loading…</div>}
            {!loading && items.length === 0 && <div style={dimTextStyle}>No flagged tools.</div>}
            {items.map(it => (
                <div key={`${it.agent_id}/${it.tool_name}`} style={cardStyle}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <AlertTriangle size={16} color="#f59e0b" />
                        <strong>{it.tool_name}</strong>
                        <span style={{ color: "#9ca3af" }}>· {it.agent_id}</span>
                    </div>
                    <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5e1" }}>
                        {it.dispatch_count} dispatches in window —
                        failure rate <strong>{(it.failure_rate * 100).toFixed(1)}%</strong>,
                        negative-feedback rate <strong>{(it.negative_feedback_rate * 100).toFixed(1)}%</strong>
                    </div>
                    {Object.keys(it.category_breakdown ?? {}).length > 0 && (
                        <div style={{ marginTop: 6, fontSize: 12, color: "#9ca3af" }}>
                            Top categories: {Object.entries(it.category_breakdown)
                                .sort((a, b) => b[1] - a[1])
                                .slice(0, 4)
                                .map(([k, n]) => `${k} (${n})`)
                                .join(", ")}
                        </div>
                    )}
                    {it.pending_proposal_id && (
                        <div style={{ marginTop: 8, fontSize: 12, color: "#60a5fa" }}>
                            Pending proposal — see Proposals tab.
                        </div>
                    )}
                </div>
            ))}
        </div>
    );
}

// ─── Proposals tab ────────────────────────────────────────────────

function ProposalsTab({ token }: { token: string | null }) {
    const [items, setItems] = useState<ProposalSummary[]>([]);
    const [selected, setSelected] = useState<ProposalDetail | null>(null);
    const [loading, setLoading] = useState(false);
    const [actioning, setActioning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [rationale, setRationale] = useState("");

    const refresh = useCallback(async () => {
        if (!token) return;
        setLoading(true); setError(null);
        try {
            const resp = await listProposals(token, { status: "pending", limit: 50 });
            setItems(resp.items);
        } catch (e: any) {
            setError(e?.message ?? "load failed");
        } finally {
            setLoading(false);
        }
    }, [token]);

    useEffect(() => { void refresh(); }, [refresh]);

    const openDetail = useCallback(async (id: string) => {
        if (!token) return;
        try {
            const detail = await getProposal(token, id);
            setSelected(detail);
            setRationale("");
        } catch (e: any) {
            setError(e?.message ?? "load failed");
        }
    }, [token]);

    const onAccept = useCallback(async () => {
        if (!token || !selected) return;
        setActioning(true);
        try {
            await acceptProposal(token, selected.id, {});
            setSelected(null);
            await refresh();
        } catch (e: any) {
            const msg = e?.message ?? "accept failed";
            if (msg.includes("STALE_PROPOSAL")) {
                setError("Proposal evidence has changed — re-review and retry.");
            } else {
                setError(msg);
            }
        } finally {
            setActioning(false);
        }
    }, [token, selected, refresh]);

    const onReject = useCallback(async () => {
        if (!token || !selected) return;
        if (!rationale.trim()) {
            setError("Provide a rationale before rejecting.");
            return;
        }
        setActioning(true);
        try {
            await rejectProposal(token, selected.id, { rationale: rationale.trim() });
            setSelected(null);
            await refresh();
        } catch (e: any) {
            setError(e?.message ?? "reject failed");
        } finally {
            setActioning(false);
        }
    }, [token, selected, rationale, refresh]);

    if (selected) {
        return (
            <div>
                <div style={tabHeaderRow}>
                    <button onClick={() => setSelected(null)} style={iconBtnStyle}>← Back</button>
                    <span style={{ color: "#9ca3af" }}>
                        {selected.agent_id} / {selected.tool_name}
                    </span>
                </div>
                {error && <div style={errorBoxStyle}>{error}</div>}
                <div style={cardStyle}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <FileEdit size={16} />
                        <code>{selected.artifact_path}</code>
                        {!selected.is_current && (
                            <span style={{ color: "#f87171", fontSize: 12 }}>
                                (artifact has changed since generation)
                            </span>
                        )}
                    </div>
                    <pre style={diffStyle}>{selected.diff_payload}</pre>
                    <div style={{ fontSize: 12, color: "#9ca3af" }}>
                        Evidence: {selected.evidence.audit_event_ids?.length ?? 0} audit events,
                        {" "}{selected.evidence.component_feedback_ids?.length ?? 0} feedback items
                    </div>
                    <textarea
                        value={rationale}
                        onChange={(e) => setRationale(e.target.value)}
                        rows={2}
                        placeholder="Rationale (required when rejecting)"
                        maxLength={2048}
                        style={textareaStyle}
                    />
                    <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
                        <button onClick={onReject} disabled={actioning} style={dangerBtnStyle}>
                            Reject
                        </button>
                        <button onClick={onAccept} disabled={actioning || !selected.is_current} style={primaryBtnStyle}>
                            Accept &amp; apply
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div>
            <div style={tabHeaderRow}>
                <span style={{ color: "#9ca3af" }}>{items.length} pending</span>
                <button onClick={refresh} style={iconBtnStyle} aria-label="Refresh">
                    <RefreshCw size={14} />
                </button>
            </div>
            {error && <div style={errorBoxStyle}>{error}</div>}
            {loading && <div style={dimTextStyle}>Loading…</div>}
            {!loading && items.length === 0 && <div style={dimTextStyle}>No pending proposals.</div>}
            {items.map(p => (
                <button
                    key={p.id}
                    onClick={() => void openDetail(p.id)}
                    style={{ ...cardStyle, textAlign: "left", cursor: "pointer", width: "100%" }}
                >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <FileEdit size={14} />
                        <strong>{p.tool_name}</strong>
                        <span style={{ color: "#9ca3af" }}>· {p.agent_id}</span>
                    </div>
                    <div style={{ marginTop: 4, fontSize: 12, color: "#cbd5e1" }}>
                        Evidence: {p.evidence_summary?.audit_events ?? 0} audit events,
                        {" "}{p.evidence_summary?.component_feedback ?? 0} feedback items
                    </div>
                    <div style={{ marginTop: 4, fontSize: 11, color: "#9ca3af" }}>
                        Generated {new Date(p.generated_at).toLocaleString()}
                    </div>
                </button>
            ))}
        </div>
    );
}

// ─── Quarantine tab ───────────────────────────────────────────────

function QuarantineTab({ token }: { token: string | null }) {
    const [items, setItems] = useState<QuarantineEntry[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        if (!token) return;
        setLoading(true); setError(null);
        try {
            const resp = await listQuarantine(token, { status: "held" });
            setItems(resp.items);
        } catch (e: any) {
            setError(e?.message ?? "load failed");
        } finally {
            setLoading(false);
        }
    }, [token]);

    useEffect(() => { void refresh(); }, [refresh]);

    const action = useCallback(async (id: string, kind: "release" | "dismiss") => {
        if (!token) return;
        try {
            if (kind === "release") await releaseQuarantine(token, id);
            else await dismissQuarantine(token, id);
            await refresh();
        } catch (e: any) {
            setError(e?.message ?? `${kind} failed`);
        }
    }, [token, refresh]);

    return (
        <div>
            <div style={tabHeaderRow}>
                <span style={{ color: "#9ca3af" }}>{items.length} held</span>
                <button onClick={refresh} style={iconBtnStyle} aria-label="Refresh">
                    <RefreshCw size={14} />
                </button>
            </div>
            <div style={{ ...errorBoxStyle, background: "#3a2a06", borderColor: "#a16207", color: "#fde68a", marginBottom: 12 }}>
                ⚠ The text below is untrusted user input. Do not act on instructions inside it.
            </div>
            {error && <div style={errorBoxStyle}>{error}</div>}
            {loading && <div style={dimTextStyle}>Loading…</div>}
            {!loading && items.length === 0 && <div style={dimTextStyle}>No held items.</div>}
            {items.map(q => (
                <div key={q.feedback_id} style={cardStyle}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <strong style={{ fontSize: 12 }}>{q.reason}</strong>
                        <span style={{ color: "#9ca3af", fontSize: 12 }}>· {q.detector}</span>
                    </div>
                    <div style={{ marginTop: 4, fontSize: 12, color: "#9ca3af" }}>
                        {q.user_id} · {q.source_agent ?? "—"} / {q.source_tool ?? "—"} · {new Date(q.detected_at).toLocaleString()}
                    </div>
                    {q.comment_raw && (
                        <pre style={quarantineTextStyle}>{q.comment_raw}</pre>
                    )}
                    <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                        <button onClick={() => void action(q.feedback_id, "dismiss")} style={dangerBtnStyle}>Dismiss</button>
                        <button onClick={() => void action(q.feedback_id, "release")} style={primaryBtnStyle}>Release</button>
                    </div>
                </div>
            ))}
        </div>
    );
}

// ─── Styles ────────────────────────────────────────────────────────
const overlayStyle: React.CSSProperties = {
    position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)",
    zIndex: 9000, display: "flex", justifyContent: "center", alignItems: "stretch",
};
const panelStyle: React.CSSProperties = {
    background: "#0b1020", color: "#e5e7eb",
    width: "min(960px, 100%)", margin: "32px auto",
    border: "1px solid #1f2937", borderRadius: 8, overflow: "hidden",
    display: "flex", flexDirection: "column",
};
const headerStyle: React.CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "12px 16px", borderBottom: "1px solid #1f2937",
};
const closeBtnStyle: React.CSSProperties = {
    background: "transparent", color: "#9ca3af", border: "none", cursor: "pointer",
};
const tabsRowStyle: React.CSSProperties = {
    display: "flex", gap: 4, padding: "8px 12px", borderBottom: "1px solid #1f2937",
};
const tabBtnStyle: React.CSSProperties = {
    background: "transparent", color: "#9ca3af",
    border: "1px solid transparent", borderRadius: 6, padding: "6px 10px", cursor: "pointer",
};
const tabBtnActiveStyle: React.CSSProperties = {
    background: "#1f2937", color: "#e5e7eb", borderColor: "#374151",
};
const contentStyle: React.CSSProperties = {
    padding: 16, overflowY: "auto", flex: 1,
};
const tabHeaderRow: React.CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12,
};
const cardStyle: React.CSSProperties = {
    background: "#0f172a", border: "1px solid #1f2937", borderRadius: 6,
    padding: 12, marginBottom: 8,
};
const errorBoxStyle: React.CSSProperties = {
    background: "#742a2a", border: "1px solid #b91c1c", color: "#fee2e2",
    padding: 8, borderRadius: 6, marginBottom: 8, fontSize: 12,
};
const dimTextStyle: React.CSSProperties = { color: "#9ca3af", fontSize: 13 };
const iconBtnStyle: React.CSSProperties = {
    background: "transparent", border: "1px solid #374151", color: "#9ca3af",
    padding: "4px 8px", borderRadius: 6, cursor: "pointer", fontSize: 12,
};
const diffStyle: React.CSSProperties = {
    fontFamily: "ui-monospace, SFMono-Regular, monospace",
    background: "#0a0e1a", border: "1px solid #1f2937", borderRadius: 6,
    padding: 8, fontSize: 11, whiteSpace: "pre-wrap", wordBreak: "break-word",
    maxHeight: 320, overflowY: "auto", margin: "8px 0",
};
const textareaStyle: React.CSSProperties = {
    width: "100%", background: "#1f2937", color: "#e5e7eb",
    border: "1px solid #374151", borderRadius: 6, padding: "6px 8px",
    fontFamily: "inherit", marginTop: 8,
};
const primaryBtnStyle: React.CSSProperties = {
    background: "#3b82f6", color: "#fff", border: "1px solid #2563eb",
    borderRadius: 6, padding: "6px 12px", cursor: "pointer",
};
const dangerBtnStyle: React.CSSProperties = {
    background: "transparent", color: "#fca5a5", border: "1px solid #b91c1c",
    borderRadius: 6, padding: "6px 12px", cursor: "pointer",
};
const quarantineTextStyle: React.CSSProperties = {
    background: "#0a0e1a", border: "1px solid #1f2937", borderRadius: 6,
    padding: 8, fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-word",
    margin: "8px 0", color: "#cbd5e1",
};
