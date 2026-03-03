/**
 * AgentPermissionsModal — Per-agent tool authorization management.
 *
 * Displays a modal overlay with toggleable permission switches for each
 * tool registered by a connected agent. Part of the RFC 8693 delegated
 * authorization framework.
 *
 * When an agent declares required_credentials in its metadata, the modal
 * shows a credentials section. Tools are locked until all required
 * credentials are provided.
 */
import React, { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
    X,
    Shield,
    ShieldCheck,
    ShieldX,
    ShieldAlert,
    AlertTriangle,
    Eye,
    Pencil,
    Search,
    Cpu,
    BarChart3,
    Save,
    Loader2,
    KeyRound,
    Lock,
    Check,
    Trash2,
    ExternalLink,
    RefreshCw,
    Linkedin,
} from "lucide-react";
import { API_URL } from "../config";
import type { RequiredCredential } from "../hooks/useWebSocket";

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

interface SecurityFlagInfo {
    category: string;
    reason: string;
    blocked: boolean;
}

/** Human-readable descriptions for security threat categories */
const SECURITY_CATEGORY_LABELS: Record<string, string> = {
    DATA_EGRESS: "Data Export Risk",
    CODE_EXECUTION: "Code Execution Risk",
    CREDENTIAL_ACCESS: "Credential Access Risk",
    DESTRUCTIVE: "Destructive Operation",
    PRIVILEGE_ESCALATION: "Privilege Escalation Risk",
    NETWORK_MANIPULATION: "Network Access Risk",
};

interface AgentPermissionsModalProps {
    isOpen: boolean;
    onClose: () => void;
    agentId: string;
    agentName: string;
    agentDescription?: string;
    permissions: Record<string, boolean>;
    toolDescriptions: Record<string, string>;
    securityFlags?: Record<string, SecurityFlagInfo>;
    onSave: (agentId: string, permissions: Record<string, boolean>) => void;
    // Credential management
    requiredCredentials?: RequiredCredential[];
    storedCredentialKeys?: string[];
    onSaveCredentials?: (agentId: string, credentials: Record<string, string>) => Promise<boolean>;
    onDeleteCredential?: (agentId: string, key: string) => Promise<boolean>;
    onStartOAuth?: (agentId: string) => Promise<boolean>;
}

