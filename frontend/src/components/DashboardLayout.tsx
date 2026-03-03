/**
 * DashboardLayout — Main app shell with sidebar and header.
 * Shows connected agents, their tools, and connection status.
 */
import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
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
} from "lucide-react";
import type { Agent, ChatSession, AgentPermissionsData, ConnectionState } from "../hooks/useWebSocket";
import AgentPermissionsModal from "./AgentPermissionsModal";

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
    agentPermissions?: AgentPermissionsData | null;
    onGetAgentPermissions?: (agentId: string) => void;
    onSetAgentPermissions?: (agentId: string, permissions: Record<string, boolean>) => void;
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
    // isAdmin and accessToken are passed but not used in this component
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    isAdmin: _isAdmin,
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    accessToken: _accessToken,
    agentPermissions,
    onGetAgentPermissions,
    onSetAgentPermissions,
}: DashboardLayoutProps) {
    const [chatToDelete, setChatToDelete] = useState<string | null>(null);
    const [permModalAgent, setPermModalAgent] = useState<string | null>(null);
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [chatSearch, setChatSearch] = useState("");

    // Close delete modal on Escape
    useEffect(() => {
        if (!chatToDelete) return;
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") setChatToDelete(null);
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => document.removeEventListener("keydown", handleKeyDown);
    }, [chatToDelete]);

    const openPermissionsModal = (agentId: string) => {
        setPermModalAgent(agentId);
        onGetAgentPermissions?.(agentId);
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

            {/* Mobile sidebar backdrop */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            {/* Sidebar */}
            <aside className={`
                fixed inset-y-0 left-0 z-50 w-64 flex flex-col border-r border-white/5 bg-astral-surface/30 backdrop-blur-xl
                transform transition-transform duration-200 ease-in-out
                ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}
                md:static md:translate-x-0
            `}>
                {/* Logo / Brand */}
                <div className="h-14 md:h-16 flex items-center justify-between px-5 border-b border-white/5 safe-top">
                    <div className="flex items-center gap-3">
                        <div className="flex items-center">
                            <img
                                src="/AstralDeep.png"
                                alt="AstralDeep Logo"
                                className="h-8 w-auto object-contain"
                            />
                        </div>
                    </div>
                    <button
                        onClick={() => setSidebarOpen(false)}
                        className="p-1.5 rounded-lg hover:bg-white/10 transition-colors md:hidden"
                    >
                        <X size={18} className="text-astral-muted" />
                    </button>
                </div>

                {/* Navigation */}
                <nav className="flex-1 overflow-y-auto overflow-x-hidden py-4 px-3 space-y-6">

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

                    {/* Agents Section */}
                    <div>
                        <div className="px-2 mb-2">
                            <p className="text-[10px] font-semibold uppercase tracking-widest text-astral-muted">
                                Agents
                            </p>
                        </div>
                        <div className="space-y-4">
                            {/* Connected Section */}
                            <div className="space-y-1">
                                <p className="px-2 text-[10px] text-astral-muted/70 uppercase">Connected</p>
                                {agents.length === 0 && (
                                    <p className="px-2 text-xs text-astral-muted/50 italic">
                                        Waiting for agents...
                                    </p>
                                )}
                                {agents.map((agent) => (
                                    <button
                                        key={agent.id}
                                        onClick={() => openPermissionsModal(agent.id)}
                                        className="w-full flex items-center gap-2 px-2 py-2 rounded-lg
                                   hover:bg-white/5 transition-colors group text-left"
                                    >
                                        <div className="w-6 h-6 rounded-md bg-astral-primary/20 flex items-center justify-center flex-shrink-0">
                                            <Activity size={12} className="text-astral-primary" />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-xs font-medium text-white truncate">
                                                {agent.name}
                                            </p>
                                            <p className="text-[10px] text-astral-muted truncate">
                                                {(() => {
                                                    const blocked = new Set(Object.entries(agent.security_flags || {}).filter(([, f]) => (f as { blocked?: boolean }).blocked).map(([n]) => n));
                                                    const active = agent.permissions
                                                        ? Object.entries(agent.permissions).filter(([n, v]) => v && !blocked.has(n)).length
                                                        : agent.tools.filter(t => !blocked.has(t)).length;
                                                    return `${active} active tools`;
                                                })()}
                                            </p>
                                        </div>
                                        {/* Permission indicator dot */}
                                        {(() => {
                                            const hasSecurityFlags = agent.security_flags &&
                                                Object.values(agent.security_flags).some((f: unknown) => (f as { blocked?: boolean }).blocked);
                                            if (hasSecurityFlags) {
                                                const flagCount = Object.values(agent.security_flags!).filter((f: unknown) => (f as { blocked?: boolean }).blocked).length;
                                                return <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 bg-red-500 animate-pulse" title={`Security review flagged ${flagCount} tool${flagCount > 1 ? "s" : ""}`} />;
                                            }
                                            if (!agent.permissions) {
                                                return <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 bg-green-400" title="All tools enabled" />;
                                            }
                                            const perms = Object.values(agent.permissions);
                                            const allEnabled = perms.every(Boolean);
                                            const allDisabled = perms.every(v => !v);
                                            return (
                                                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${allEnabled ? "bg-green-400" :
                                                    allDisabled ? "bg-red-400" : "bg-amber-400"
                                                    }`} title={allEnabled ? "All tools enabled" : allDisabled ? "All tools disabled" : "Some tools restricted"} />
                                            );
                                        })()}
                                        <Shield size={12} className="text-astral-muted/50 group-hover:text-astral-primary transition-colors flex-shrink-0" />
                                    </button>
                                ))}
                            </div>
                        </div>
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
                                        placeholder="Search chats..."
                                        value={chatSearch}
                                        onChange={(e) => setChatSearch(e.target.value)}
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
                                        onClick={() => { onLoadChat?.(chat.id); setSidebarOpen(false); }}
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

                {/* Footer */}
                <div className="border-t border-white/5 p-3">
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
                            onClick={() => setSidebarOpen(true)}
                            className="p-2 rounded-lg hover:bg-white/10 transition-colors md:hidden"
                        >
                            <Menu size={20} className="text-astral-muted" />
                        </button>
                        <LayoutDashboard size={16} className="text-astral-muted hidden sm:block" />
                        <span className="text-sm font-medium text-white hidden sm:block">Dashboard</span>
                    </div>
                    {/* Centered logo — visible only when sidebar is collapsed */}
                    <div className="absolute left-1/2 -translate-x-1/2 md:hidden">
                        <img
                            src="/AstralDeep.png"
                            alt="AstralDeep Logo"
                            className="h-7 w-auto object-contain"
                        />
                    </div>
                    <div className="flex items-center gap-2 sm:gap-3">
                        <button
                            onClick={() => { onNewChat?.(); setSidebarOpen(false); }}
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

            {/* Agent Permissions Modal */}
            {permModalAgent && agentPermissions && agentPermissions.agent_id === permModalAgent && (
                <AgentPermissionsModal
                    isOpen={true}
                    onClose={() => setPermModalAgent(null)}
                    agentId={agentPermissions.agent_id}
                    agentName={agentPermissions.agent_name}
                    agentDescription={agents.find(a => a.id === permModalAgent)?.description}
                    permissions={agentPermissions.permissions}
                    toolDescriptions={agentPermissions.tool_descriptions}
                    securityFlags={agentPermissions.security_flags}
                    onSave={(agentId, perms) => {
                        onSetAgentPermissions?.(agentId, perms);
                    }}
                />
            )}
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
