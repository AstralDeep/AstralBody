/**
 * AuditFilters — chip-based filter UI.
 *
 * Applies to event_class, outcome, date range, and keyword. The
 * component is purely controlled — its parent owns the AuditListFilters
 * state and reflects it in the URL query string.
 */
import { Search, X } from "lucide-react";
import { useState, useEffect } from "react";

import type {
    AuditEventClass,
    AuditListFilters,
    AuditOutcome,
} from "../../types/audit";

const ALL_CLASSES: { value: AuditEventClass; label: string }[] = [
    { value: "auth", label: "Auth" },
    { value: "conversation", label: "Conversation" },
    { value: "file", label: "File" },
    { value: "settings", label: "Settings" },
    { value: "agent_tool_call", label: "Tool call" },
    { value: "agent_ui_render", label: "UI render" },
    { value: "agent_external_call", label: "External" },
    { value: "audit_view", label: "Audit view" },
];

const ALL_OUTCOMES: { value: AuditOutcome; label: string }[] = [
    { value: "success", label: "Success" },
    { value: "failure", label: "Failure" },
    { value: "interrupted", label: "Interrupted" },
    { value: "in_progress", label: "In progress" },
];

export interface AuditFiltersProps {
    filters: AuditListFilters;
    onChange: (filters: AuditListFilters) => void;
}

export default function AuditFilters({ filters, onChange }: AuditFiltersProps) {
    const [keywordDraft, setKeywordDraft] = useState(filters.q ?? "");

    useEffect(() => {
        setKeywordDraft(filters.q ?? "");
    }, [filters.q]);

    const toggleClass = (value: AuditEventClass) => {
        const current = new Set(filters.event_class ?? []);
        if (current.has(value)) {
            current.delete(value);
        } else {
            current.add(value);
        }
        onChange({ ...filters, event_class: Array.from(current), cursor: undefined });
    };

    const toggleOutcome = (value: AuditOutcome) => {
        const current = new Set(filters.outcome ?? []);
        if (current.has(value)) {
            current.delete(value);
        } else {
            current.add(value);
        }
        onChange({ ...filters, outcome: Array.from(current), cursor: undefined });
    };

    const submitKeyword = () => {
        const next = keywordDraft.trim();
        onChange({ ...filters, q: next || undefined, cursor: undefined });
    };

    const clearAll = () => {
        setKeywordDraft("");
        onChange({});
    };

    const hasAny =
        (filters.event_class && filters.event_class.length > 0) ||
        (filters.outcome && filters.outcome.length > 0) ||
        filters.q ||
        filters.from ||
        filters.to;

    return (
        <div className="space-y-3">
            <div className="flex items-center gap-2">
                <div className="flex-1 flex items-center gap-2 bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 focus-within:border-astral-primary/40">
                    <Search size={12} className="text-astral-muted/60 flex-shrink-0" />
                    <input
                        type="text"
                        name="audit-keyword"
                        value={keywordDraft}
                        onChange={(e) => setKeywordDraft(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter") submitKeyword();
                        }}
                        onBlur={submitKeyword}
                        placeholder="Search description or action…"
                        className="bg-transparent text-xs text-white placeholder:text-astral-muted/40 focus:outline-none w-full"
                        autoComplete="off"
                    />
                    {keywordDraft && (
                        <button
                            type="button"
                            onClick={() => {
                                setKeywordDraft("");
                                onChange({ ...filters, q: undefined, cursor: undefined });
                            }}
                            className="text-astral-muted/60 hover:text-white"
                            aria-label="Clear keyword"
                        >
                            <X size={10} />
                        </button>
                    )}
                </div>
                {hasAny && (
                    <button
                        type="button"
                        onClick={clearAll}
                        className="text-[11px] text-astral-muted hover:text-white px-2 py-1.5 rounded-lg border border-white/10 hover:bg-white/5"
                    >
                        Clear filters
                    </button>
                )}
            </div>

            <div className="flex flex-wrap gap-1.5">
                <span className="text-[10px] uppercase tracking-widest text-astral-muted self-center mr-1">Class</span>
                {ALL_CLASSES.map((c) => {
                    const active = filters.event_class?.includes(c.value);
                    return (
                        <button
                            key={c.value}
                            type="button"
                            onClick={() => toggleClass(c.value)}
                            className={`text-[11px] px-2 py-1 rounded-full border transition-colors ${
                                active
                                    ? "bg-astral-primary/20 border-astral-primary/40 text-white"
                                    : "bg-white/[0.02] border-white/10 text-astral-muted hover:bg-white/5"
                            }`}
                        >
                            {c.label}
                        </button>
                    );
                })}
            </div>

            <div className="flex flex-wrap gap-1.5">
                <span className="text-[10px] uppercase tracking-widest text-astral-muted self-center mr-1">Outcome</span>
                {ALL_OUTCOMES.map((o) => {
                    const active = filters.outcome?.includes(o.value);
                    return (
                        <button
                            key={o.value}
                            type="button"
                            onClick={() => toggleOutcome(o.value)}
                            className={`text-[11px] px-2 py-1 rounded-full border transition-colors ${
                                active
                                    ? "bg-astral-primary/20 border-astral-primary/40 text-white"
                                    : "bg-white/[0.02] border-white/10 text-astral-muted hover:bg-white/5"
                            }`}
                        >
                            {o.label}
                        </button>
                    );
                })}
            </div>

            <div className="flex flex-wrap items-center gap-2 text-[11px]">
                <span className="text-[10px] uppercase tracking-widest text-astral-muted mr-1">Date</span>
                <label className="text-astral-muted">From
                    <input
                        type="date"
                        value={filters.from ? filters.from.slice(0, 10) : ""}
                        onChange={(e) =>
                            onChange({
                                ...filters,
                                from: e.target.value ? `${e.target.value}T00:00:00Z` : undefined,
                                cursor: undefined,
                            })
                        }
                        className="ml-2 bg-white/5 border border-white/10 rounded px-2 py-1 text-white"
                    />
                </label>
                <label className="text-astral-muted">To
                    <input
                        type="date"
                        value={filters.to ? filters.to.slice(0, 10) : ""}
                        onChange={(e) =>
                            onChange({
                                ...filters,
                                to: e.target.value ? `${e.target.value}T23:59:59Z` : undefined,
                                cursor: undefined,
                            })
                        }
                        className="ml-2 bg-white/5 border border-white/10 rounded px-2 py-1 text-white"
                    />
                </label>
            </div>
        </div>
    );
}
