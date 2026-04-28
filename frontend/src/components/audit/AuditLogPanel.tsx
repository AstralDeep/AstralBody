/**
 * AuditLogPanel — full-screen overlay that lists, filters, and drills
 * into the user's audit log.
 *
 * The project has no router, so this panel is the equivalent of the
 * spec's "dedicated route" (FR-005). Filter and selection state is
 * reflected in the URL query string (``?audit=open&q=...&class=...``)
 * so refreshing or sharing the URL restores the same view. Server-side
 * filtering is the only filter for ``audit_append`` events
 * (FR-007 / FR-019); this panel listens for them via the
 * ``audit:append`` window event.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { ListChecks, RefreshCw, ShieldCheck, X } from "lucide-react";

import AuditDetailDrawer from "./AuditDetailDrawer";
import AuditEntryRow from "./AuditEntryRow";
import AuditFilters from "./AuditFilters";
import { useAuditStream } from "../../hooks/useAuditStream";
import type {
    AuditEvent,
    AuditEventClass,
    AuditListFilters,
    AuditOutcome,
} from "../../types/audit";

export interface AuditLogPanelProps {
    open: boolean;
    accessToken: string | undefined;
    onClose: () => void;
}

const VALID_EVENT_CLASSES: AuditEventClass[] = [
    "auth",
    "conversation",
    "file",
    "settings",
    "agent_tool_call",
    "agent_ui_render",
    "agent_external_call",
    "audit_view",
];
const VALID_OUTCOMES: AuditOutcome[] = ["in_progress", "success", "failure", "interrupted"];

function readFiltersFromUrl(): AuditListFilters {
    const params = new URLSearchParams(window.location.search);
    const ec = params.getAll("class").filter((v): v is AuditEventClass =>
        VALID_EVENT_CLASSES.includes(v as AuditEventClass),
    );
    const oc = params.getAll("outcome").filter((v): v is AuditOutcome =>
        VALID_OUTCOMES.includes(v as AuditOutcome),
    );
    const q = params.get("audit_q") ?? undefined;
    const from = params.get("audit_from") ?? undefined;
    const to = params.get("audit_to") ?? undefined;
    return {
        event_class: ec.length ? ec : undefined,
        outcome: oc.length ? oc : undefined,
        q: q || undefined,
        from: from || undefined,
        to: to || undefined,
    };
}

function writeFiltersToUrl(filters: AuditListFilters, open: boolean, selectedId: string | null) {
    const params = new URLSearchParams(window.location.search);
    params.delete("class");
    params.delete("outcome");
    params.delete("audit_q");
    params.delete("audit_from");
    params.delete("audit_to");
    params.delete("audit");
    params.delete("audit_id");
    if (open) params.set("audit", "open");
    for (const c of filters.event_class ?? []) params.append("class", c);
    for (const o of filters.outcome ?? []) params.append("outcome", o);
    if (filters.q) params.set("audit_q", filters.q);
    if (filters.from) params.set("audit_from", filters.from);
    if (filters.to) params.set("audit_to", filters.to);
    if (selectedId) params.set("audit_id", selectedId);
    const qs = params.toString();
    const newUrl = qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
    window.history.replaceState({}, "", newUrl);
}

export default function AuditLogPanel({ open, accessToken, onClose }: AuditLogPanelProps) {
    const [filters, setFilters] = useState<AuditListFilters>(() => readFiltersFromUrl());
    const [selectedId, setSelectedId] = useState<string | null>(() => {
        const params = new URLSearchParams(window.location.search);
        return params.get("audit_id");
    });

    const { items, nextCursor, isLoading, error, refresh, loadMore } = useAuditStream(
        accessToken,
        filters,
    );

    // Reflect open / filters / selected in URL whenever they change
    useEffect(() => {
        writeFiltersToUrl(filters, open, selectedId);
    }, [filters, open, selectedId]);

    const handleClose = useCallback(() => {
        setSelectedId(null);
        onClose();
    }, [onClose]);

    const handleSelect = useCallback((entry: AuditEvent) => {
        setSelectedId(entry.event_id);
    }, []);

    const initialEntry = useMemo(
        () => (selectedId ? items.find((e) => e.event_id === selectedId) ?? null : null),
        [selectedId, items],
    );

    if (!open) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={handleClose}>
            <div
                className="bg-astral-surface border border-white/10 rounded-xl shadow-2xl w-full max-w-5xl mx-4 max-h-[90vh] flex flex-col"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-astral-primary/20 flex items-center justify-center">
                            <ListChecks size={16} className="text-astral-primary" />
                        </div>
                        <div>
                            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                                Audit log
                                <span className="text-[10px] px-1.5 py-0.5 rounded border border-white/10 text-astral-muted flex items-center gap-1">
                                    <ShieldCheck size={10} /> per-user
                                </span>
                            </h2>
                            <p className="text-[11px] text-astral-muted">
                                Every action recorded for you. HIPAA + NIST AU compliant.
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <button
                            type="button"
                            onClick={() => void refresh()}
                            disabled={isLoading}
                            className="flex items-center gap-1.5 text-[11px] px-2 py-1.5 rounded-lg border border-white/10 hover:bg-white/5 disabled:opacity-50"
                            aria-label="Refresh audit log"
                        >
                            <RefreshCw size={12} className={isLoading ? "animate-spin" : ""} />
                            Refresh
                        </button>
                        <button
                            type="button"
                            onClick={handleClose}
                            className="p-1.5 rounded-lg hover:bg-white/10"
                            aria-label="Close audit log"
                        >
                            <X size={14} className="text-astral-muted" />
                        </button>
                    </div>
                </div>

                {/* Filters */}
                <div className="px-6 py-4 border-b border-white/5">
                    <AuditFilters filters={filters} onChange={setFilters} />
                </div>

                {/* List */}
                <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
                    {error && (
                        <div className="px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-300">
                            {error}
                        </div>
                    )}
                    {!error && items.length === 0 && !isLoading && (
                        <div className="flex flex-col items-center justify-center py-16 text-astral-muted">
                            <ListChecks size={28} className="mb-3 opacity-40" />
                            <p className="text-sm">No audit entries match the current filters.</p>
                            <p className="text-[11px] mt-1 opacity-70">
                                Trigger an action and watch it appear here in real time.
                            </p>
                        </div>
                    )}
                    {items.map((entry) => (
                        <AuditEntryRow
                            key={entry.event_id}
                            entry={entry}
                            onSelect={handleSelect}
                            isSelected={entry.event_id === selectedId}
                        />
                    ))}
                    {nextCursor && (
                        <button
                            type="button"
                            onClick={() => void loadMore()}
                            disabled={isLoading}
                            className="w-full text-[11px] text-astral-muted hover:text-white py-2 rounded-lg border border-white/10 hover:bg-white/5 disabled:opacity-50"
                        >
                            {isLoading ? "Loading…" : "Load more"}
                        </button>
                    )}
                </div>
            </div>

            <AuditDetailDrawer
                eventId={selectedId}
                accessToken={accessToken}
                initialEntry={initialEntry}
                onClose={() => setSelectedId(null)}
            />
        </div>
    );
}
