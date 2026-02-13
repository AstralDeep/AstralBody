/**
 * LoginScreen — Simple admin login gate.
 * No OIDC, just a basic admin check for now.
 */
import React, { useState } from "react";
import { motion } from "framer-motion";
import { Zap, Lock, User, ArrowRight, AlertCircle } from "lucide-react";

interface LoginScreenProps {
    onLogin: () => void;
}

const ADMIN_USER = "admin";
const ADMIN_PASS = "admin";

export default function LoginScreen({ onLogin }: LoginScreenProps) {
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);

        setTimeout(() => {
            if (username === ADMIN_USER && password === ADMIN_PASS) {
                localStorage.setItem("isAuthenticated", "true");
                onLogin();
            } else {
                setError("Invalid credentials. Use admin/admin.");
                setLoading(false);
            }
        }, 600); // Simulate auth delay
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
                        <h2 className="text-base font-semibold text-white">Admin Login</h2>
                        <p className="text-xs text-astral-muted mt-1">Sign in to access the dashboard</p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label className="text-xs text-astral-muted block mb-1.5">Username</label>
                            <div className="relative">
                                <User size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-astral-muted" />
                                <input
                                    type="text"
                                    value={username}
                                    onChange={(e) => setUsername(e.target.value)}
                                    placeholder="admin"
                                    className="w-full pl-9 pr-4 py-2.5 bg-astral-bg/60 border border-white/10
                             rounded-lg text-sm text-white placeholder:text-astral-muted/40
                             focus:outline-none focus:border-astral-primary/50 transition-colors"
                                    id="login-username"
                                    autoComplete="username"
                                />
                            </div>
                        </div>

                        <div>
                            <label className="text-xs text-astral-muted block mb-1.5">Password</label>
                            <div className="relative">
                                <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-astral-muted" />
                                <input
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="••••••"
                                    className="w-full pl-9 pr-4 py-2.5 bg-astral-bg/60 border border-white/10
                             rounded-lg text-sm text-white placeholder:text-astral-muted/40
                             focus:outline-none focus:border-astral-primary/50 transition-colors"
                                    id="login-password"
                                    autoComplete="current-password"
                                />
                            </div>
                        </div>

                        {error && (
                            <motion.div
                                initial={{ opacity: 0, y: -5 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="flex items-center gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3"
                            >
                                <AlertCircle size={14} />
                                <span>{error}</span>
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
                                    Sign In
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
