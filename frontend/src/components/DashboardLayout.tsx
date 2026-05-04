/**
 * DashboardLayout — Main app shell with sidebar and header.
 * Shows connected agents, their tools, and connection status.
 */
import React, { useState, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
    LayoutDashboard,
    Bot,
    Wrench,
    Wifi,
    WifiOff,
    LogOut,
    Activity,
    MessageSquare,
    Plus,
    Grid,
    X,
    Shield,
    Menu,
    Search,
    KeyRound,
    ChevronRight,
    Globe,
    Lock,
    User,
    FileCode,
    Trash2,
} from "lucide-react";
import { API_URL } from "../config";
import type { Agent, ChatSession, AgentPermissionsData, ConnectionState } from "../hooks/useWebSocket";
import AgentPermissionsModal from "./AgentPermissionsModal";
import CreateAgentModal from "./CreateAgentModal";
import { Tooltip } from "./onboarding/Tooltip";
import { tooltipCatalog } from "./onboarding/tooltipCatalog";
import { SettingsMenu } from "./settings/SettingsMenu";
import { useFlaggedToolsCount } from "./useFlaggedToolsCount";

interface DashboardLayoutProps {
    children: React.ReactNode;
    agents: Agent[];
    isConnected: boolean;
    connectionState?: ConnectionState;
    onLogout: () => void;
    chatHistory?: ChatSession[];
    activeChatId?: string | null;
    onLoadChat?: (chatId: string) => void;
    onNewChat?: () => void;
    onDeleteChat?: (chatId: string) => void;
    isAdmin?: boolean;
    accessToken?: string;
    userEmail?: string;
    agentPermissions?: AgentPermissionsData | null;
    onGetAgentPermissions?: (agentId: string) => void;
    onSetAgentPermissions?: (agentId: string, scopes: Record<string, boolean>, toolOverrides?: Record<string, boolean>) => void;
    onRegisterExternalAgent?: (url: string) => void;
    onOpenAuditLog?: () => void;
    /** Feature 006 — opens the LLM Settings overlay (per-device personal LLM config). */
    onOpenLlmSettings?: () => void;
    onOpenFeedbackAdmin?: () => void;
    /** Feature 005 — replays the getting-started tutorial overlay. */
    onReplayTutorial?: () => void;
    /** Feature 005 — opens the admin tutorial-step editor (admin only). */
    onOpenTutorialAdmin?: () => void;
    /** Feature 005 — opens the static User Guide overlay. */
    onOpenUserGuide?: () => void;
    // Credential management
    agentCredentialKeys?: Record<string, string[]>;
    onFetchAgentCredentials?: (agentId: string) => Promise<unknown>;
    onSaveAgentCredentials?: (agentId: string, credentials: Record<string, string>) => Promise<boolean>;
    onDeleteAgentCredential?: (agentId: string, key: string) => Promise<boolean>;
    onStartOAuthFlow?: (agentId: string) => Promise<boolean>;
    onSetAgentVisibility?: (agentId: string, isPublic: boolean) => Promise<boolean>;
    onDiscoverAgents?: () => void;
    /**
     * Feature 008-llm-text-only-chat: bumped (e.g., from Date.now()) by an
     * external caller — typically the persistent text-only banner's
     * "Enable agents" button — to ask DashboardLayout to open its agents
     * modal. Each new value triggers exactly one open. The default
     * undefined is a no-op for callers that don't use the affordance.
     */
    requestOpenAgentsModalKey?: number;
}

