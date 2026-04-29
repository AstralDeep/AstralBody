/**
 * LlmSettingsPanel — full-screen overlay for managing the user's
 * personal LLM configuration (feature 006-user-llm-config).
 *
 * Mirrors the AuditLogPanel pattern from feature 003: the project
 * has no router, so this panel is the equivalent of a dedicated route.
 * Its open state is reflected in the URL query string (`?llm=open`)
 * so refreshing or sharing the URL restores the same view.
 *
 * Header text adapts to the user's config state:
 *   - "Connected — using your own provider" when a personal config is set
 *   - "Using operator default" when no personal config is set
 *
 * Constitution VIII compliance: existing styling primitives only.
 */
import { useEffect } from "react";
import { KeyRound, X, ShieldCheck } from "lucide-react";

import LlmConfigForm from "./LlmConfigForm";
import TokenUsageDialog from "./TokenUsageDialog";
import { useLlmConfig } from "../../hooks/useLlmConfig";

export interface LlmSettingsPanelProps {
    open: boolean;
    accessToken: string | undefined;
    onClose: () => void;
}

function writeOpenStateToUrl(open: boolean): void {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (open) {
        if (params.get("llm") !== "open") {
            params.set("llm", "open");
            window.history.pushState({}, "", `?${params.toString()}`);
        }
    } else {
        if (params.get("llm") === "open") {
            params.delete("llm");
            const qs = params.toString();
            window.history.pushState({}, "", qs ? `?${qs}` : window.location.pathname);
        }
    }
}

export default function LlmSettingsPanel({
    open,
    accessToken,
    onClose,
}: LlmSettingsPanelProps) {
    const { config } = useLlmConfig();

    // Sync open state to URL.
    useEffect(() => {
        if (typeof window === "undefined") return;
        writeOpenStateToUrl(open);
    }, [open]);

    // Close on Escape.
    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [open, onClose]);

    if (!open) return null;

    const hasPersonalConfig = !!config;
    const headerSubtitle = hasPersonalConfig
        ? `Connected — using your own provider${config?.connectedAt ? ` since ${new Date(config.connectedAt).toLocaleString()}` : ""}.`
        : "Currently using the operator default. Save a personal configuration to use your own provider.";

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={onClose}
        >
            <div
                className="bg-astral-surface border border-white/10 rounded-xl shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col"
                onClick={(e) => e.stopPropagation()}
                role="dialog"
                aria-modal="true"
                aria-label="LLM settings"
            >
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-astral-primary/20 flex items-center justify-center">
                            <KeyRound size={16} className="text-astral-primary" />
                        </div>
                        <div>
                            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                                LLM settings
                                <span className="text-[10px] px-1.5 py-0.5 rounded border border-white/10 text-astral-muted flex items-center gap-1">
                                    <ShieldCheck size={10} /> per-device
                                </span>
                            </h2>
                            <p className="text-[11px] text-astral-muted">{headerSubtitle}</p>
                        </div>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        className="p-1.5 rounded-lg hover:bg-white/10"
                        aria-label="Close LLM settings"
                    >
                        <X size={14} className="text-astral-muted" />
                    </button>
                </div>

                {/* Body */}
                <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
                    <LlmConfigForm accessToken={accessToken} />
                    <TokenUsageDialog hasPersonalConfig={hasPersonalConfig} />
                </div>
            </div>
        </div>
    );
}
