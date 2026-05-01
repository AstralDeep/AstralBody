/**
 * TextOnlyBanner — Persistent banner shown at the top of the chat surface
 * whenever the current user has no usable tools, signalling that chat
 * messages will be answered by the LLM in text-only mode.
 *
 * Feature 008-llm-text-only-chat:
 * - FR-007a: persistent banner while text-only mode is active, with an
 *   inline link/button to the agent management surface; disappears on
 *   the next render that has tools available.
 * - Driven by `toolsAvailableForUser`, which is broadcast by the
 *   orchestrator on the `agent_list` WebSocket message and updated
 *   whenever agents register/disconnect or permissions change
 *   (see contracts/ws-agent-list.md).
 */
import { motion, AnimatePresence } from "framer-motion";
import { Bot, ChevronRight } from "lucide-react";

export interface TextOnlyBannerProps {
    /** True if the user currently has at least one tool available. When
     * false, the banner is rendered. */
    toolsAvailableForUser: boolean;
    /** Opens the existing agent management surface (the agents modal in
     * DashboardLayout). */
    onOpenAgentSettings: () => void;
}

export default function TextOnlyBanner({
    toolsAvailableForUser,
    onOpenAgentSettings,
}: TextOnlyBannerProps) {
    return (
        <AnimatePresence>
            {!toolsAvailableForUser && (
                <motion.div
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.2 }}
                    role="status"
                    aria-live="polite"
                    data-testid="text-only-banner"
                    className="mx-1 sm:mx-0 mb-3 sm:mb-4 flex items-center justify-between gap-3 px-3 sm:px-4 py-2.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-100"
                >
                    <div className="flex items-start gap-3 min-w-0">
                        <div className="w-8 h-8 rounded-lg bg-amber-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                            <Bot size={16} className="text-amber-300" />
                        </div>
                        <div className="min-w-0">
                            <p className="text-sm font-medium leading-snug">
                                Text-only mode — no agents are enabled
                            </p>
                            <p className="text-xs text-amber-200/80 leading-snug mt-0.5">
                                You can chat with the language model, but it can&apos;t take actions on your behalf until you turn on an agent.
                            </p>
                        </div>
                    </div>
                    <button
                        type="button"
                        onClick={onOpenAgentSettings}
                        data-testid="text-only-banner-cta"
                        className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-amber-400/20 hover:bg-amber-400/30 text-amber-100 transition-colors flex-shrink-0"
                    >
                        Enable agents
                        <ChevronRight size={14} />
                    </button>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