export default function DashboardLayout({
    children,
    agents,
    isConnected,
    connectionState = "disconnected",
    onLogout,
    chatHistory = [],
    activeChatId,
    onLoadChat,
    onNewChat,
    onDeleteChat,
    isAdmin = false,
    accessToken,
    userEmail,
    agentPermissions,
    onGetAgentPermissions,
    onSetAgentPermissions,
    agentCredentialKeys = {},
    onFetchAgentCredentials,
    onSaveAgentCredentials,
    onDeleteAgentCredential,
    onStartOAuthFlow,
    onSetAgentVisibility,
    onRegisterExternalAgent,
    onDiscoverAgents,
    onOpenAuditLog,
    onOpenLlmSettings,
    onOpenFeedbackAdmin,
    onReplayTutorial,
    onOpenTutorialAdmin,
    onOpenUserGuide,
    requestOpenAgentsModalKey,
}: DashboardLayoutProps) {
    const [chatToDelete, setChatToDelete] = useState<string | null>(null);
    const [permModalAgent, setPermModalAgent] = useState<string | null>(null);
    const { count: flaggedToolsCount, refresh: refreshFlaggedToolsCount } =
        useFlaggedToolsCount(accessToken, isAdmin);
    // When admin opens the FeedbackAdminPanel, that's an "explicit
    // user action" per spec FR-004, so we invalidate the session cache
    // and refetch so the badge reflects the current backend state on
    // close. Only wired up when the parent provides the open callback.
    const onOpenFeedbackAdminWithRefresh = useMemo(() => {
        if (!onOpenFeedbackAdmin) return undefined;
        return () => {
            refreshFlaggedToolsCount();
            onOpenFeedbackAdmin();
        };
    }, [onOpenFeedbackAdmin, refreshFlaggedToolsCount]);
    const [sidebarOpen, setSidebarOpen] = useState(() => {
        const saved = localStorage.getItem("sidebarOpen");
        if (saved !== null) return saved === "true";
        return window.innerWidth >= 768;
    });

    useEffect(() => {
        localStorage.setItem("sidebarOpen", String(sidebarOpen));
    }, [sidebarOpen]);
    const [chatSearch, setChatSearch] = useState("");
    const [agentsModalOpen, setAgentsModalOpen] = useState(false);
    const [agentsTab, setAgentsTab] = useState<"my" | "all" | "drafts">("my");
    const [externalAgentUrl, setExternalAgentUrl] = useState("");
    const [createAgentOpen, setCreateAgentOpen] = useState(false);
    const [resumeDraftId, setResumeDraftId] = useState<string | null>(null);

    // Draft agents
    interface DraftAgentSummary {
        id: string;
        agent_name: string;
        agent_slug: string;
        description: string;
        status: string;
        port?: number | null;
        created_at?: number;
    }
    const [drafts, setDrafts] = useState<DraftAgentSummary[]>([]);
    const [draftsLoading, setDraftsLoading] = useState(false);

    const fetchDrafts = useCallback(async () => {
        if (!accessToken) return;
        setDraftsLoading(true);
        try {
            const resp = await fetch(`${API_URL}/api/agents/drafts`, {
                headers: { Authorization: `Bearer ${accessToken}` },
            });
            if (resp.ok) {
                const data = await resp.json();
                setDrafts(data.drafts || []);
            }
        } catch { /* ignore */ }
        finally { setDraftsLoading(false); }
    }, [accessToken]);

    // Fetch drafts when switching to Drafts tab or opening modal
    useEffect(() => {
        if (agentsModalOpen && agentsTab === "drafts") {
            fetchDrafts();
        }
    }, [agentsModalOpen, agentsTab, fetchDrafts]);

    const deleteDraft = async (draftId: string) => {
        if (!accessToken) return;
        try {
            await fetch(`${API_URL}/api/agents/drafts/${draftId}`, {
                method: "DELETE",
                headers: { Authorization: `Bearer ${accessToken}` },
            });
            setDrafts(prev => prev.filter(d => d.id !== draftId));
        } catch { /* ignore */ }
    };

    const openDraftInModal = (draftId: string) => {
        setAgentsModalOpen(false);
        setResumeDraftId(draftId);
        setCreateAgentOpen(true);
    };

    // Close delete modal on Escape
    useEffect(() => {
        if (!chatToDelete) return;
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") setChatToDelete(null);
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => document.removeEventListener("keydown", handleKeyDown);
    }, [chatToDelete]);

    // Close agents modal on Escape
    useEffect(() => {
        if (!agentsModalOpen) return;
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") setAgentsModalOpen(false);
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => document.removeEventListener("keydown", handleKeyDown);
    }, [agentsModalOpen]);

    // Feature 008-llm-text-only-chat: external request to open the
    // agents modal (e.g., from the text-only banner's "Enable agents"
    // button). The first render's `undefined` does nothing; every
    // subsequent change opens the modal once.
    useEffect(() => {
        if (requestOpenAgentsModalKey === undefined) return;
        setAgentsModalOpen(true);
    }, [requestOpenAgentsModalKey]);

    // Open the per-agent Permissions modal. We do NOT close the agents modal —
    // the Permissions modal stacks ON TOP of it (same fixed inset-0, rendered
    // later in the DOM, with a higher z-index). When the user dismisses the
    // Permissions modal they're back on the agents list naturally.
    //
    // Story 4 background: the previous code called setAgentsModalOpen(false)
    // here, but the Permissions modal only mounts once async permissions data
    // arrives — leaving an empty-frame gap that users perceived as the modal
    // "closing and the page refreshing." Stacking eliminates that gap entirely
    // and survives the case where the permissions response is delayed or
    // missing (e.g. for public agents where the user has no row yet).
    const openPermissionsModal = (agentId: string) => {
        setPermModalAgent(agentId);
        onGetAgentPermissions?.(agentId);
        // Fetch stored credential keys for agents that need them
        const agent = agents.find(a => a.id === agentId);
        if (agent?.metadata?.required_credentials?.length) {
            onFetchAgentCredentials?.(agentId);
        }
    };

    const totalTools = agents.reduce((sum, a) => {
        const blockedSet = new Set(
            Object.entries(a.security_flags || {})
                .filter(([, f]) => (f as { blocked?: boolean }).blocked)
                .map(([name]) => name)
        );
        if (a.permissions) {
            return sum + Object.entries(a.permissions).filter(([name, allowed]) => allowed && !blockedSet.has(name)).length;
        }
        return sum + a.tools.filter(t => !blockedSet.has(t)).length;
    }, 0);

    /** Helper: get status info for an agent */
    const getAgentStatus = (agent: Agent) => {
        const reqCreds = agent.metadata?.required_credentials || [];
        const storedKeys = agentCredentialKeys[agent.id] || [];
        const hasMissingCreds = reqCreds.some(c => c.required && !storedKeys.includes(c.key));

        const blocked = new Set(
            Object.entries(agent.security_flags || {})
                .filter(([, f]) => (f as { blocked?: boolean }).blocked)
                .map(([n]) => n)
        );
        const activeTools = agent.permissions
            ? Object.entries(agent.permissions).filter(([n, v]) => v && !blocked.has(n)).length
            : agent.tools.filter(t => !blocked.has(t)).length;

        const hasSecurityFlags = agent.security_flags &&
            Object.values(agent.security_flags).some((f: unknown) => (f as { blocked?: boolean }).blocked);

        let statusColor = "bg-green-400";
        let statusLabel = "All tools enabled";
        if (hasMissingCreds) {
            statusColor = "bg-amber-400";
            statusLabel = "Credentials required";
        } else if (hasSecurityFlags) {
            statusColor = "bg-red-500";
            statusLabel = "Security flags";
        } else if (agent.permissions) {
            const perms = Object.values(agent.permissions);
            const allEnabled = perms.every(Boolean);
            const allDisabled = perms.every(v => !v);
            if (allDisabled) { statusColor = "bg-red-400"; statusLabel = "All tools disabled"; }
            else if (!allEnabled) { statusColor = "bg-amber-400"; statusLabel = "Some tools restricted"; }
        }

        return { hasMissingCreds, activeTools, statusColor, statusLabel };
    };

    return (
        <div className="h-dvh flex overflow-hidden bg-astral-bg relative">

            {/* Delete Confirmation Modal */}
            {chatToDelete && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setChatToDelete(null)}>
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="bg-astral-surface border border-white/10 rounded-xl p-6 shadow-2xl max-w-sm w-full mx-4"
                        role="dialog"
                        aria-modal="true"
                        aria-label="Delete chat confirmation"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <h3 className="text-lg font-medium text-white mb-2">Delete Chat?</h3>
                        <p className="text-sm text-astral-muted mb-6">
                            Are you sure you want to delete this chat? This action cannot be undone.
                        </p>
                        <div className="flex justify-end gap-3">
                            <button
                                onClick={() => setChatToDelete(null)}
                                className="px-4 py-2 text-sm font-medium text-astral-muted hover:text-white hover:bg-white/5 rounded-lg transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={() => {
                                    if (onDeleteChat) onDeleteChat(chatToDelete);
                                    setChatToDelete(null);
                                }}
                                className="px-4 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors"
                            >
                                Delete
                            </button>
                        </div>
                    </motion.div>
                </div>
            )}

            {/* Agents Grid Modal */}
            <AnimatePresence>
                {agentsModalOpen && (() => {
                    const myAgents = agents.filter(a => a.owner_email === userEmail || !a.owner_email);
                    const publicAgents = agents.filter(a => a.is_public);
                    const filteredAgents = agentsTab === "my" ? myAgents : publicAgents;

                    return (
                    <div
                        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
                        onClick={() => setAgentsModalOpen(false)}
                    >
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.95 }}
                            transition={{ duration: 0.15 }}
                            className="bg-astral-surface border border-white/10 rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col"
                            role="dialog"
                            aria-modal="true"
                            aria-label="Connected agents"
                            onClick={(e) => e.stopPropagation()}
                        >
                            {/* Header */}
                            <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
                                <div className="flex items-center gap-3">
                                    <div className="w-8 h-8 rounded-lg bg-astral-primary/20 flex items-center justify-center">
                                        <Bot size={16} className="text-astral-primary" />
                                    </div>
                                    <div>
                                        <h2 className="text-base font-semibold text-white">Agents</h2>
                                        <p className="text-xs text-astral-muted">{agents.length} agent{agents.length !== 1 ? "s" : ""} connected &middot; {totalTools} tools available</p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-1.5">
                                    <button
                                        onClick={() => { setAgentsModalOpen(false); setCreateAgentOpen(true); }}
                                        className="p-1.5 rounded-lg hover:bg-astral-accent/15 transition-colors group"
                                        title="Create new agent"
                                    >
                                        <Plus size={16} className="text-astral-muted group-hover:text-astral-accent" />
                                    </button>
                                    <button
                                        onClick={() => setAgentsModalOpen(false)}
                                        className="p-1.5 rounded-lg hover:bg-white/10 transition-colors"
                                    >
                                        <X size={16} className="text-astral-muted" />
                                    </button>
                                </div>
                            </div>

                            {/* Tabs */}
                            <div className="flex items-center gap-1 px-6 pt-3 pb-0">
                                <button
                                    onClick={() => setAgentsTab("my")}
                                    className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors
                                        ${agentsTab === "my"
                                            ? "bg-astral-primary/15 text-astral-primary border border-astral-primary/20"
                                            : "text-astral-muted hover:text-white hover:bg-white/5 border border-transparent"}`}
                                >
                                    <User size={12} />
                                    My Agents
                                    <span className="text-[10px] opacity-60">({myAgents.length})</span>
                                </button>
                                <button
                                    onClick={() => setAgentsTab("all")}
                                    className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors
                                        ${agentsTab === "all"
                                            ? "bg-astral-primary/15 text-astral-primary border border-astral-primary/20"
                                            : "text-astral-muted hover:text-white hover:bg-white/5 border border-transparent"}`}
                                >
                                    <Globe size={12} />
                                    Public Agents
                                    <span className="text-[10px] opacity-60">({publicAgents.length})</span>
                                </button>
                                <button
                                    onClick={() => setAgentsTab("drafts")}
                                    className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors
                                        ${agentsTab === "drafts"
                                            ? "bg-astral-accent/15 text-astral-accent border border-astral-accent/20"
                                            : "text-astral-muted hover:text-white hover:bg-white/5 border border-transparent"}`}
                                >
                                    <FileCode size={12} />
                                    Drafts
                                    {drafts.length > 0 && <span className="text-[10px] opacity-60">({drafts.length})</span>}
                                </button>
                            </div>

                            {/* Register External Agent */}
                            {onRegisterExternalAgent && (
                                <div className="px-6 pt-3">
                                    <form
                                        onSubmit={(e) => {
                                            e.preventDefault();
                                            const url = externalAgentUrl.trim();
                                            if (url) {
                                                onRegisterExternalAgent(url);
                                                setExternalAgentUrl("");
                                            }
                                        }}
                                        className="flex gap-2"
                                    >
                                        <input
                                            type="url"
                                            value={externalAgentUrl}
                                            onChange={(e) => setExternalAgentUrl(e.target.value)}
                                            placeholder="Register external A2A agent URL..."
                                            className="flex-1 px-3 py-1.5 text-xs bg-white/5 border border-white/10 rounded-lg
                                                       text-white placeholder-astral-muted/50 focus:outline-none focus:border-astral-primary/40"
                                        />
                                        <button
                                            type="submit"
                                            disabled={!externalAgentUrl.trim()}
                                            className="px-3 py-1.5 text-xs font-medium rounded-lg bg-astral-primary/15 text-astral-primary
                                                       border border-astral-primary/20 hover:bg-astral-primary/25 transition-colors
                                                       disabled:opacity-30 disabled:cursor-not-allowed"
                                        >
                                            <Plus size={12} />
                                        </button>
                                    </form>
                                </div>
                            )}

                            {/* Grid */}
                            <div className="flex-1 overflow-y-auto p-4">
                                {/* Drafts tab */}
                                {agentsTab === "drafts" ? (
                                    draftsLoading ? (
                                        <div className="flex items-center justify-center py-12 text-astral-muted">
                                            <span className="text-sm">Loading drafts...</span>
                                        </div>
                                    ) : drafts.length === 0 ? (
                                        <div className="flex flex-col items-center justify-center py-12 text-astral-muted">
                                            <FileCode size={32} className="mb-3 opacity-30" />
                                            <p className="text-sm">No draft agents yet</p>
                                            <p className="text-xs opacity-60 mt-1">Create a new agent to get started.</p>
                                        </div>
                                    ) : (
                                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                            {drafts.map((d) => {
                                                const statusColors: Record<string, string> = {
                                                    pending: "bg-gray-400", generating: "bg-blue-400 animate-pulse",
                                                    generated: "bg-green-400", testing: "bg-amber-400 animate-pulse",
                                                    analyzing: "bg-blue-400 animate-pulse", approved: "bg-green-400",
                                                    pending_review: "bg-amber-400", rejected: "bg-red-400",
                                                    live: "bg-green-400", error: "bg-red-400",
                                                };
                                                const statusLabels: Record<string, string> = {
                                                    pending: "Pending", generating: "Generating...",
                                                    generated: "Ready to Test", testing: "Testing",
                                                    analyzing: "Analyzing...", approved: "Approved",
                                                    pending_review: "Awaiting Review", rejected: "Rejected",
                                                    live: "Live", error: "Error",
                                                };
                                                return (
                                                    <div
                                                        key={d.id}
                                                        className="flex items-start gap-3 p-4 rounded-xl border border-white/5 bg-white/[0.02]
                                                                   hover:bg-white/5 hover:border-astral-accent/20 transition-all text-left group"
                                                    >
                                                        <button
                                                            onClick={() => openDraftInModal(d.id)}
                                                            className="flex items-start gap-3 flex-1 min-w-0 text-left"
                                                        >
                                                            <div className="w-9 h-9 rounded-lg bg-astral-accent/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                                                                <FileCode size={16} className="text-astral-accent" />
                                                            </div>
                                                            <div className="flex-1 min-w-0">
                                                                <div className="flex items-center gap-2">
                                                                    <p className="text-sm font-medium text-white truncate">{d.agent_name}</p>
                                                                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${statusColors[d.status] || "bg-gray-400"}`} />
                                                                </div>
                                                                <p className="text-[11px] text-astral-muted mt-0.5 line-clamp-2">{d.description}</p>
                                                                <div className="flex items-center gap-2 mt-1.5">
                                                                    <span className="text-[10px] text-astral-muted/70">
                                                                        {statusLabels[d.status] || d.status}
                                                                    </span>
                                                                    {d.port && (
                                                                        <span className="text-[10px] text-astral-muted/50">Port {d.port}</span>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        </button>
                                                        <button
                                                            onClick={() => deleteDraft(d.id)}
                                                            className="p-1.5 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-red-500/10 text-astral-muted hover:text-red-400 transition-all flex-shrink-0"
                                                            title="Delete draft"
                                                        >
                                                            <Trash2 size={12} />
                                                        </button>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )
                                ) : filteredAgents.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center py-12 text-astral-muted">
                                        <Bot size={32} className="mb-3 opacity-30" />
                                        <p className="text-sm">
                                            {agentsTab === "my" ? "No agents owned by you" : "No public agents available"}
                                        </p>
                                        <p className="text-xs opacity-60 mt-1">
                                            {agentsTab === "my"
                                                ? "Agents you create or are assigned to you will appear here."
                                                : "When other users make their agents public, they'll appear here."}
                                        </p>
                                    </div>
                                ) : (
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                        {filteredAgents.map((agent) => {
                                            const { hasMissingCreds, activeTools, statusColor, statusLabel } = getAgentStatus(agent);
                                            const isOwner = agent.owner_email === userEmail;
                                            return (
                                                <button
                                                    key={agent.id}
                                                    type="button"
                                                    onClick={(e) => { e.stopPropagation(); openPermissionsModal(agent.id); }}
                                                    className="flex items-start gap-3 p-4 rounded-xl border border-white/5 bg-white/[0.02]
                                                               hover:bg-white/5 hover:border-astral-primary/20 transition-all text-left group"
                                                >
                                                    <div className="w-9 h-9 rounded-lg bg-astral-primary/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                                                        <Activity size={16} className="text-astral-primary" />
                                                    </div>
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-2">
                                                            <p className="text-sm font-medium text-white truncate">{agent.name}</p>
                                                            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${statusColor} ${hasMissingCreds ? "animate-pulse" : ""}`} title={statusLabel} />
                                                            {hasMissingCreds && (
                                                                <KeyRound size={10} className="text-amber-400 flex-shrink-0 animate-pulse" />
                                                            )}
                                                            <span title={agent.is_public ? "Public" : "Private"}>
                                                                {agent.is_public ? (
                                                                    <Globe size={10} className="text-green-400/60 flex-shrink-0" />
                                                                ) : (
                                                                    <Lock size={10} className="text-astral-muted/40 flex-shrink-0" />
                                                                )}
                                                            </span>
                                                        </div>
                                                        {agent.description && (
                                                            <p className="text-[11px] text-astral-muted mt-0.5 line-clamp-2">{agent.description}</p>
                                                        )}
                                                        <div className="flex items-center gap-2 mt-1.5">
                                                            <span className="text-[10px] text-astral-muted/70 flex items-center gap-1">
                                                                <Wrench size={9} />
                                                                {activeTools} tool{activeTools !== 1 ? "s" : ""} active
                                                            </span>
                                                            {!isOwner && agent.owner_email && (
                                                                <span className="text-[10px] text-astral-muted/50 truncate">
                                                                    by {agent.owner_email}
                                                                </span>
                                                            )}
                                                            <Shield size={10} className="text-astral-muted/30 group-hover:text-astral-primary transition-colors" />
                                                        </div>
                                                    </div>
                                                    <ChevronRight size={14} className="text-astral-muted/30 group-hover:text-astral-primary transition-colors mt-1 flex-shrink-0" />
                                                </button>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        </motion.div>
                    </div>
                    );
                })()}
            </AnimatePresence>

            {/* Mobile sidebar backdrop */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            {/* Sidebar — Gemini-style: collapses to icon rail on desktop, overlay on mobile */}
            <aside className={`
                flex flex-col border-r border-white/5 bg-astral-surface/30 backdrop-blur-xl flex-shrink-0 overflow-hidden
                fixed inset-y-0 left-0 z-50 w-64
                transform transition-all duration-200 ease-in-out
                ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}
                md:static md:z-auto md:translate-x-0
                ${sidebarOpen ? "md:w-64" : "md:w-16"}
            `}>
                {/* Logo / Brand */}
                <div className={`h-14 flex items-center border-b border-white/5 safe-top ${sidebarOpen ? "justify-between px-5" : "md:justify-center md:px-0 justify-between px-5"}`}>
                    <div className={`flex items-center gap-3 transition-opacity duration-200 ${sidebarOpen ? "opacity-100" : "md:opacity-0 md:w-0 md:overflow-hidden"}`}>
                        <div className="flex items-center">
                            <img
                                src="/AstralDeep.png"
                                alt="AstralDeep Logo"
                                className="h-8 w-auto object-contain"
                            />
                        </div>
                    </div>
                    {/* Mobile: X to close overlay */}
                    <button
                        onClick={() => setSidebarOpen(false)}
                        className="p-1.5 rounded-lg hover:bg-white/10 transition-colors md:hidden"
                    >
                        <X size={18} className="text-astral-muted" />
                    </button>
                    {/* Desktop: hamburger to toggle */}
                    <button
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                        className="p-1.5 rounded-lg hover:bg-white/10 transition-colors hidden md:block"
                    >
                        <Menu size={18} className="text-astral-muted" />
                    </button>
                </div>

                {/* Collapsed icon rail (desktop only) */}
                <div className={`flex-1 flex-col items-center pt-3 pb-4 gap-2 hidden ${sidebarOpen ? "md:hidden" : "md:flex"}`}>
                    <button
                        onClick={() => { onNewChat?.(); }}
                        className="p-2.5 rounded-lg hover:bg-white/10 transition-colors"
                        title="New chat"
                    >
                        <Plus size={18} className="text-astral-primary" />
                    </button>
                    <button
                        onClick={() => setAgentsModalOpen(true)}
                        className="p-2.5 rounded-lg hover:bg-white/10 transition-colors"
                        title={`Agents — ${agents.length} connected`}
                    >
                        <Bot size={18} className="text-astral-primary" />
                    </button>
                    {/* Feature 007 — single Settings entry replaces the per-feature
                        sidebar utility buttons (Audit, LLM, Tool quality, Tutorial admin,
                        Take the tour, User guide). */}
                    <SettingsMenu
                        variant="collapsed"
                        isAdmin={isAdmin}
                        flaggedToolsCount={flaggedToolsCount}
                        onOpenAuditLog={onOpenAuditLog}
                        onOpenLlmSettings={onOpenLlmSettings}
                        onOpenFeedbackAdmin={onOpenFeedbackAdminWithRefresh}
                        onOpenTutorialAdmin={onOpenTutorialAdmin}
                        onReplayTutorial={onReplayTutorial}
                        onOpenUserGuide={onOpenUserGuide}
                    />
                    <div className="flex-1" />
                    <div className="flex flex-col items-center gap-1 mb-1">
                        <span className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-400" : "bg-red-400"} ${connectionState === "reconnecting" || connectionState === "connecting" ? "animate-pulse" : ""}`}
                            title={isConnected ? "Connected" : "Disconnected"}
                        />
                    </div>
                    <button
                        onClick={onLogout}
                        className="p-2.5 rounded-lg hover:bg-white/10 transition-colors"
                        title="Sign Out"
                    >
                        <LogOut size={18} className="text-astral-muted" />
                    </button>
                </div>

                {/* Expanded navigation (always on mobile, conditional on desktop) */}
                <nav className={`flex-1 overflow-y-auto overflow-x-hidden py-4 px-3 space-y-6 ${sidebarOpen ? "" : "md:hidden"}`}>

                    {/* Status Section */}
                    <div>
                        <p className="px-2 text-[10px] font-semibold uppercase tracking-widest text-astral-muted mb-2">
                            Status
                        </p>
                        <div className="space-y-1">
                            <StatusItem
                                icon={isConnected ? <Wifi size={14} /> : <WifiOff size={14} />}
                                label="Orchestrator"
                                value={
                                    connectionState === "reconnecting" ? "Reconnecting..." :
                                    connectionState === "connecting" ? "Connecting..." :
                                    isConnected ? "Connected" : "Disconnected"
                                }
                                color={
                                    connectionState === "reconnecting" ? "text-yellow-400" :
                                    connectionState === "connecting" ? "text-yellow-400" :
                                    isConnected ? "text-green-400" : "text-red-400"
                                }
                                pulse={connectionState === "reconnecting" || connectionState === "connecting"}
                            />
                            <StatusItem
                                icon={<Bot size={14} />}
                                label="Agents"
                                value={`${agents.length} active`}
                                color="text-astral-accent"
                            />
                            <StatusItem
                                icon={<Wrench size={14} />}
                                label="Tools"
                                value={`${totalTools} available`}
                                color="text-astral-secondary"
                            />
                        </div>
                    </div>

                    {/* Agents Button */}
                    <div>
                        <Tooltip text={tooltipCatalog["sidebar.agents"]}>
                            <button
                                onClick={() => setAgentsModalOpen(true)}
                                data-tutorial-target="sidebar.agents"
                                className="w-full flex items-center gap-2 px-2 py-2 rounded-lg
                                           hover:bg-white/5 transition-colors group text-left"
                            >
                                <div className="w-6 h-6 rounded-md bg-astral-primary/20 flex items-center justify-center flex-shrink-0">
                                    <Bot size={12} className="text-astral-primary" />
                                </div>
                                <span className="text-xs font-medium text-white flex-1">Agents</span>
                                <span className="text-[10px] text-astral-muted">{agents.length} connected</span>
                                <ChevronRight size={12} className="text-astral-muted/50 group-hover:text-astral-primary transition-colors flex-shrink-0" />
                            </button>
                        </Tooltip>
                    </div>

                    {/* Settings (feature 007-sidebar-settings-menu) — single
                        consolidated entry that replaces the previous six
                        utility buttons (Audit log, LLM settings, Tool quality,
                        Tutorial admin, Take the tour, User guide). Each item
                        inside the popover preserves the original
                        `data-tutorial-target` key so existing tutorial steps
                        still resolve. */}
                    <div>
                        <Tooltip text={tooltipCatalog["sidebar.settings"]}>
                            <SettingsMenu
                                variant="expanded"
                                isAdmin={isAdmin}
                                flaggedToolsCount={flaggedToolsCount}
                                onOpenAuditLog={onOpenAuditLog}
                                onOpenLlmSettings={onOpenLlmSettings}
                                onOpenFeedbackAdmin={onOpenFeedbackAdminWithRefresh}
                                onOpenTutorialAdmin={onOpenTutorialAdmin}
                                onReplayTutorial={onReplayTutorial}
                                onOpenUserGuide={onOpenUserGuide}
                            />
                        </Tooltip>
                    </div>

                    {/* Recent Chats */}
                    <div>
                        <p className="px-2 text-[10px] font-semibold uppercase tracking-widest text-astral-muted mb-2">
                            Recent Chats
                        </p>
                        {chatHistory.length > 3 && (
                            <div className="px-1 mb-2">
                                <div className="flex items-center gap-1.5 bg-white/5 border border-white/5 rounded-lg px-2 py-1.5 focus-within:border-astral-primary/30">
                                    <Search size={12} className="text-astral-muted/50 flex-shrink-0" />
                                    <input
                                        type="text"
                                        name="chat-search-filter"
                                        placeholder="Search chats..."
                                        value={chatSearch}
                                        onChange={(e) => setChatSearch(e.target.value)}
                                        autoComplete="new-password"
                                        className="bg-transparent text-xs text-white placeholder:text-astral-muted/40 focus:outline-none w-full"
                                    />
                                    {chatSearch && (
                                        <button onClick={() => setChatSearch("")} className="text-astral-muted/50 hover:text-white">
                                            <X size={10} />
                                        </button>
                                    )}
                                </div>
                            </div>
                        )}
                        <div className="space-y-1">
                            {chatHistory.length === 0 && (
                                <p className="px-2 text-xs text-astral-muted/50 italic">
                                    No history yet...
                                </p>
                            )}
                            {chatHistory.filter(chat =>
                                !chatSearch || (chat.title || "").toLowerCase().includes(chatSearch.toLowerCase())
                            ).map((chat) => (
                                <div key={chat.id} className="relative group">
                                    <button
                                        onClick={() => { onLoadChat?.(chat.id); if (window.innerWidth < 768) setSidebarOpen(false); }}
                                        className={`w-full flex items-center gap-2 px-2 py-2 rounded-lg transition-colors text-left pr-8
                                        ${activeChatId === chat.id ? "bg-white/10 text-white" : "hover:bg-white/5 text-astral-muted hover:text-white"}`}
                                    >
                                        <MessageSquare size={14} className="flex-shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-1">
                                                <p className="text-xs font-medium truncate">
                                                    {chat.title || "Untitled Chat"}
                                                </p>
                                                {chat.has_saved_components && (
                                                    <div className="relative group/grid" onClick={(e) => e.stopPropagation()}>
                                                        <Grid size={10} className="text-astral-primary flex-shrink-0" />
                                                        <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-1 px-2 py-1 text-xs bg-astral-surface border border-white/10 rounded opacity-0 group-hover/grid:opacity-100 transition-opacity whitespace-nowrap z-10 pointer-events-none">
                                                            Contains saved UI components
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                            <p className="text-[10px] text-astral-muted/70 truncate">
                                                {new Date(chat.updated_at).toLocaleDateString()}
                                            </p>
                                        </div>
                                    </button>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setChatToDelete(chat.id);
                                        }}
                                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-astral-muted/50 hover:text-red-400 hover:bg-red-400/20 rounded opacity-0 group-hover:opacity-100 transition-all z-10"
                                        title="Delete chat"
                                    >
                                        <X size={14} />
                                    </button>
                                </div>
                            ))}
                        </div>
                    </div>
                </nav>

                {/* Footer (expanded only) */}
                <div className={`border-t border-white/5 p-3 ${sidebarOpen ? "" : "md:hidden"}`}>
                    <button
                        onClick={onLogout}
                        className="w-full flex items-center gap-2 px-3 py-2 text-xs text-astral-muted
                       hover:text-white hover:bg-white/5 rounded-lg transition-colors"
                    >
                        <LogOut size={14} />
                        <span>Sign Out</span>
                    </button>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 flex flex-col min-w-0">
                {/* Header */}
                <header className="h-14 relative flex items-center justify-between px-3 sm:px-6 border-b border-white/5 bg-astral-bg/80 backdrop-blur-md flex-shrink-0 safe-top">
                    <div className="flex items-center gap-2 sm:gap-3">
                        <button
                            onClick={() => setSidebarOpen(!sidebarOpen)}
                            className="p-2 rounded-lg hover:bg-white/10 transition-colors md:hidden"
                        >
                            <Menu size={20} className="text-astral-muted" />
                        </button>
                        <LayoutDashboard size={16} className="text-astral-muted hidden sm:block" />
                        <span className="text-sm font-medium text-white hidden sm:block">Dashboard</span>
                    </div>
                    {/* Centered logo — visible on mobile only */}
                    <div className="absolute left-1/2 -translate-x-1/2 md:hidden">
                        <img
                            src="/AstralDeep.png"
                            alt="AstralDeep Logo"
                            className="h-7 w-auto object-contain"
                        />
                    </div>
                    <div className="flex items-center gap-2 sm:gap-3">
                        <button
                            onClick={() => { onNewChat?.(); if (window.innerWidth < 768) setSidebarOpen(false); }}
                            className="flex items-center gap-2 px-3 py-1.5 bg-astral-primary/10
                                     border border-astral-primary/20 rounded-md text-xs font-medium
                                     text-astral-primary hover:bg-astral-primary/20 transition-colors"
                        >
                            <Plus size={14} />
                            <span className="hidden sm:inline">New Chat</span>
                        </button>
                    </div>
                </header>

                {/* Page Content */}
                <div className="flex-1 overflow-hidden">{children}</div>
            </main>

            {/* Create Agent Modal */}
            <CreateAgentModal
                isOpen={createAgentOpen}
                onClose={() => { setCreateAgentOpen(false); setResumeDraftId(null); }}
                accessToken={accessToken}
                onAgentCreated={() => {
                    setCreateAgentOpen(false);
                    setResumeDraftId(null);
                    setAgentsTab("my");
                    setAgentsModalOpen(true);
                    // Refresh agent list after a short delay to allow the new agent to register
                    if (onDiscoverAgents) {
                        setTimeout(() => onDiscoverAgents(), 2000);
                        setTimeout(() => onDiscoverAgents(), 5000);
                    }
                }}
                resumeDraftId={resumeDraftId}
            />

            {/* Agent Permissions Modal */}
            {permModalAgent && agentPermissions && agentPermissions.agent_id === permModalAgent && (() => {
                const modalAgent = agents.find(a => a.id === permModalAgent);
                const isAgentOwner = modalAgent?.owner_email === userEmail || !modalAgent?.owner_email;
                return (
                    <AgentPermissionsModal
                        isOpen={true}
                        onClose={() => setPermModalAgent(null)}
                        onBack={() => { setPermModalAgent(null); setAgentsModalOpen(true); }}
                        agentId={agentPermissions.agent_id}
                        agentName={agentPermissions.agent_name}
                        agentDescription={modalAgent?.description}
                        scopes={agentPermissions.scopes}
                        toolScopeMap={agentPermissions.tool_scope_map}
                        permissions={agentPermissions.permissions}
                        toolDescriptions={agentPermissions.tool_descriptions}
                        securityFlags={agentPermissions.security_flags}
                        toolOverrides={agentPermissions.tool_overrides}
                        onSave={(agentId, scopes, toolOverrides) => {
                            onSetAgentPermissions?.(agentId, scopes, toolOverrides);
                        }}
                        requiredCredentials={modalAgent?.metadata?.required_credentials}
                        storedCredentialKeys={agentCredentialKeys[permModalAgent] || []}
                        onSaveCredentials={onSaveAgentCredentials}
                        onDeleteCredential={onDeleteAgentCredential}
                        onStartOAuth={onStartOAuthFlow}
                        isOwner={isAgentOwner}
                        isPublic={modalAgent?.is_public}
                        onSetVisibility={onSetAgentVisibility}
                    />
                );
            })()}
        </div>
    );
}

function StatusItem({
    icon,
    label,
    value,
    color,
    pulse,
}: {
    icon: React.ReactNode;
    label: string;
    value: string;
    color: string;
    pulse?: boolean;
}) {
    return (
        <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg">
            <span className={`${color} ${pulse ? "animate-pulse" : ""}`}>{icon}</span>
            <div className="flex-1">
                <p className="text-[11px] text-astral-muted">{label}</p>
            </div>
            <span className={`text-[11px] font-medium ${color}`}>{value}</span>
        </div>
    );
}
