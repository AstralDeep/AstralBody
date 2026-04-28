/**
 * Single audit-log row. Composed from existing primitives + lucide
 * icons (consistent with the rest of the app's chrome). No new design
 * primitive is introduced.
 */
import {
    AlertTriangle,
    CheckCircle2,
    Clock,
    LogIn,
    LogOut,
    MessageSquare,
    Paperclip,
    Settings,
    ShieldAlert,
    Wrench,
    Eye,
    Globe2,
    type LucideIcon,
} from "lucide-react";

import type { AuditEvent } from "../../types/audit";

const iconForClass: Record<AuditEvent["event_class"], LucideIcon> = {
    auth: LogIn,
    conversation: MessageSquare,
    file: Paperclip,
    settings: Settings,
    agent_tool_call: Wrench,
    agent_ui_render: MessageSquare,
    agent_external_call: Globe2,
    audit_view: Eye,
};

const outcomeStyle: Record<AuditEvent["outcome"], { icon: LucideIcon; cls: string; label: string }> = {
    in_progress: { icon: Clock, cls: "text-yellow-300 bg-yellow-300/10 border-yellow-300/20", label: "In progress" },
    success: { icon: CheckCircle2, cls: "text-green-300 bg-green-300/10 border-green-300/20", label: "Success" },
    failure: { icon: AlertTriangle, cls: "text-red-300 bg-red-300/10 border-red-300/20", label: "Failure" },
    interrupted: { icon: ShieldAlert, cls: "text-orange-300 bg-orange-300/10 border-orange-300/20", label: "Interrupted" },
};

function formatTimestamp(iso: string): string {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });
}

export interface AuditEntryRowProps {
    entry: AuditEvent;
    onSelect: (entry: AuditEvent) => void;
    isSelected?: boolean;
}

export default function AuditEntryRow({ entry, onSelect, isSelected }: AuditEntryRowProps) {
    const Icon = iconForClass[entry.event_class] ?? Settings;
    const outcomeMeta = outcomeStyle[entry.outcome];
    const OutcomeIcon = outcomeMeta.icon;

    // Logout maps to LogOut icon when action_type indicates disconnect
    const ResolvedIcon =
        entry.event_class === "auth" && entry.action_type.includes("disconnect")
            ? LogOut
            : Icon;

    return (
        <button
            onClick={() => onSelect(entry)}
            className={`w-full flex items-start gap-3 px-3 py-3 rounded-lg border transition-colors text-left ${
                isSelected
                    ? "bg-white/10 border-astral-primary/40"
                    : "bg-white/[0.02] border-white/5 hover:bg-white/5"
            }`}
        >
            <div className="w-8 h-8 rounded-md bg-astral-primary/15 flex items-center justify-center flex-shrink-0 mt-0.5">
                <ResolvedIcon size={14} className="text-astral-primary" />
            </div>
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-white truncate">{entry.description}</p>
                </div>
                <div className="mt-1 flex items-center gap-2 flex-wrap text-[11px] text-astral-muted">
                    <span className="font-mono">{entry.action_type}</span>
                    {entry.agent_id && (
                        <>
                            <span className="opacity-40">·</span>
                            <span className="truncate">agent {entry.agent_id}</span>
                        </>
                    )}
                    {entry.conversation_id && (
                        <>
                            <span className="opacity-40">·</span>
                            <span className="truncate">chat {entry.conversation_id.slice(0, 8)}</span>
                        </>
                    )}
                    <span className="opacity-40">·</span>
                    <span>{formatTimestamp(entry.recorded_at)}</span>
                </div>
            </div>
            <span
                className={`flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded-full border flex-shrink-0 ${outcomeMeta.cls}`}
            >
                <OutcomeIcon size={10} />
                {outcomeMeta.label}
            </span>
        </button>
    );
}
