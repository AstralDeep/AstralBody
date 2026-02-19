/**
 * ChatInterface — Real-time chat with the orchestrator.
 *
 * Features:
 * - Message input with send button
 * - Chat history display (user + assistant messages)
 * - Loading states (thinking, executing)
 * - Dynamic UI rendering for assistant responses via DynamicRenderer
 */
import React, { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Bot, User, Sparkles, Loader2, Grid, ChevronLeft } from "lucide-react";
import DynamicRenderer from "./DynamicRenderer";
import UISavedDrawer from "./UISavedDrawer";
import type { ChatStatus } from "../hooks/useWebSocket";

interface ChatInterfaceProps {
    messages: { role: string; content: any }[];
    chatStatus: ChatStatus;
    onSendMessage: (message: string) => void;
    isConnected: boolean;
    activeChatId: string | null;
    savedComponents: any[];
    onSaveComponent: (componentData: any, componentType: string) => Promise<boolean>;
    onDeleteSavedComponent: (componentId: string) => void;
}

const SUGGESTIONS = [
    "Get me all patients over 30 and graph their ages",
    "What is my system's CPU and memory usage?",
    "Search Wikipedia for artificial intelligence",
    "Show me disk usage information",
];

export default function ChatInterface({
    messages,
    chatStatus,
    onSendMessage,
    isConnected,
    activeChatId,
    savedComponents,
    onSaveComponent,
    onDeleteSavedComponent,
}: ChatInterfaceProps) {
    const [input, setInput] = useState("");
    const [isDrawerOpen, setIsDrawerOpen] = useState(false);
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, chatStatus]);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || !isConnected) return;
        onSendMessage(input.trim());
        setInput("");
    };

    const handleSuggestion = (text: string) => {
        if (!isConnected) return;
        onSendMessage(text);
    };

    return (
        <div className="flex flex-col h-full">
            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
                {messages.length === 0 && (
                    <div className="flex flex-col items-center justify-center h-full text-center">
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="space-y-6"
                        >
                            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-astral-primary to-astral-secondary flex items-center justify-center mx-auto">
                                <Sparkles className="text-white" size={28} />
                            </div>
                            <div>
                                <h2 className="text-xl font-semibold text-white mb-2">
                                    AstralDeep
                                </h2>
                                <p className="text-sm text-astral-muted">
                                    Ask anything!
                                    <br />
                                    Results are dynamically rendered as rich UI components.
                                </p>
                            </div>
                            <div className="grid grid-cols-2 gap-3 max-w-lg">
                                {SUGGESTIONS.map((s, i) => (
                                    <button
                                        key={i}
                                        onClick={() => handleSuggestion(s)}
                                        className="p-3 text-left text-xs text-astral-muted hover:text-white
                               bg-white/5 hover:bg-white/10 rounded-lg border border-white/5
                               hover:border-astral-primary/30 transition-all duration-200"
                                    >
                                        {s}
                                    </button>
                                ))}
                            </div>
                        </motion.div>
                    </div>
                )}

                {messages.map((msg, i) => (
                    <motion.div
                        key={i}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.2 }}
                        className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}
                    >
                        {msg.role === "assistant" && (
                            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-astral-primary to-astral-secondary flex items-center justify-center flex-shrink-0 mt-1">
                                <Bot size={16} className="text-white" />
                            </div>
                        )}
                        <div
                            className={`${msg.role === "user"
                                ? "max-w-md bg-astral-primary/20 border border-astral-primary/30 rounded-2xl rounded-tr-sm px-4 py-3"
                                : "flex-1 max-w-4xl"
                                }`}
                        >
                            {msg.role === "user" ? (
                                <p className="text-sm text-white">{msg.content}</p>
                            ) : (
                                <DynamicRenderer 
                                    components={msg.content} 
                                    onSaveComponent={onSaveComponent}
                                    activeChatId={activeChatId}
                                />
                            )}
                        </div>
                        {msg.role === "user" && (
                            <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center flex-shrink-0 mt-1">
                                <User size={16} className="text-astral-muted" />
                            </div>
                        )}
                    </motion.div>
                ))}

                {/* Loading state */}
                <AnimatePresence>
                    {chatStatus.status !== "idle" && chatStatus.status !== "done" && (
                        <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            className="flex gap-3"
                        >
                            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-astral-primary to-astral-secondary flex items-center justify-center flex-shrink-0 pulse-glow">
                                <Bot size={16} className="text-white" />
                            </div>
                            <div className="glass-card px-4 py-3 flex items-center gap-3">
                                <Loader2 size={16} className="text-astral-primary animate-spin" />
                                <span className="text-sm text-astral-muted">
                                    {chatStatus.message || "Processing..."}
                                </span>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>

                <div ref={bottomRef} />
            </div>

            {/* Input Area */}
            <div className="border-t border-white/5 p-4 bg-astral-bg/80 backdrop-blur-md">
                <form onSubmit={handleSubmit} className="flex gap-3 max-w-4xl mx-auto">
                    <div className="flex-1 relative">
                        <input
                            type="text"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            placeholder={isConnected ? "Ask anything..." : "Connecting to orchestrator..."}
                            disabled={!isConnected || (chatStatus.status !== "idle" && chatStatus.status !== "done")}
                            className="w-full px-4 py-3 bg-astral-surface/60 border border-white/10
                         rounded-xl text-sm text-white placeholder:text-astral-muted/50
                         focus:outline-none focus:border-astral-primary/50 focus:ring-1 focus:ring-astral-primary/20
                         disabled:opacity-50 transition-all"
                            id="chat-input"
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={!input.trim() || !isConnected || (chatStatus.status !== "idle" && chatStatus.status !== "done")}
                        className="px-4 py-3 rounded-xl bg-astral-primary hover:bg-astral-primary/80
                       disabled:opacity-30 disabled:cursor-not-allowed
                       transition-colors flex items-center gap-2"
                        id="chat-submit"
                    >
                        <Send size={16} className="text-white" />
                    </button>
                </form>
            </div>

            {/* Saved Components Drawer */}
            <UISavedDrawer
                isOpen={isDrawerOpen}
                onClose={() => setIsDrawerOpen(false)}
                onOpen={() => setIsDrawerOpen(true)}
                savedComponents={savedComponents}
                onDeleteComponent={onDeleteSavedComponent}
                activeChatId={activeChatId}
            />

            {/* Drawer Toggle Button */}
            {!isDrawerOpen && savedComponents.length > 0 && (
                <button
                    onClick={() => setIsDrawerOpen(true)}
                    className="fixed right-4 bottom-20 z-30 bg-astral-primary hover:bg-astral-primary/80 text-white p-3 rounded-full shadow-lg transition-all duration-200 hover:shadow-xl hover:scale-105 flex items-center gap-2"
                    aria-label="Open saved components drawer"
                >
                    <Grid size={20} />
                    <span className="text-xs font-medium">{savedComponents.length}</span>
                </button>
            )}
        </div>
    );
}
