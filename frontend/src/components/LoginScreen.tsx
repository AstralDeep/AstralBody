/**
 * LoginScreen — Simple login gate.
 * No OIDC, just a basic admin check for now.
 */
import React, { useState } from "react";
import { useSmartAuth as useAuth } from "../hooks/useSmartAuth";
import { motion } from "framer-motion";
import { Zap, ArrowRight, AlertCircle } from "lucide-react";

export default function LoginScreen() {
    const auth = useAuth();
    const [loading, setLoading] = useState(false);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        auth.signinRedirect().catch(e => {
            console.error("Login failed:", e);
            setLoading(false);
        });
    };

    return (
        <div className="min-h-screen bg-astral-bg flex items-center justify-center relative overflow-hidden">
            {/* Background Effects */}
            <div className="absolute inset-0">
                <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-astral-primary/5 rounded-full blur-3xl" />
                <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-astral-accent/5 rounded-full blur-3xl" />
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,#0F1221_70%)]" />
            </div>

            <motion.div
                initial={{ opacity: 0, y: 20, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.5 }}
                className="relative z-10 w-full max-w-sm"
            >
                {/* Brand */}
                <div className="text-center mb-8">
                    <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ type: "spring", stiffness: 200, delay: 0.2 }}
                        className="w-16 h-16 rounded-2xl bg-gradient-to-br from-astral-primary to-astral-accent
                       flex items-center justify-center mx-auto mb-4 shadow-lg shadow-astral-primary/20"
                    >
                        <Zap size={28} className="text-white" />
                    </motion.div>
                    <h1 className="text-2xl font-bold text-white tracking-tight">AstralDeep</h1>
                    <p className="text-sm text-astral-muted mt-1">Multi-Agent Orchestration Platform</p>
                </div>

                {/* Login Card */}
                <div className="glass-card p-6 space-y-5">
                    <div className="text-center">
                        <h2 className="text-base font-semibold text-white">Sign in to access the dashboard</h2>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-4">
                        {auth.error && (
                            <motion.div
                                initial={{ opacity: 0, y: -5 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="flex items-center gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3"
                            >
                                <AlertCircle size={14} />
                                <span>{auth.error.message}</span>
                            </motion.div>
                        )}

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full py-2.5 bg-gradient-to-r from-astral-primary to-astral-secondary
                         rounded-lg text-sm font-medium text-white
                         hover:opacity-90 disabled:opacity-50 transition-opacity
                         flex items-center justify-center gap-2"
                            id="login-submit"
                        >
                            {loading ? (
                                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            ) : (
                                <>
                                    Sign In with SSO
                                    <ArrowRight size={14} />
                                </>
                            )}
                        </button>
                    </form>
                </div>

                <p className="text-center text-[10px] text-astral-muted/50 mt-6">
                    v1.0.0 — Orchestrator + Agent2Agent + MCP
                </p>
            </motion.div>
        </div>
    );
}