export default function AgentPermissionsModal({
    isOpen,
    onClose,
    agentId,
    agentName,
    agentDescription,
    permissions: initialPermissions,
    toolDescriptions,
    securityFlags,
    onSave,
    requiredCredentials,
    storedCredentialKeys = [],
    onSaveCredentials,
    onDeleteCredential,
    onStartOAuth,
}: AgentPermissionsModalProps) {
    const [localPermissions, setLocalPermissions] = useState<Record<string, boolean>>({});
    const [saving, setSaving] = useState(false);
    const [hasChanges, setHasChanges] = useState(false);

    // Credential state
    const [credentialValues, setCredentialValues] = useState<Record<string, string>>({});
    const [showCredentialForm, setShowCredentialForm] = useState(false);
    const [savingCredentials, setSavingCredentials] = useState(false);
    const [deletingKey, setDeletingKey] = useState<string | null>(null);
    const [authorizing, setAuthorizing] = useState(false);

    const hasRequiredCredentials = requiredCredentials && requiredCredentials.length > 0;
    const missingCredentials = hasRequiredCredentials
        ? requiredCredentials.filter(c => c.required && !storedCredentialKeys.includes(c.key))
        : [];
    const credentialsComplete = missingCredentials.length === 0;
    const needsCredentials = hasRequiredCredentials && !credentialsComplete;

    // Check if this agent needs OAuth (has client_id/secret type credentials)
    const hasClientIdStored = storedCredentialKeys.includes("LINKEDIN_CLIENT_ID");
    const hasClientSecretStored = storedCredentialKeys.includes("LINKEDIN_CLIENT_SECRET");
    const hasAccessToken = storedCredentialKeys.includes("LINKEDIN_ACCESS_TOKEN");
    const canAuthorize = hasClientIdStored && hasClientSecretStored && onStartOAuth;

    // OAuth connection status
    const [oauthStatus, setOauthStatus] = useState<{
        connected: boolean;
        expired?: boolean;
        profile_name?: string;
        profile_email?: string;
    } | null>(null);
    const [loadingOAuthStatus, setLoadingOAuthStatus] = useState(false);

    const fetchOAuthStatus = useCallback(async () => {
        if (!hasAccessToken) {
            setOauthStatus(null);
            return;
        }
        setLoadingOAuthStatus(true);
        try {
            const resp = await fetch(`${API_URL}/api/agents/${agentId}/oauth/status`, {
                headers: { "Authorization": "Bearer mock" },
            });
            if (resp.ok) {
                setOauthStatus(await resp.json());
            }
        } catch {
            // ignore
        } finally {
            setLoadingOAuthStatus(false);
        }
    }, [agentId, hasAccessToken]);

    // Sync local state when modal opens or permissions change
    useEffect(() => {
        if (isOpen) {
            setLocalPermissions({ ...initialPermissions });
            setHasChanges(false);
            setSaving(false);
            setCredentialValues({});
            setSavingCredentials(false);
            setDeletingKey(null);
            setOauthStatus(null);
            // Auto-show credential form if credentials are missing
            setShowCredentialForm(!credentialsComplete && !!hasRequiredCredentials);
            // Fetch OAuth status if token exists
            fetchOAuthStatus();
        }
    }, [isOpen, initialPermissions, credentialsComplete, hasRequiredCredentials, fetchOAuthStatus]);

    // Close on Escape key
    useEffect(() => {
        if (!isOpen) return;
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => document.removeEventListener("keydown", handleKeyDown);
    }, [isOpen, onClose]);

    const toggleTool = (toolName: string) => {
        if (needsCredentials) return; // Can't toggle when credentials missing
        setLocalPermissions((prev) => {
            const updated = { ...prev, [toolName]: !prev[toolName] };
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
        setTimeout(() => {
            setSaving(false);
            onClose();
        }, 300);
    };

    const handleSaveCredentials = async () => {
        if (!onSaveCredentials) return;
        // Filter out empty values
        const toSave: Record<string, string> = {};
        for (const [k, v] of Object.entries(credentialValues)) {
            if (v.trim()) toSave[k] = v.trim();
        }
        if (Object.keys(toSave).length === 0) return;

        setSavingCredentials(true);
        const ok = await onSaveCredentials(agentId, toSave);
        setSavingCredentials(false);
        if (ok) {
            setCredentialValues({});
            setShowCredentialForm(false);
        }
    };

    const handleDeleteCredential = async (key: string) => {
        if (!onDeleteCredential) return;
        setDeletingKey(key);
        await onDeleteCredential(agentId, key);
        setDeletingKey(null);
    };

    const handleStartOAuth = async () => {
        if (!onStartOAuth) return;
        setAuthorizing(true);
        await onStartOAuth(agentId);
        setAuthorizing(false);
        // Refresh OAuth status after authorization attempt
        setTimeout(() => fetchOAuthStatus(), 500);
    };

    const systemBlockedCount = Object.keys(securityFlags || {}).filter(
        t => securityFlags?.[t]?.blocked
    ).length;
    const enabledCount = Object.entries(localPermissions).filter(
        ([name, v]) => v && !(securityFlags?.[name]?.blocked)
    ).length;
    const totalCount = Object.keys(localPermissions).length;

    // Group tools by category
    const grouped: Record<string, string[]> = {};
    for (const tool of Object.keys(localPermissions)) {
        const { category } = getToolMeta(tool);
        if (!grouped[category]) grouped[category] = [];
        grouped[category].push(tool);
    }

    const categoryOrder = ["Data", "System", "Search", "Other"];
    const sortedCategories = Object.keys(grouped).sort(
        (a, b) => (categoryOrder.indexOf(a) === -1 ? 99 : categoryOrder.indexOf(a))
            - (categoryOrder.indexOf(b) === -1 ? 99 : categoryOrder.indexOf(b))
    );

    const hasCredentialInputValues = Object.values(credentialValues).some(v => v.trim().length > 0);

    return (
        <AnimatePresence>
            {isOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95, y: 10 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95, y: 10 }}
                        transition={{ duration: 0.2 }}
                        className="bg-astral-surface border border-white/10 rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden"
                        role="dialog"
                        aria-modal="true"
                        aria-label={`${agentName} permissions`}
                        onClick={(e) => e.stopPropagation()}
                    >
                        {/* Header */}
                        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg bg-astral-primary/20 flex items-center justify-center">
                                    <Shield size={16} className="text-astral-primary" />
                                </div>
                                <div>
                                    <h2 className="text-sm font-semibold text-white">
                                        {agentName}
                                    </h2>
                                    <p className="text-[11px] text-astral-muted">
                                        {enabledCount}/{totalCount - systemBlockedCount} tools enabled
                                        {systemBlockedCount > 0 && (
                                            <span className="text-red-400"> &middot; {systemBlockedCount} blocked</span>
                                        )}
                                        {needsCredentials && (
                                            <span className="text-amber-400"> &middot; credentials required</span>
                                        )}
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

                        {/* Agent Description */}
                        {agentDescription && (
                            <div className="px-6 pt-4 pb-0">
                                <p className="text-xs text-astral-muted/80 leading-relaxed">
                                    {agentDescription}
                                </p>
                            </div>
                        )}

                        {/* Scrollable Content */}
                        <div className="px-6 py-4 max-h-[60vh] overflow-y-auto space-y-5">

                            {/* ── Credentials Section ────────────────────────── */}
                            {hasRequiredCredentials && (
                                <div>
                                    <div className="flex items-center justify-between mb-2">
                                        <p className="text-[10px] font-semibold uppercase tracking-widest text-astral-muted flex items-center gap-1.5">
                                            <KeyRound size={10} />
                                            API Credentials
                                        </p>
                                        {credentialsComplete && !showCredentialForm && (
                                            <button
                                                onClick={() => setShowCredentialForm(true)}
                                                className="text-[10px] text-astral-primary hover:text-astral-primary/80 transition-colors"
                                            >
                                                Update
                                            </button>
                                        )}
                                    </div>

                                    {/* Credential status rows */}
                                    <div className="space-y-1">
                                        {requiredCredentials!.map((cred) => {
                                            const isStored = storedCredentialKeys.includes(cred.key);
                                            const isDeleting = deletingKey === cred.key;

                                            return (
                                                <div key={cred.key}>
                                                    <div
                                                        className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors
                                                            ${isStored
                                                                ? "bg-green-500/[0.06] border border-green-500/10"
                                                                : "bg-amber-500/[0.06] border border-amber-500/15"}`}
                                                    >
                                                        <div className={`w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0
                                                            ${isStored ? "bg-green-500/15 text-green-400" : "bg-amber-500/15 text-amber-400"}`}>
                                                            {isStored ? <Check size={14} /> : <Lock size={14} />}
                                                        </div>
                                                        <div className="flex-1 min-w-0">
                                                            <div className="flex items-center gap-2">
                                                                <p className="text-xs font-medium text-white truncate">
                                                                    {cred.label}
                                                                </p>
                                                                <span className={`text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded-full
                                                                    ${isStored ? "bg-green-500/15 text-green-400" : "bg-amber-500/15 text-amber-400"}`}>
                                                                    {isStored ? "Stored" : "Required"}
                                                                </span>
                                                            </div>
                                                            <p className="text-[10px] text-astral-muted truncate mt-0.5">
                                                                {cred.key}
                                                            </p>
                                                        </div>
                                                        {isStored && onDeleteCredential && (
                                                            <button
                                                                onClick={() => handleDeleteCredential(cred.key)}
                                                                disabled={isDeleting}
                                                                className="p-1 text-astral-muted/40 hover:text-red-400 transition-colors"
                                                                title="Remove credential"
                                                            >
                                                                {isDeleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                                                            </button>
                                                        )}
                                                    </div>

                                                    {/* Inline input when form is shown */}
                                                    {showCredentialForm && (
                                                        <div className="mt-1 ml-10 mr-1">
                                                            <input
                                                                type="password"
                                                                placeholder={isStored ? "Enter new value to update..." : `Enter ${cred.label}...`}
                                                                value={credentialValues[cred.key] || ""}
                                                                onChange={(e) => setCredentialValues(prev => ({ ...prev, [cred.key]: e.target.value }))}
                                                                className="w-full px-3 py-1.5 text-xs bg-white/5 border border-white/10 rounded-md
                                                                    text-white placeholder:text-astral-muted/40 focus:outline-none focus:border-astral-primary/40
                                                                    transition-colors"
                                                            />
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })}
                                    </div>

                                    {/* Save credentials button */}
                                    {showCredentialForm && (
                                        <div className="flex items-center gap-2 mt-3">
                                            <button
                                                onClick={handleSaveCredentials}
                                                disabled={!hasCredentialInputValues || savingCredentials}
                                                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-all
                                                    ${hasCredentialInputValues && !savingCredentials
                                                        ? "bg-green-500/20 text-green-400 hover:bg-green-500/30 border border-green-500/20"
                                                        : "bg-white/5 text-astral-muted cursor-not-allowed border border-white/5"}`}
                                            >
                                                {savingCredentials ? (
                                                    <Loader2 size={12} className="animate-spin" />
                                                ) : (
                                                    <KeyRound size={12} />
                                                )}
                                                <span>Save Credentials</span>
                                            </button>
                                            {credentialsComplete && (
                                                <button
                                                    onClick={() => { setShowCredentialForm(false); setCredentialValues({}); }}
                                                    className="px-3 py-1.5 text-xs text-astral-muted hover:text-white transition-colors"
                                                >
                                                    Cancel
                                                </button>
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* ── LinkedIn Connection Status ────────────────── */}
                            {canAuthorize && (
                                <div>
                                    <p className="text-[10px] font-semibold uppercase tracking-widest text-astral-muted flex items-center gap-1.5 mb-2">
                                        <Linkedin size={10} />
                                        LinkedIn Connection
                                    </p>

                                    {/* Connected state */}
                                    {oauthStatus?.connected && !oauthStatus?.expired ? (
                                        <div className="space-y-2">
                                            <div className="flex items-center gap-3 px-3 py-3 rounded-lg bg-[#0077B5]/[0.08] border border-[#0077B5]/15">
                                                <div className="w-8 h-8 rounded-full bg-[#0077B5]/20 flex items-center justify-center flex-shrink-0">
                                                    <Linkedin size={16} className="text-[#0077B5]" />
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <p className="text-xs font-medium text-white truncate">
                                                            {oauthStatus.profile_name || "LinkedIn Account"}
                                                        </p>
                                                        <span className="text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded-full bg-green-500/15 text-green-400">
                                                            Connected
                                                        </span>
                                                    </div>
                                                    {oauthStatus.profile_email && (
                                                        <p className="text-[10px] text-astral-muted truncate mt-0.5">
                                                            {oauthStatus.profile_email}
                                                        </p>
                                                    )}
                                                </div>
                                                <button
                                                    onClick={handleStartOAuth}
                                                    disabled={authorizing}
                                                    className="p-1.5 text-astral-muted/60 hover:text-[#0077B5] transition-colors"
                                                    title="Re-authorize with LinkedIn"
                                                >
                                                    {authorizing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                                                </button>
                                            </div>
                                        </div>
                                    ) : oauthStatus?.connected && oauthStatus?.expired ? (
                                        /* Expired token state */
                                        <div className="space-y-2">
                                            <div className="flex items-center gap-3 px-3 py-3 rounded-lg bg-amber-500/[0.06] border border-amber-500/15">
                                                <div className="w-8 h-8 rounded-full bg-amber-500/15 flex items-center justify-center flex-shrink-0">
                                                    <Linkedin size={16} className="text-amber-400" />
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <p className="text-xs font-medium text-white truncate">
                                                            {oauthStatus.profile_name || "LinkedIn Account"}
                                                        </p>
                                                        <span className="text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-400">
                                                            Expired
                                                        </span>
                                                    </div>
                                                    <p className="text-[10px] text-amber-400/80 mt-0.5">
                                                        Token expired — re-authorize to reconnect
                                                    </p>
                                                </div>
                                            </div>
                                            <button
                                                onClick={handleStartOAuth}
                                                disabled={authorizing}
                                                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-medium rounded-lg
                                                    bg-[#0077B5]/20 text-[#0077B5] hover:bg-[#0077B5]/30 border border-[#0077B5]/25
                                                    transition-all"
                                            >
                                                {authorizing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                                                <span>{authorizing ? "Waiting for authorization..." : "Re-authorize with LinkedIn"}</span>
                                            </button>
                                        </div>
                                    ) : (
                                        /* Not connected state */
                                        <div>
                                            <button
                                                onClick={handleStartOAuth}
                                                disabled={authorizing}
                                                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-medium rounded-lg
                                                    bg-[#0077B5]/20 text-[#0077B5] hover:bg-[#0077B5]/30 border border-[#0077B5]/25
                                                    transition-all"
                                            >
                                                {authorizing ? (
                                                    <Loader2 size={14} className="animate-spin" />
                                                ) : (
                                                    <ExternalLink size={14} />
                                                )}
                                                <span>{authorizing ? "Waiting for authorization..." : "Authorize with LinkedIn"}</span>
                                            </button>
                                            <p className="text-[10px] text-astral-muted/60 text-center mt-1.5">
                                                Opens LinkedIn in a new window to grant access
                                            </p>
                                        </div>
                                    )}

                                    {loadingOAuthStatus && (
                                        <div className="flex items-center justify-center gap-2 py-2">
                                            <Loader2 size={12} className="animate-spin text-astral-muted" />
                                            <span className="text-[10px] text-astral-muted">Checking connection...</span>
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* ── Credential Lock Banner ─────────────────────── */}
                            {needsCredentials && (
                                <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-amber-500/[0.08] border border-amber-500/15">
                                    <Lock size={14} className="text-amber-400 flex-shrink-0" />
                                    <p className="text-[11px] text-amber-300/90">
                                        {canAuthorize
                                            ? "Save your Client ID and Secret above, then click 'Authorize with LinkedIn' to connect."
                                            : "Enter the required credentials above to unlock tools."}
                                    </p>
                                </div>
                            )}

                            {/* ── Tool List ──────────────────────────────────── */}
                            <div className={needsCredentials ? "opacity-40 pointer-events-none select-none" : ""}>
                                {sortedCategories.map((category) => (
                                    <div key={category} className="mb-4 last:mb-0">
                                        <p className="text-[10px] font-semibold uppercase tracking-widest text-astral-muted mb-2">
                                            {category}
                                        </p>
                                        <div className="space-y-1">
                                            {grouped[category].map((tool) => {
                                                const meta = getToolMeta(tool);
                                                const enabled = localPermissions[tool];
                                                const flag = securityFlags?.[tool];
                                                const isSystemBlocked = flag?.blocked === true;
                                                return (
                                                    <div
                                                        key={tool}
                                                        className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors group
                                                            ${isSystemBlocked
                                                                ? "bg-red-500/[0.08] border border-red-500/20 cursor-not-allowed opacity-80"
                                                                : enabled
                                                                    ? "bg-white/[0.03] hover:bg-white/[0.06] cursor-pointer"
                                                                    : "bg-white/[0.01] hover:bg-white/[0.03] opacity-60 cursor-pointer"}`}
                                                        onClick={() => !isSystemBlocked && toggleTool(tool)}
                                                    >
                                                        {/* Icon */}
                                                        <div className={`w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0
                                                            ${isSystemBlocked
                                                                ? "bg-red-500/20 text-red-400"
                                                                : enabled
                                                                    ? "bg-astral-primary/15 text-astral-primary"
                                                                    : "bg-white/5 text-astral-muted"}`}>
                                                            {isSystemBlocked ? <ShieldAlert size={14} /> : meta.icon}
                                                        </div>

                                                        {/* Info */}
                                                        <div className="flex-1 min-w-0">
                                                            <div className="flex items-center gap-2">
                                                                <p className={`text-xs font-medium truncate ${isSystemBlocked ? "text-red-300" : "text-white"}`}>
                                                                    {formatToolName(tool)}
                                                                </p>
                                                                {isSystemBlocked ? (
                                                                    <span className="text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded-full bg-red-500/20 text-red-400">
                                                                        Blocked
                                                                    </span>
                                                                ) : (
                                                                    <span className={`text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded-full
                                                                        ${meta.risk === "write"
                                                                            ? "bg-amber-500/15 text-amber-400"
                                                                            : "bg-green-500/15 text-green-400"}`}>
                                                                        {meta.risk === "write" ? "Write" : "Read"}
                                                                    </span>
                                                                )}
                                                            </div>
                                                            <p className="text-[10px] text-astral-muted truncate mt-0.5">
                                                                {toolDescriptions[tool] || "No description available"}
                                                            </p>
                                                            {isSystemBlocked && flag && (
                                                                <div className="flex items-center gap-1 mt-1">
                                                                    <AlertTriangle size={10} className="text-red-400 flex-shrink-0" />
                                                                    <p className="text-[9px] text-red-400/80">
                                                                        <span className="font-medium">{SECURITY_CATEGORY_LABELS[flag.category] || flag.category}</span>
                                                                        {" — "}{flag.reason}
                                                                    </p>
                                                                </div>
                                                            )}
                                                        </div>

                                                        {/* Toggle Switch */}
                                                        <div
                                                            className={`relative w-9 h-5 rounded-full flex-shrink-0 transition-colors duration-200
                                                                ${isSystemBlocked
                                                                    ? "bg-red-500/20"
                                                                    : enabled
                                                                        ? "bg-astral-primary"
                                                                        : "bg-white/10"}`}
                                                        >
                                                            <motion.div
                                                                className={`absolute top-0.5 w-4 h-4 rounded-full shadow-sm ${isSystemBlocked ? "bg-red-400/50" : "bg-white"}`}
                                                                animate={{ left: (enabled && !isSystemBlocked) ? "18px" : "2px" }}
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
                        </div>

                        {/* Footer */}
                        <div className="flex items-center justify-between px-6 py-4 border-t border-white/5 bg-white/[0.02]">
                            <div className="flex items-center gap-2 text-[11px] text-astral-muted">
                                {needsCredentials ? (
                                    <>
                                        <Lock size={14} className="text-amber-400" />
                                        <span className="text-amber-400">{missingCredentials.length} credential{missingCredentials.length > 1 ? "s" : ""} needed</span>
                                    </>
                                ) : systemBlockedCount > 0 ? (
                                    <>
                                        <ShieldAlert size={14} className="text-red-400" />
                                        <span>{systemBlockedCount} tool{systemBlockedCount > 1 ? "s" : ""} system-blocked</span>
                                        {enabledCount > 0 && (
                                            <span className="text-astral-muted/50">&middot; {enabledCount} enabled</span>
                                        )}
                                    </>
                                ) : enabledCount === totalCount ? (
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
                                    disabled={!hasChanges || saving || needsCredentials}
                                    className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg transition-all
                                        ${hasChanges && !saving && !needsCredentials
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
