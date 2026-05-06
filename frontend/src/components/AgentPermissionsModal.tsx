/**
 * AgentPermissionsModal -- Scope-based agent authorization management.
 *
 * Displays a modal overlay with scope toggle cards (read, write, search,
 * system) instead of individual per-tool switches.  Each scope card is
 * expandable to show which tools fall under it, and toggling a scope ON
 * triggers a confirmation dialog explaining what the scope grants.
 *
 * Part of the RFC 8693 delegated authorization framework.
 *
 * When an agent declares required_credentials in its metadata, the modal
 * shows a credentials section.  Tools are locked until all required
 * credentials are provided.
 */
import React, { useState, useEffect, useCallback, useMemo } from "react";
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
    Save,
    Loader2,
    KeyRound,
    Lock,
    Check,
    Trash2,
    ExternalLink,
    RefreshCw,
    Linkedin,
    Globe,
    ArrowLeft,
    Info,
} from "lucide-react";
import { API_URL } from "../config";
import type { RequiredCredential } from "../hooks/useWebSocket";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/*  Scope metadata                                                     */
/* ------------------------------------------------------------------ */

interface ScopeMeta {
    key: string;
    label: string;
    description: string;
    icon: React.ReactNode;
    warning: string;
    color: string;          // tailwind color stem, e.g. "green"
    colorClass: string;     // text color class
    bgClass: string;        // bg tint class
}

