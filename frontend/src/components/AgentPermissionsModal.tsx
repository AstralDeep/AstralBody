/**
 * AgentPermissionsModal — Per-agent tool authorization management.
 *
 * Displays a modal overlay with toggleable permission switches for each
 * tool registered by a connected agent. Part of the RFC 8693 delegated
 * authorization framework.
 */
import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
    X,
    Shield,
    ShieldCheck,
    ShieldX,
    Eye,
    Pencil,
    Search,
    Cpu,
    BarChart3,
    Save,
    Loader2,
} from "lucide-react";

/**
 * Tool metadata for display — categories and risk levels.
 */
const TOOL_META: Record<string, { category: string; risk: "read" | "write"; icon: React.ReactNode }> = {
    generate_dynamic_chart: { category: "Data", risk: "read", icon: <BarChart3 size={14} /> },
    modify_data: { category: "Data", risk: "write", icon: <Pencil size={14} /> },
    get_system_status: { category: "System", risk: "read", icon: <Cpu size={14} /> },
    get_cpu_info: { category: "System", risk: "read", icon: <Cpu size={14} /> },
    get_memory_info: { category: "System", risk: "read", icon: <Cpu size={14} /> },
    get_disk_info: { category: "System", risk: "read", icon: <Cpu size={14} /> },
    search_wikipedia: { category: "Search", risk: "read", icon: <Search size={14} /> },
    search_arxiv: { category: "Search", risk: "read", icon: <Search size={14} /> },
};

function getToolMeta(toolName: string) {
    return TOOL_META[toolName] || { category: "Other", risk: "read" as const, icon: <Eye size={14} /> };
}

function formatToolName(name: string): string {
    return name
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());
}

interface AgentPermissionsModalProps {
    isOpen: boolean;
    onClose: () => void;
    agentId: string;
    agentName: string;
    permissions: Record<string, boolean>;
    toolDescriptions: Record<string, string>;
    onSave: (agentId: string, permissions: Record<string, boolean>) => void;
}

