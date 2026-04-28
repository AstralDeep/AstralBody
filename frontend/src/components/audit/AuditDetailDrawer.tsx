/**
 * AuditDetailDrawer — full-detail view of a single audit entry.
 *
 * Refetches the entry by id when opened so ``artifact_pointers[].available``
 * is recomputed at read time (FR-017). Composed from existing layout
 * primitives + lucide icons; introduces no new design primitive.
 */
import { useEffect, useState } from "react";
import { ExternalLink, FileText, Hourglass, X } from "lucide-react";

import { getAudit } from "../../api/audit";
import type { AuditEvent } from "../../types/audit";

export interface AuditDetailDrawerProps {
    eventId: string | null;
    accessToken: string | undefined;
    initialEntry?: AuditEvent | null;
    onClose: () => void;
}

function fmt(iso: string | null | undefined): string {
    if (!iso) return "—";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export default function AuditDetailDrawer({
    eventId,
    accessToken,
    initialEntry,
    onClose,
}: AuditDetailDrawerProps) {
    const [detail, setDetail] = useState<AuditEvent | null>(initialEntry ?? null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!eventId || !accessToken) return;
        let cancelled = false;
        setLoading(true);
        setError(null);
        // Refetch on every open so artifact `available` is current
        getAudit(accessToken, eventId)
            .then((d) => {
                if (!cancelled) setDetail(d);
            })
            .catch((e) => {
                if (!cancelled) setError(e instanceof Error ? e.message : String(e));
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [eventId, accessToken]);

    if (!eventId) return null;

    return (
        <div
            className="fixed inset-0 z-[60] flex justify-end bg-black/40 backdrop-blur-sm"
            onClick={onClose}
        >
            <div
                className="bg-astral-surface border-l border-white/10 w-full max-w-md h-full overflow-y-auto"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between px-5 py-4 border-b border-white/5 sticky top-0 bg-astral-surface/95 backdrop-blur z-10">
                    <h3 className="text-sm font-semibold text-white">Audit entry</h3>
                    <button
                        onClick={onClose}
                        className="p-1.5 rounded-lg hover:bg-white/10"
                        aria-label="Close detail"
                    >
                        <X size={14} className="text-astral-muted" />
                    </button>
                </div>

                {loading && !detail && (
                    <div className="px-5 py-12 flex items-center justify-center text-astral-muted gap-2">
                        <Hourglass size={14} className="animate-pulse" />
                        Loading…
                    </div>
                )}
                {error && (
                    <div className="px-5 py-6 text-xs text-red-300">
                        {error}
                    </div>
                )}

                {detail && (
                    <div className="px-5 py-4 space-y-5 text-xs text-astral-muted">
                        <Section label="Description">
                            <p className="text-sm text-white">{detail.description}</p>
                        </Section>

                        <KvGrid>
                            <Kv k="Class" v={detail.event_class} />
                            <Kv k="Action" v={detail.action_type} />
                            <Kv k="Outcome" v={detail.outcome} />
                            {detail.outcome_detail && (
                                <Kv k="Detail" v={detail.outcome_detail} wide />
                            )}
                            {detail.agent_id && <Kv k="Agent" v={detail.agent_id} />}
                            {detail.conversation_id && <Kv k="Chat" v={detail.conversation_id} />}
                            <Kv k="Started" v={fmt(detail.started_at)} />
                            <Kv k="Completed" v={fmt(detail.completed_at)} />
                            <Kv k="Recorded" v={fmt(detail.recorded_at)} />
                            <Kv k="Event id" v={detail.event_id} mono />
                            <Kv k="Correlation id" v={detail.correlation_id} mono />
                        </KvGrid>

                        {Object.keys(detail.inputs_meta || {}).length > 0 && (
                            <Section label="Inputs">
                                <pre className="bg-white/[0.04] border border-white/5 rounded-lg p-3 text-[11px] text-astral-muted overflow-x-auto">
                                    {JSON.stringify(detail.inputs_meta, null, 2)}
                                </pre>
                            </Section>
                        )}
                        {Object.keys(detail.outputs_meta || {}).length > 0 && (
                            <Section label="Outputs">
                                <pre className="bg-white/[0.04] border border-white/5 rounded-lg p-3 text-[11px] text-astral-muted overflow-x-auto">
                                    {JSON.stringify(detail.outputs_meta, null, 2)}
                                </pre>
                            </Section>
                        )}

                        {detail.artifact_pointers && detail.artifact_pointers.length > 0 && (
                            <Section label="Artifacts">
                                <ul className="space-y-1.5">
                                    {detail.artifact_pointers.map((p) => (
                                        <li
                                            key={`${p.store}:${p.artifact_id}`}
                                            className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-white/[0.03] border border-white/5"
                                        >
                                            <FileText size={12} className="text-astral-muted/70" />
                                            <span className="text-[11px] text-white truncate flex-1">
                                                {p.extension ? `${p.extension.toUpperCase()} · ` : ""}
                                                {p.artifact_id}
                                            </span>
                                            <span
                                                className={`text-[10px] px-1.5 py-0.5 rounded-full border flex items-center gap-1 ${
                                                    p.available
                                                        ? "text-green-300 bg-green-300/10 border-green-300/20"
                                                        : "text-red-300 bg-red-300/10 border-red-300/20"
                                                }`}
                                                title={p.available ? "" : "Source artifact no longer available"}
                                            >
                                                {p.available ? (
                                                    <>
                                                        <ExternalLink size={9} /> available
                                                    </>
                                                ) : (
                                                    "no longer available"
                                                )}
                                            </span>
                                        </li>
                                    ))}
                                </ul>
                            </Section>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div>
            <p className="text-[10px] uppercase tracking-widest text-astral-muted mb-1.5">{label}</p>
            {children}
        </div>
    );
}

function KvGrid({ children }: { children: React.ReactNode }) {
    return <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">{children}</div>;
}

function Kv({ k, v, mono, wide }: { k: string; v: string | null; mono?: boolean; wide?: boolean }) {
    return (
        <div className={wide ? "col-span-2" : ""}>
            <p className="text-[10px] uppercase tracking-widest text-astral-muted/60">{k}</p>
            <p className={`text-xs text-white ${mono ? "font-mono" : ""} truncate`}>{v ?? "—"}</p>
        </div>
    );
}
