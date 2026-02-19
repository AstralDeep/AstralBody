/**
 * DashboardLayout — Main app shell with sidebar and header.
 * Shows connected agents, their tools, and connection status.
 */
import React, { useState } from "react";
import { motion } from "framer-motion";
import {
    LayoutDashboard,
    Bot,
    Wrench,
    Wifi,
    WifiOff,
    ChevronDown,
    ChevronRight,
    LogOut,
    Activity,
    MessageSquare,
    Plus,
    Grid,
} from "lucide-react";
import type { Agent, ChatSession } from "../hooks/useWebSocket";

interface DashboardLayoutProps {
    children: React.ReactNode;
    agents: Agent[];
    isConnected: boolean;
    onLogout: () => void;
    chatHistory?: ChatSession[];
    activeChatId?: string | null;
    onLoadChat?: (chatId: string) => void;
    onNewChat?: () => void;
}

export default function DashboardLayout({
    children,
    agents,
    isConnected,
    onLogout,
    chatHistory = [],
    activeChatId,
    onLoadChat,
    onNewChat,
}: DashboardLayoutProps) {
    const [expandedAgents, setExpandedAgents] = useState<string[]>([]);

    const toggleAgent = (id: string) => {
        setExpandedAgents((prev) =>
            prev.includes(id) ? prev.filter((a) => a !== id) : [...prev, id]
        );
    };

    const totalTools = agents.reduce((sum, a) => sum + a.tools.length, 0);

    return (
        <div className="h-screen flex overflow-hidden bg-astral-bg">
            {/* Sidebar */}
            <aside className="w-64 flex flex-col border-r border-white/5 bg-astral-surface/30 backdrop-blur-xl">
                {/* Logo / Brand */}
                <div className="h-16 flex items-center px-5 border-b border-white/5">
                    <div className="flex items-center gap-3">
                        <div className="flex items-center">
                            <img
                                src="/AstralDeep.png"
                                alt="AstralDeep Logo"
                                className="h-8 w-auto object-contain"
                            />
                        </div>
                    </div>
                </div>

                {/* Navigation */}
                <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-6">

                    {/* Status Section */}
                    <div>
                        <p className="px-2 text-[10px] font-semibold uppercase tracking-widest text-astral-muted mb-2">
                            Status
                        </p>
                        <div className="space-y-1">
                            <StatusItem
                                icon={isConnected ? <Wifi size={14} /> : <WifiOff size={14} />}
                                label="Orchestrator"
                                value={isConnected ? "Connected" : "Disconnected"}
                                color={isConnected ? "text-green-400" : "text-red-400"}
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
                        <p className="px-2 text-[10px] font-semibold uppercase tracking-widest text-astral-muted mb-2">
                            Connected Agents
                        </p>
                        <div className="space-y-1">
                            {agents.length === 0 && (
                                <p className="px-2 text-xs text-astral-muted/50 italic">
                                    Waiting for agents...
                                </p>
                            )}
                            {agents.map((agent) => (
                                <div key={agent.id}>
                                    <button
                                        onClick={() => toggleAgent(agent.id)}
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
                                            <p className="text-[10px] text-astral-muted">
                                                {agent.tools.length} tools
                                            </p>
                                        </div>
                                        {expandedAgents.includes(agent.id) ? (
                                            <ChevronDown size={12} className="text-astral-muted" />
                                        ) : (
                                            <ChevronRight size={12} className="text-astral-muted" />
                                        )}
                                    </button>

                                    {expandedAgents.includes(agent.id) && (
                                        <motion.div
                                            initial={{ opacity: 0, height: 0 }}
                                            animate={{ opacity: 1, height: "auto" }}
                                            className="ml-8 mt-1 space-y-0.5"
                                        >
                                            {agent.tools.map((tool) => (
                                                <div
                                                    key={tool}
                                                    className="flex items-center gap-2 px-2 py-1.5 text-[11px] text-astral-muted rounded hover:bg-white/5"
                                                >
                                                    <span className="w-1 h-1 rounded-full bg-astral-accent" />
                                                    <span className="truncate">{tool}</span>
                                                </div>
                                            ))}
                                        </motion.div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>



                    {/* Recent Chats */}
                    <div>
                        <p className="px-2 text-[10px] font-semibold uppercase tracking-widest text-astral-muted mb-2">
                            Recent Chats
                        </p>
                        <div className="space-y-1">
                            {chatHistory.length === 0 && (
                                <p className="px-2 text-xs text-astral-muted/50 italic">
                                    No history yet...
                                </p>
                            )}
                            {chatHistory.map((chat) => (
                                <button
                                    key={chat.id}
                                    onClick={() => onLoadChat?.(chat.id)}
                                    className={`w-full flex items-center gap-2 px-2 py-2 rounded-lg transition-colors text-left
                                    ${activeChatId === chat.id ? "bg-white/10 text-white" : "hover:bg-white/5 text-astral-muted hover:text-white"}`}
                                >
                                    <MessageSquare size={14} className="flex-shrink-0" />
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-1">
                                            <p className="text-xs font-medium truncate">
                                                {chat.title || "Untitled Chat"}
                                            </p>
                                            {chat.has_saved_components && (
                                                <div className="relative group">
                                                    <Grid size={10} className="text-astral-primary flex-shrink-0" />
                                                    <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-1 px-2 py-1 text-xs bg-astral-surface border border-white/10 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">
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
                <header className="h-14 flex items-center justify-between px-6 border-b border-white/5 bg-astral-bg/80 backdrop-blur-md flex-shrink-0">
                    <div className="flex items-center gap-3">
                        <LayoutDashboard size={16} className="text-astral-muted" />
                        <span className="text-sm font-medium text-white">Dashboard</span>
                    </div>
                    <div className="flex items-center gap-3">
                        <button
                            onClick={onNewChat}
                            className="flex items-center gap-2 px-3 py-1.5 bg-astral-primary/10 
                                     border border-astral-primary/20 rounded-md text-xs font-medium 
                                     text-astral-primary hover:bg-astral-primary/20 transition-colors"
                        >
                            <Plus size={14} />
                            <span>New Chat</span>
                        </button>
                    </div>
                </header>

                {/* Page Content */}
                <div className="flex-1 overflow-hidden">{children}</div>
            </main>
        </div>
    );
}

function StatusItem({
    icon,
    label,
    value,
    color,
}: {
    icon: React.ReactNode;
    label: string;
    value: string;
    color: string;
}) {
    return (
        <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg">
            <span className={`${color}`}>{icon}</span>
            <div className="flex-1">
                <p className="text-[11px] text-astral-muted">{label}</p>
            </div>
            <span className={`text-[11px] font-medium ${color}`}>{value}</span>
        </div>
    );
}