export default function AgentPermissionsModal({
    isOpen,
    onClose,
    agentId,
    agentName,
    permissions: initialPermissions,
    toolDescriptions,
    onSave,
}: AgentPermissionsModalProps) {
    const [localPermissions, setLocalPermissions] = useState<Record<string, boolean>>({});
    const [saving, setSaving] = useState(false);
    const [hasChanges, setHasChanges] = useState(false);

    // Sync local state when modal opens or permissions change
    useEffect(() => {
        if (isOpen) {
            setLocalPermissions({ ...initialPermissions });
            setHasChanges(false);
            setSaving(false);
        }
    }, [isOpen, initialPermissions]);

    const toggleTool = (toolName: string) => {
        setLocalPermissions((prev) => {
            const updated = { ...prev, [toolName]: !prev[toolName] };
            // Check if anything differs from initial
            const changed = Object.keys(updated).some(
                (k) => updated[k] !== initialPermissions[k]
            );
            setHasChanges(changed);
            return updated;
        });
    };

    const handleSave = () => {
        setSaving(true);
        onSave(agentId, localPermissions);
        // Modal will close or update when parent receives the response
        setTimeout(() => {
            setSaving(false);
            onClose();
        }, 300);
    };

    const enabledCount = Object.values(localPermissions).filter(Boolean).length;
    const totalCount = Object.keys(localPermissions).length;

    // Group tools by category
    const grouped: Record<string, string[]> = {};
    for (const tool of Object.keys(localPermissions)) {
        const { category } = getToolMeta(tool);
        if (!grouped[category]) grouped[category] = [];
        grouped[category].push(tool);
    }

    // Sort categories: Data, System, Search, Other
    const categoryOrder = ["Data", "System", "Search", "Other"];
    const sortedCategories = Object.keys(grouped).sort(
        (a, b) => (categoryOrder.indexOf(a) === -1 ? 99 : categoryOrder.indexOf(a))
            - (categoryOrder.indexOf(b) === -1 ? 99 : categoryOrder.indexOf(b))
    );

    return (
        <AnimatePresence>
            {isOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95, y: 10 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95, y: 10 }}
                        transition={{ duration: 0.2 }}
                        className="bg-astral-surface border border-white/10 rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden"
                    >
                        {/* Header */}
                        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg bg-astral-primary/20 flex items-center justify-center">
                                    <Shield size={16} className="text-astral-primary" />
                                </div>
                                <div>
                                    <h2 className="text-sm font-semibold text-white">
                                        Agent Permissions
                                    </h2>
                                    <p className="text-[11px] text-astral-muted">
                                        {agentName} &middot; {enabledCount}/{totalCount} tools enabled
                                    </p>
                                </div>
                            </div>
                            <button
                                onClick={onClose}
                                className="p-1.5 text-astral-muted hover:text-white hover:bg-white/5 rounded-lg transition-colors"
                            >
                                <X size={16} />
                            </button>
                        </div>

                        {/* Tool List */}
                        <div className="px-6 py-4 max-h-[60vh] overflow-y-auto space-y-5">
                            {sortedCategories.map((category) => (
                                <div key={category}>
                                    <p className="text-[10px] font-semibold uppercase tracking-widest text-astral-muted mb-2">
                                        {category}
                                    </p>
                                    <div className="space-y-1">
                                        {grouped[category].map((tool) => {
                                            const meta = getToolMeta(tool);
                                            const enabled = localPermissions[tool];
                                            return (
                                                <div
                                                    key={tool}
                                                    className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors cursor-pointer group
                                                        ${enabled ? "bg-white/[0.03] hover:bg-white/[0.06]" : "bg-white/[0.01] hover:bg-white/[0.03] opacity-60"}`}
                                                    onClick={() => toggleTool(tool)}
                                                >
                                                    {/* Icon */}
                                                    <div className={`w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0
                                                        ${enabled ? "bg-astral-primary/15 text-astral-primary" : "bg-white/5 text-astral-muted"}`}>
                                                        {meta.icon}
                                                    </div>

                                                    {/* Info */}
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-2">
                                                            <p className="text-xs font-medium text-white truncate">
                                                                {formatToolName(tool)}
                                                            </p>
                                                            {/* Risk Badge */}
                                                            <span className={`text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded-full
                                                                ${meta.risk === "write"
                                                                    ? "bg-amber-500/15 text-amber-400"
                                                                    : "bg-green-500/15 text-green-400"}`}>
                                                                {meta.risk === "write" ? "Write" : "Read"}
                                                            </span>
                                                        </div>
                                                        <p className="text-[10px] text-astral-muted truncate mt-0.5">
                                                            {toolDescriptions[tool] || "No description available"}
                                                        </p>
                                                    </div>

                                                    {/* Toggle Switch */}
                                                    <div
                                                        className={`relative w-9 h-5 rounded-full flex-shrink-0 transition-colors duration-200
                                                            ${enabled ? "bg-astral-primary" : "bg-white/10"}`}
                                                    >
                                                        <motion.div
                                                            className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-sm"
                                                            animate={{ left: enabled ? "18px" : "2px" }}
                                                            transition={{ type: "spring", stiffness: 500, damping: 30 }}
                                                        />
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            ))}

                            {totalCount === 0 && (
                                <div className="text-center py-8">
                                    <ShieldX size={24} className="text-astral-muted mx-auto mb-2" />
                                    <p className="text-xs text-astral-muted">No tools registered for this agent</p>
                                </div>
                            )}
                        </div>

                        {/* Footer */}
                        <div className="flex items-center justify-between px-6 py-4 border-t border-white/5 bg-white/[0.02]">
                            <div className="flex items-center gap-2 text-[11px] text-astral-muted">
                                {enabledCount === totalCount ? (
                                    <>
                                        <ShieldCheck size={14} className="text-green-400" />
                                        <span>All tools enabled</span>
                                    </>
                                ) : enabledCount === 0 ? (
                                    <>
                                        <ShieldX size={14} className="text-red-400" />
                                        <span>All tools disabled</span>
                                    </>
                                ) : (
                                    <>
                                        <Shield size={14} className="text-amber-400" />
                                        <span>{totalCount - enabledCount} tool{totalCount - enabledCount > 1 ? "s" : ""} restricted</span>
                                    </>
                                )}
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={onClose}
                                    className="px-4 py-2 text-xs font-medium text-astral-muted hover:text-white hover:bg-white/5 rounded-lg transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleSave}
                                    disabled={!hasChanges || saving}
                                    className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg transition-all
                                        ${hasChanges && !saving
                                            ? "bg-astral-primary text-white hover:bg-astral-primary/90 shadow-lg shadow-astral-primary/20"
                                            : "bg-white/5 text-astral-muted cursor-not-allowed"}`}
                                >
                                    {saving ? (
                                        <Loader2 size={12} className="animate-spin" />
                                    ) : (
                                        <Save size={12} />
                                    )}
                                    <span>Save</span>
                                </button>
                            </div>
                        </div>
                    </motion.div>
                </div>
            )}
        </AnimatePresence>
    );
}