const SCOPE_DEFINITIONS: ScopeMeta[] = [
    {
        key: "tools:read",
        label: "Read",
        description: "View data, files, profiles, and analytics",
        icon: <Eye size={16} />,
        warning:
            "This agent will be able to read your data, including files, profiles, and analytics. It can view but not modify your information.",
        color: "green",
        colorClass: "text-green-400",
        bgClass: "bg-green-500",
    },
    {
        key: "tools:write",
        label: "Write",
        description: "Create, modify, and delete data on your behalf",
        icon: <Pencil size={16} />,
        warning:
            "This agent will be able to create, modify, and delete data on your behalf. This includes writing files, posting to external services (e.g., LinkedIn), and updating settings.",
        color: "amber",
        colorClass: "text-amber-400",
        bgClass: "bg-amber-500",
    },
    {
        key: "tools:search",
        label: "Search",
        description: "Query external APIs, databases, and web search",
        icon: <Search size={16} />,
        warning:
            "This agent will be able to query external APIs and databases, including academic databases, grant repositories, and web search engines. Search queries may be sent to third-party services.",
        color: "blue",
        colorClass: "text-blue-400",
        bgClass: "bg-blue-500",
    },
    {
        key: "tools:system",
        label: "System",
        description: "Access CPU, memory, disk, and server environment info",
        icon: <Cpu size={16} />,
        warning:
            "This agent will be able to access system resources including CPU usage, memory information, and disk status. This reveals details about the server environment.",
        color: "purple",
        colorClass: "text-purple-400",
        bgClass: "bg-purple-500",
    },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function formatToolName(name: string): string {
    return name
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface AgentPermissionsModalProps {
    isOpen: boolean;
    onClose: () => void;
    agentId: string;
    agentName: string;
    agentDescription?: string;
    // Scope-based permissions
    scopes?: Record<string, boolean>;
    toolScopeMap?: Record<string, string>;
    permissions: Record<string, boolean>;
    toolOverrides?: Record<string, boolean>;
    toolDescriptions: Record<string, string>;
    securityFlags?: Record<string, SecurityFlagInfo>;
    onSave: (agentId: string, scopes: Record<string, boolean>, toolOverrides?: Record<string, boolean>) => void;
    // Credential management
    requiredCredentials?: RequiredCredential[];
    storedCredentialKeys?: string[];
    onSaveCredentials?: (agentId: string, credentials: Record<string, string>) => Promise<boolean>;
    onDeleteCredential?: (agentId: string, key: string) => Promise<boolean>;
    onStartOAuth?: (agentId: string) => Promise<boolean>;
    // Ownership / visibility
    isOwner?: boolean;
    isPublic?: boolean;
    onSetVisibility?: (agentId: string, isPublic: boolean) => Promise<boolean>;
    // Navigation
    onBack?: () => void;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function AgentPermissionsModal({
    isOpen,
    onClose,
    agentId,
    agentName,
    agentDescription,
    scopes: initialScopes,
    toolScopeMap = {},
    permissions,
    toolOverrides: initialToolOverrides,
    toolDescriptions,
    securityFlags,
    onSave,
    requiredCredentials,
    storedCredentialKeys = [],
    onSaveCredentials,
    onDeleteCredential,
    onStartOAuth,
    isOwner = false,
    isPublic: initialIsPublic = false,
    onSetVisibility,
    onBack,
}: AgentPermissionsModalProps) {

    /* ---------- Derive initial scopes from props ---------- */

    const deriveScopes = useCallback((): Record<string, boolean> => {
        if (initialScopes) return { ...initialScopes };
        // Fallback: infer scopes from per-tool permissions + toolScopeMap
        const inferred: Record<string, boolean> = {};
        for (const def of SCOPE_DEFINITIONS) {
            inferred[def.key] = false;
        }
        for (const [tool, enabled] of Object.entries(permissions)) {
            const scope = toolScopeMap[tool];
            if (scope && enabled) {
                inferred[scope] = true;
            }
        }
        return inferred;
    }, [initialScopes, permissions, toolScopeMap]);

    /* ---------- State ---------- */

    const [localScopes, setLocalScopes] = useState<Record<string, boolean>>({});
    const [localToolOverrides, setLocalToolOverrides] = useState<Record<string, boolean>>({});
    const [saving, setSaving] = useState(false);
    const [hasChanges, setHasChanges] = useState(false);

    // Scope warning confirmation dialog. Triggered by per-tool toggles
    // when the underlying scope is OFF — the user must consent to the
    // permission kind before any tool of that kind goes live.
    const [pendingScopeToggle, setPendingScopeToggle] = useState<(ScopeMeta & { triggeringTool?: string }) | null>(null);

    // Credential state
    const [credentialValues, setCredentialValues] = useState<Record<string, string>>({});
    const [showCredentialForm, setShowCredentialForm] = useState(false);
    const [savingCredentials, setSavingCredentials] = useState(false);
    const [deletingKey, setDeletingKey] = useState<string | null>(null);
    const [authorizing, setAuthorizing] = useState(false);

    // Visibility state
    const [localIsPublic, setLocalIsPublic] = useState(initialIsPublic);
    const [showPublicWarning, setShowPublicWarning] = useState(false);
    const [togglingVisibility, setTogglingVisibility] = useState(false);

    const hasRequiredCredentials = requiredCredentials && requiredCredentials.length > 0;
    const missingCredentials = hasRequiredCredentials
        ? requiredCredentials.filter(c => c.required && !storedCredentialKeys.includes(c.key))
        : [];
    const credentialsComplete = missingCredentials.length === 0;
    const needsCredentials = hasRequiredCredentials && !credentialsComplete;

    // LinkedIn OAuth helpers
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

    /* ---------- Effects ---------- */

    // Sync local state when modal opens or props change
    useEffect(() => {
        if (isOpen) {
            setLocalScopes(deriveScopes());
            setLocalToolOverrides(initialToolOverrides ? { ...initialToolOverrides } : {});
            setHasChanges(false);
            setSaving(false);
            setPendingScopeToggle(null);
            setCredentialValues({});
            setSavingCredentials(false);
            setDeletingKey(null);
            setOauthStatus(null);
            setLocalIsPublic(initialIsPublic);
            setShowPublicWarning(false);
            setShowCredentialForm(!credentialsComplete && !!hasRequiredCredentials);
            fetchOAuthStatus();
        }
    }, [isOpen, deriveScopes, initialIsPublic, credentialsComplete, hasRequiredCredentials, fetchOAuthStatus]);

    // Close on Escape key
    useEffect(() => {
        if (!isOpen) return;
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => document.removeEventListener("keydown", handleKeyDown);
    }, [isOpen, onClose]);

    /* ---------- Scope helpers ---------- */

    const { enabledToolCount, totalToolCount } = useMemo(() => {
        let enabled = 0;
        let total = 0;
        for (const tool of Object.keys(permissions)) {
            const isBlocked = securityFlags?.[tool]?.blocked === true;
            if (isBlocked) continue;
            total += 1;
            const requiredScope = toolScopeMap[tool] || "tools:read";
            const scopeOn = !!localScopes[requiredScope];
            const overrideEnabled = localToolOverrides[tool] ?? true;
            if (scopeOn && overrideEnabled) enabled += 1;
        }
        return { enabledToolCount: enabled, totalToolCount: total };
    }, [permissions, securityFlags, toolScopeMap, localScopes, localToolOverrides]);

    const baselineOverrides = initialToolOverrides || {};

    const detectChanges = (scopes: Record<string, boolean>, overrides: Record<string, boolean>) => {
        const baseline = deriveScopes();
        const scopeChanged = Object.keys(scopes).some(k => scopes[k] !== baseline[k]);
        const overrideChanged =
            Object.keys(overrides).some(k => overrides[k] !== (baselineOverrides[k] ?? true)) ||
            Object.keys(baselineOverrides).some(k => (overrides[k] ?? true) !== (baselineOverrides[k] ?? true));
        setHasChanges(scopeChanged || overrideChanged);
    };

    const toggleToolOverride = (toolName: string) => {
        setLocalToolOverrides(prev => {
            const currentlyEnabled = prev[toolName] ?? true; // default = enabled (follows scope)
            const updated = { ...prev, [toolName]: !currentlyEnabled };
            detectChanges(localScopes, updated);
            return updated;
        });
    };

    const confirmScopeToggle = () => {
        if (!pendingScopeToggle) return;
        const { key: scopeKey, triggeringTool } = pendingScopeToggle;
        const updatedOverrides = { ...localToolOverrides };
        if (triggeringTool) {
            delete updatedOverrides[triggeringTool];
            for (const t of Object.keys(permissions)) {
                if (t === triggeringTool) continue;
                if ((toolScopeMap[t] || "tools:read") !== scopeKey) continue;
                if (updatedOverrides[t] === true) continue;
                updatedOverrides[t] = false;
            }
        }
        setLocalToolOverrides(updatedOverrides);
        setLocalScopes(prev => {
            const nextScopes = { ...prev, [scopeKey]: true };
            detectChanges(nextScopes, updatedOverrides);
            return nextScopes;
        });
        setPendingScopeToggle(null);
    };

    /* ---------- Save ---------- */

    const handleSave = () => {
        setSaving(true);
        // Build tool overrides to send: only include explicitly disabled tools
        const overridesToSend = Object.keys(localToolOverrides).length > 0 ? localToolOverrides : undefined;
        onSave(agentId, localScopes, overridesToSend);
        setTimeout(() => {
            setSaving(false);
            onClose();
        }, 300);
    };

    /* ---------- Credential handlers ---------- */

    const handleSaveCredentials = async () => {
        if (!onSaveCredentials) return;
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
        setTimeout(() => fetchOAuthStatus(), 500);
    };

    /* ---------- Visibility handlers ---------- */

    const handleVisibilityToggle = () => {
        if (localIsPublic) {
            confirmVisibilityChange(false);
        } else {
            setShowPublicWarning(true);
        }
    };

    const confirmVisibilityChange = async (makePublic: boolean) => {
        if (!onSetVisibility) return;
        setTogglingVisibility(true);
        const ok = await onSetVisibility(agentId, makePublic);
        setTogglingVisibility(false);
        setShowPublicWarning(false);
        if (ok) {
            setLocalIsPublic(makePublic);
        }
    };

    const hasCredentialInputValues = Object.values(credentialValues).some(v => v.trim().length > 0);

    /* ================================================================ */
    /*  Render                                                          */
    /* ================================================================ */

    return (
        <AnimatePresence>
            {isOpen && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95, y: 10 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95, y: 10 }}
                        transition={{ duration: 0.2 }}
                        className="bg-astral-surface border border-white/10 rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden relative flex flex-col max-h-[90vh]"
                        role="dialog"
                        aria-modal="true"
                        aria-label={`${agentName} permissions`}
                        onClick={(e) => e.stopPropagation()}
                    >
                        {/* ── Header ──────────────────────────────────── */}
                        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
                            <div className="flex items-center gap-3">
                                {onBack && (
                                    <button
                                        onClick={onBack}
                                        className="p-1.5 text-astral-muted hover:text-white hover:bg-white/5 rounded-lg transition-colors"
                                        title="Back to agents"
                                    >
                                        <ArrowLeft size={16} />
                                    </button>
                                )}
                                <div className="w-8 h-8 rounded-lg bg-astral-primary/20 flex items-center justify-center">
                                    <Shield size={16} className="text-astral-primary" />
                                </div>
                                <div>
                                    <h2 className="text-sm font-semibold text-white">
                                        {agentName}
                                    </h2>
                                    <p className="text-[11px] text-astral-muted">
                                        {enabledToolCount}/{totalToolCount} tools enabled
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

                        {/* ── Agent Description ───────────────────────── */}
                        {agentDescription && (
                            <div className="px-6 pt-4 pb-0">
                                <p className="text-xs text-astral-muted/80 leading-relaxed">
                                    {agentDescription}
                                </p>
                            </div>
                        )}

                        {/* ── Public Warning Confirmation Modal ────────── */}
                        <AnimatePresence>
                            {showPublicWarning && (
                                <motion.div
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    exit={{ opacity: 0 }}
                                    className="absolute inset-0 z-10 flex items-center justify-center bg-black/70 backdrop-blur-sm rounded-xl"
                                    onClick={() => setShowPublicWarning(false)}
                                >
                                    <motion.div
                                        initial={{ opacity: 0, scale: 0.95 }}
                                        animate={{ opacity: 1, scale: 1 }}
                                        exit={{ opacity: 0, scale: 0.95 }}
                                        className="bg-astral-surface border border-amber-500/20 rounded-xl p-6 shadow-2xl max-w-sm mx-4"
                                        onClick={(e) => e.stopPropagation()}
                                    >
                                        <div className="flex items-center gap-3 mb-3">
                                            <div className="w-10 h-10 rounded-lg bg-amber-500/15 flex items-center justify-center flex-shrink-0">
                                                <AlertTriangle size={20} className="text-amber-400" />
                                            </div>
                                            <h3 className="text-sm font-semibold text-white">Make Agent Public?</h3>
                                        </div>
                                        <div className="space-y-2 mb-5">
                                            <p className="text-xs text-astral-muted leading-relaxed">
                                                Making this agent <span className="text-white font-medium">publicly available</span> means:
                                            </p>
                                            <ul className="text-xs text-astral-muted space-y-1.5 ml-1">
                                                <li className="flex items-start gap-2">
                                                    <span className="text-amber-400 mt-0.5">&#8226;</span>
                                                    <span>All users in the system will be able to see and use this agent</span>
                                                </li>
                                                <li className="flex items-start gap-2">
                                                    <span className="text-amber-400 mt-0.5">&#8226;</span>
                                                    <span>Other users will have access to the agent's tools and capabilities</span>
                                                </li>
                                                <li className="flex items-start gap-2">
                                                    <span className="text-amber-400 mt-0.5">&#8226;</span>
                                                    <span>You retain ownership and can make it private again at any time</span>
                                                </li>
                                            </ul>
                                        </div>
                                        <div className="flex justify-end gap-2">
                                            <button
                                                onClick={() => setShowPublicWarning(false)}
                                                className="px-4 py-2 text-xs font-medium text-astral-muted hover:text-white hover:bg-white/5 rounded-lg transition-colors"
                                            >
                                                Cancel
                                            </button>
                                            <button
                                                onClick={() => confirmVisibilityChange(true)}
                                                disabled={togglingVisibility}
                                                className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-amber-300 bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/20 rounded-lg transition-colors"
                                            >
                                                {togglingVisibility ? (
                                                    <Loader2 size={12} className="animate-spin" />
                                                ) : (
                                                    <Globe size={12} />
                                                )}
                                                <span>Confirm &mdash; Make Public</span>
                                            </button>
                                        </div>
                                    </motion.div>
                                </motion.div>
                            )}
                        </AnimatePresence>

                        {/* ── Scope Warning Confirmation Dialog ────────── */}
                        <AnimatePresence>
                            {pendingScopeToggle && (
                                <motion.div
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    exit={{ opacity: 0 }}
                                    className="absolute inset-0 z-10 flex items-center justify-center bg-black/70 backdrop-blur-sm rounded-xl"
                                    onClick={() => setPendingScopeToggle(null)}
                                >
                                    <motion.div
                                        initial={{ opacity: 0, scale: 0.95 }}
                                        animate={{ opacity: 1, scale: 1 }}
                                        exit={{ opacity: 0, scale: 0.95 }}
                                        className="bg-astral-surface border border-amber-500/20 rounded-xl p-6 shadow-2xl max-w-sm mx-4"
                                        onClick={(e) => e.stopPropagation()}
                                    >
                                        <div className="flex items-center gap-3 mb-3">
                                            <div className={`w-10 h-10 rounded-lg ${pendingScopeToggle.bgClass}/15 flex items-center justify-center flex-shrink-0`}>
                                                <AlertTriangle size={20} className="text-amber-400" />
                                            </div>
                                            <h3 className="text-sm font-semibold text-white">
                                                Enable {pendingScopeToggle.label} Scope?
                                            </h3>
                                        </div>
                                        <p className="text-xs text-astral-muted leading-relaxed mb-5">
                                            {pendingScopeToggle.warning}
                                        </p>
                                        <div className="flex justify-end gap-2">
                                            <button
                                                onClick={() => setPendingScopeToggle(null)}
                                                className="px-4 py-2 text-xs font-medium text-astral-muted hover:text-white hover:bg-white/5 rounded-lg transition-colors"
                                            >
                                                Cancel
                                            </button>
                                            <button
                                                onClick={confirmScopeToggle}
                                                className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg transition-colors
                                                    ${pendingScopeToggle.colorClass} ${pendingScopeToggle.bgClass}/15 hover:${pendingScopeToggle.bgClass}/25
                                                    border ${pendingScopeToggle.bgClass}/20`}
                                            >
                                                <ShieldCheck size={12} />
                                                <span>Enable {pendingScopeToggle.label}</span>
                                            </button>
                                        </div>
                                    </motion.div>
                                </motion.div>
                            )}
                        </AnimatePresence>

                        {/* ── Scrollable Content ──────────────────────── */}
                        <div className="px-6 py-4 flex-1 min-h-0 overflow-y-auto space-y-5">

                            {/* ── Visibility Toggle (owner only) ─────────── */}
                            {isOwner && onSetVisibility && (
                                <div>
                                    <p className="text-[10px] font-semibold uppercase tracking-widest text-astral-muted flex items-center gap-1.5 mb-2">
                                        {localIsPublic ? <Globe size={10} /> : <Lock size={10} />}
                                        Visibility
                                    </p>
                                    <div
                                        className={`flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors
                                            ${localIsPublic
                                                ? "bg-green-500/[0.06] border border-green-500/10"
                                                : "bg-white/[0.03] border border-white/5"}`}
                                        onClick={handleVisibilityToggle}
                                    >
                                        <div className={`w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0
                                            ${localIsPublic ? "bg-green-500/15 text-green-400" : "bg-white/5 text-astral-muted"}`}>
                                            {localIsPublic ? <Globe size={14} /> : <Lock size={14} />}
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-xs font-medium text-white">
                                                {localIsPublic ? "Public Agent" : "Private Agent"}
                                            </p>
                                            <p className="text-[10px] text-astral-muted mt-0.5">
                                                {localIsPublic
                                                    ? "Visible to all users in the system"
                                                    : "Only visible to you"}
                                            </p>
                                        </div>
                                        {/* Toggle Switch */}
                                        <div
                                            className={`relative w-9 h-5 rounded-full flex-shrink-0 transition-colors duration-200
                                                ${localIsPublic ? "bg-green-500" : "bg-white/10"}`}
                                        >
                                            <motion.div
                                                className="absolute top-0.5 w-4 h-4 rounded-full shadow-sm bg-white"
                                                animate={{ left: localIsPublic ? "18px" : "2px" }}
                                                transition={{ type: "spring", stiffness: 500, damping: 30 }}
                                            />
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* ── Credentials Section ────────────────────── */}
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

                            {/* ── LinkedIn Connection Status ──────────────── */}
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

                            {/* ── Credential Lock Banner ─────────────────── */}
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

                            {/* ── Per-Tool Permissions (Feature 013 / FR-010, FR-011, FR-014) ─
                                One row per tool, exposing only the permission kind that
                                applies to that tool. The (i) icon is reachable while the
                                toggle is OFF (FR-011) so the user can read what enabling
                                will allow before consenting. The localScopes / localToolOverrides
                                state shape is preserved so the existing save path stays
                                compatible — the orchestrator's PUT endpoint mirrors
                                scope+override updates to per-(tool, kind) rows. */}
                            <div className={needsCredentials ? "opacity-40 pointer-events-none select-none" : ""}>
                                <p className="text-[10px] font-semibold uppercase tracking-widest text-astral-muted flex items-center gap-1.5 mb-3">
                                    <Shield size={10} />
                                    Tool permissions
                                </p>

                                {/* General info banner */}
                                <div className="flex items-start gap-2.5 px-3 py-2.5 rounded-lg bg-blue-500/[0.06] border border-blue-500/10 mb-3">
                                    <Info size={14} className="text-blue-400 flex-shrink-0 mt-0.5" />
                                    <p className="text-[10.5px] text-blue-300/80 leading-relaxed">
                                        Each tool below shows the kind of permission it needs (Read,
                                        Write, Search, or System). Hover the <span className="inline-flex"><Info size={10} className="inline" /></span>
                                        {" "}icon to see what enabling that permission lets the agent do
                                        — before you turn it on. Toggling one tool does not affect any
                                        other tool's state.
                                    </p>
                                </div>

                                {Object.keys(permissions).length === 0 ? (
                                    <div className="text-center py-8">
                                        <ShieldX size={24} className="text-astral-muted mx-auto mb-2" />
                                        <p className="text-xs text-astral-muted">No tools registered for this agent</p>
                                    </div>
                                ) : (
                                    <ul
                                        data-testid="per-tool-permission-list"
                                        className="space-y-1.5 max-h-[420px] overflow-y-auto pr-1"
                                    >
                                        {/* Stable order: by required kind, then alphabetically. */}
                                        {Object.keys(permissions)
                                            .slice()
                                            .sort((a, b) => {
                                                const ka = toolScopeMap[a] || "tools:read";
                                                const kb = toolScopeMap[b] || "tools:read";
                                                if (ka !== kb) return ka.localeCompare(kb);
                                                return a.localeCompare(b);
                                            })
                                            .map((tool) => {
                                                const requiredScope = toolScopeMap[tool] || "tools:read";
                                                const scopeDef = SCOPE_DEFINITIONS.find(s => s.key === requiredScope) ?? SCOPE_DEFINITIONS[0];
                                                const flag = securityFlags?.[tool];
                                                const isBlocked = flag?.blocked === true;
                                                // Effective enabled state: scope must be on AND no per-tool disable override.
                                                const scopeOn = !!localScopes[scopeDef.key];
                                                const overrideEnabled = localToolOverrides[tool] ?? true;
                                                const enabled = scopeOn && overrideEnabled && !isBlocked;
                                                return (
                                                    <li
                                                        key={tool}
                                                        data-testid={`per-tool-row-${tool}`}
                                                        className={`flex items-start gap-3 px-3 py-2.5 rounded-lg border transition-colors ${
                                                            isBlocked
                                                                ? "bg-red-500/[0.06] border-red-500/20"
                                                                : enabled
                                                                ? `${scopeDef.bgClass}/[0.06] border-${scopeDef.color}-500/15`
                                                                : "bg-white/[0.02] border-white/5 hover:border-white/10"
                                                        }`}
                                                    >
                                                        {/* Permission-kind icon */}
                                                        <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 ${
                                                            enabled
                                                                ? `${scopeDef.bgClass}/15 ${scopeDef.colorClass}`
                                                                : "bg-white/5 text-astral-muted"
                                                        }`}>
                                                            {scopeDef.icon}
                                                        </div>

                                                        {/* Tool name + description + permission-kind badge */}
                                                        <div className="flex-1 min-w-0">
                                                            <div className="flex items-center gap-2 flex-wrap">
                                                                <p className={`text-xs font-medium ${isBlocked ? "text-red-300" : "text-white"}`}>
                                                                    {formatToolName(tool)}
                                                                </p>
                                                                <span
                                                                    className={`text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${
                                                                        enabled
                                                                            ? `${scopeDef.bgClass}/20 ${scopeDef.colorClass}`
                                                                            : "bg-white/5 text-astral-muted"
                                                                    }`}
                                                                    title={`Required permission: ${scopeDef.label}`}
                                                                >
                                                                    {scopeDef.label}
                                                                </span>
                                                                {/* (i) info — reachable BEFORE the toggle is on (FR-011) */}
                                                                <span
                                                                    className="text-astral-muted/70 hover:text-astral-primary focus:text-astral-primary transition-colors cursor-help"
                                                                    tabIndex={0}
                                                                    role="img"
                                                                    aria-label={`What ${scopeDef.label} permission grants`}
                                                                    title={scopeDef.warning}
                                                                    data-testid={`per-tool-info-${tool}`}
                                                                >
                                                                    <Info size={11} />
                                                                </span>
                                                            </div>
                                                            <p className="text-[10.5px] text-astral-muted/80 mt-0.5 leading-relaxed">
                                                                {toolDescriptions[tool] || "No description available"}
                                                            </p>
                                                            {isBlocked && flag && (
                                                                <div className="flex items-center gap-1 mt-1">
                                                                    <AlertTriangle size={9} className="text-red-400 flex-shrink-0" />
                                                                    <p className="text-[9px] text-red-400/80">
                                                                        <span className="font-medium">{SECURITY_CATEGORY_LABELS[flag.category] || flag.category}</span>
                                                                        {" — "}{flag.reason}
                                                                    </p>
                                                                </div>
                                                            )}
                                                        </div>

                                                        {/* Per-tool toggle (FR-010, FR-012). System-blocked tools are
                                                            never user-toggleable — the proactive review wins. */}
                                                        {isBlocked ? (
                                                            <ShieldAlert size={14} className="text-red-400 mt-0.5 flex-shrink-0" />
                                                        ) : (
                                                            <button
                                                                type="button"
                                                                role="switch"
                                                                aria-checked={enabled}
                                                                aria-label={enabled ? `Disable ${formatToolName(tool)}` : `Enable ${formatToolName(tool)}`}
                                                                data-testid={`per-tool-toggle-${tool}`}
                                                                onClick={() => {
                                                                    if (!scopeOn && !enabled) {
                                                                        // First time enabling something of this kind:
                                                                        // surface the consent warning (FR-011 — pre-toggle
                                                                        // info already shown via the (i) icon, this is the
                                                                        // explicit confirm step). Tag the triggering tool
                                                                        // so confirmScopeToggle only enables this one and
                                                                        // leaves siblings explicitly disabled.
                                                                        setPendingScopeToggle({ ...scopeDef, triggeringTool: tool });
                                                                        return;
                                                                    }
                                                                    // Scope is already on — flipping the per-tool override.
                                                                    toggleToolOverride(tool);
                                                                }}
                                                                className={`relative w-9 h-5 rounded-full flex-shrink-0 transition-colors duration-200 mt-0.5 ${
                                                                    enabled ? scopeDef.bgClass : "bg-white/10 hover:bg-white/15"
                                                                }`}
                                                            >
                                                                <motion.div
                                                                    className="absolute top-0.5 w-4 h-4 rounded-full shadow-sm bg-white"
                                                                    animate={{ left: enabled ? "18px" : "2px" }}
                                                                    transition={{ type: "spring", stiffness: 500, damping: 30 }}
                                                                />
                                                            </button>
                                                        )}
                                                    </li>
                                                );
                                            })}
                                    </ul>
                                )}
                            </div>
                        </div>

                        {/* ── Footer ──────────────────────────────────── */}
                        <div className="flex items-center justify-end px-6 py-4 border-t border-white/5 bg-white/[0.02]">
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
