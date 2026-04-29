/**
 * LlmConfigForm — the "API key / base URL / model" entry form
 * (feature 006-user-llm-config).
 *
 * Behaviour:
 *
 *   - All three inputs required and non-empty before "Test Connection"
 *     is enabled.
 *   - "Test Connection" issues a real chat-completions probe via
 *     `POST /api/llm/test`. The result (latency, error message)
 *     displays inline.
 *   - "Save" is enabled only after a successful probe since the most
 *     recent edit. Any field edit re-disables Save until the next
 *     probe — so users can't save credentials they haven't validated.
 *   - On Save, the config is committed to localStorage and a
 *     `llm-config-changed` window event fires (useWebSocket dispatches
 *     the corresponding `llm_config_set` message).
 *
 * Constitution VIII compliance: uses only existing styling primitives
 * (no third-party UI library). No new primitive proposed.
 */
import { useCallback, useEffect, useState } from "react";
import { Eye, EyeOff, Loader2, CheckCircle2, AlertCircle, Save, Beaker } from "lucide-react";

import type { TestConnectionResponse } from "../../api/llm";
import { useLlmConfig, type LlmConfig } from "../../hooks/useLlmConfig";

export interface LlmConfigFormProps {
    accessToken: string | undefined;
    onSaved?: (config: LlmConfig) => void;
    onCleared?: () => void;
}

export default function LlmConfigForm({ accessToken, onSaved, onCleared }: LlmConfigFormProps) {
    const { config, save, clear, testConnection } = useLlmConfig();

    const [apiKey, setApiKey] = useState<string>(config?.apiKey ?? "");
    const [baseUrl, setBaseUrl] = useState<string>(config?.baseUrl ?? "https://api.openai.com/v1");
    const [model, setModel] = useState<string>(config?.model ?? "gpt-4o-mini");
    const [revealKey, setRevealKey] = useState<boolean>(false);

    const [probeState, setProbeState] = useState<"idle" | "probing" | "passed" | "failed">("idle");
    const [probeResult, setProbeResult] = useState<TestConnectionResponse | null>(null);
    const [probeError, setProbeError] = useState<string | null>(null);

    // Sync from external config changes (other tab, clear).
    useEffect(() => {
        if (config) {
            setApiKey(config.apiKey);
            setBaseUrl(config.baseUrl);
            setModel(config.model);
        } else {
            setApiKey("");
            // Keep existing baseUrl/model defaults so the form is usable.
        }
    }, [config?.apiKey, config?.baseUrl, config?.model, !!config]);

    const allFilled = apiKey.trim() !== "" && baseUrl.trim() !== "" && model.trim() !== "";
    const probePassed = probeState === "passed";

    // Any edit invalidates a prior probe so the user must re-validate.
    const onEdit = useCallback(() => {
        if (probeState !== "idle") {
            setProbeState("idle");
            setProbeResult(null);
            setProbeError(null);
        }
    }, [probeState]);

    const handleTest = useCallback(async () => {
        if (!allFilled) return;
        setProbeState("probing");
        setProbeError(null);
        setProbeResult(null);
        try {
            const result = await testConnection(
                { apiKey: apiKey.trim(), baseUrl: baseUrl.trim(), model: model.trim() },
                accessToken,
            );
            setProbeResult(result);
            setProbeState(result.ok ? "passed" : "failed");
        } catch (err) {
            setProbeError(err instanceof Error ? err.message : String(err));
            setProbeState("failed");
        }
    }, [allFilled, apiKey, baseUrl, model, accessToken, testConnection]);

    const handleSave = useCallback(() => {
        if (!probePassed) return;
        save({
            apiKey: apiKey.trim(),
            baseUrl: baseUrl.trim(),
            model: model.trim(),
            markConnected: true,
        });
        const next: LlmConfig = {
            apiKey: apiKey.trim(),
            baseUrl: baseUrl.trim(),
            model: model.trim(),
            connectedAt: new Date().toISOString(),
            schemaVersion: 1,
        };
        onSaved?.(next);
    }, [probePassed, apiKey, baseUrl, model, save, onSaved]);

    const handleClear = useCallback(() => {
        // Caller is responsible for showing the confirmation; this
        // component just performs the clear.
        clear();
        setApiKey("");
        setProbeState("idle");
        setProbeResult(null);
        setProbeError(null);
        onCleared?.();
    }, [clear, onCleared]);

    return (
        <div className="space-y-4">
            {/* Privacy notice */}
            <div className="text-[11px] text-astral-muted bg-white/5 border border-white/10 rounded-lg px-3 py-2">
                Your API key lives only on this device's browser storage. It's
                sent to the orchestrator with each LLM request and used in
                memory; it's never written to a database, log, or audit field.
                Sign out won't clear it — use "Clear configuration" to remove
                it from this device.
            </div>

            {/* API key */}
            <label className="block">
                <span className="text-[11px] font-medium text-astral-muted block mb-1">
                    API key
                </span>
                <div className="relative">
                    <input
                        type={revealKey ? "text" : "password"}
                        autoComplete="off"
                        spellCheck={false}
                        value={apiKey}
                        onChange={(e) => { setApiKey(e.target.value); onEdit(); }}
                        placeholder="sk-…"
                        className="w-full px-3 py-2 pr-10 text-sm bg-astral-bg border border-white/10 rounded-lg focus:outline-none focus:border-astral-primary/50 text-white placeholder:text-astral-muted/50"
                    />
                    <button
                        type="button"
                        onClick={() => setRevealKey((v) => !v)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-astral-muted hover:text-white"
                        aria-label={revealKey ? "Hide API key" : "Reveal API key"}
                    >
                        {revealKey ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                </div>
            </label>

            {/* Base URL */}
            <label className="block">
                <span className="text-[11px] font-medium text-astral-muted block mb-1">
                    Base URL <span className="text-astral-muted/70 font-normal">(OpenAI-compatible chat-completions endpoint)</span>
                </span>
                <input
                    type="url"
                    value={baseUrl}
                    onChange={(e) => { setBaseUrl(e.target.value); onEdit(); }}
                    placeholder="https://api.openai.com/v1"
                    className="w-full px-3 py-2 text-sm bg-astral-bg border border-white/10 rounded-lg focus:outline-none focus:border-astral-primary/50 text-white placeholder:text-astral-muted/50"
                />
            </label>

            {/* Model */}
            <label className="block">
                <span className="text-[11px] font-medium text-astral-muted block mb-1">
                    Model
                </span>
                <input
                    type="text"
                    value={model}
                    onChange={(e) => { setModel(e.target.value); onEdit(); }}
                    placeholder="gpt-4o-mini"
                    className="w-full px-3 py-2 text-sm bg-astral-bg border border-white/10 rounded-lg focus:outline-none focus:border-astral-primary/50 text-white placeholder:text-astral-muted/50"
                />
            </label>

            {/* Probe result */}
            {probeState === "passed" && probeResult && (
                <div className="px-3 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300 flex items-center gap-2">
                    <CheckCircle2 size={14} />
                    <span>
                        Connected. Responded in {probeResult.latency_ms ?? "?"} ms.
                    </span>
                </div>
            )}
            {probeState === "failed" && (
                <div className="px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-300 flex items-start gap-2">
                    <AlertCircle size={14} className="flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                        <div className="font-medium">
                            {probeResult?.error_class ?? "test_failed"}
                        </div>
                        <div className="opacity-80 mt-0.5">
                            {probeResult?.upstream_message ?? probeError ?? "Probe failed"}
                        </div>
                    </div>
                </div>
            )}

            {/* Buttons */}
            <div className="flex items-center gap-2">
                <button
                    type="button"
                    onClick={handleTest}
                    disabled={!allFilled || probeState === "probing" || !accessToken}
                    className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-white/10 hover:bg-white/5 disabled:opacity-50 disabled:cursor-not-allowed text-white"
                >
                    {probeState === "probing"
                        ? <Loader2 size={14} className="animate-spin" />
                        : <Beaker size={14} />
                    }
                    Test connection
                </button>
                <button
                    type="button"
                    onClick={handleSave}
                    disabled={!probePassed}
                    className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-astral-primary/20 border border-astral-primary/40 hover:bg-astral-primary/30 disabled:opacity-40 disabled:cursor-not-allowed text-white"
                >
                    <Save size={14} />
                    Save
                </button>
                {config && (
                    <button
                        type="button"
                        onClick={handleClear}
                        className="ml-auto px-3 py-2 text-xs font-medium rounded-lg border border-red-500/30 hover:bg-red-500/10 text-red-300"
                    >
                        Clear configuration
                    </button>
                )}
            </div>
        </div>
    );
}
