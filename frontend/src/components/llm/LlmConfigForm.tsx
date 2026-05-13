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
 *   - Model auto-discovery: when Base URL + API key are both filled,
 *     `POST /api/llm/list-models` is fired (debounced 500ms) to populate
 *     a dropdown of available model ids. The dropdown always includes
 *     a "Custom…" escape hatch that switches the field back to free
 *     text. Listing failure (404, auth, empty list, non-OpenAI shape)
 *     falls back silently to free-text input with a subtle hint.
 *
 * Constitution VIII compliance: uses only existing styling primitives
 * (no third-party UI library). No new primitive proposed.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Eye, EyeOff, Loader2, CheckCircle2, AlertCircle, Save, Beaker, ChevronDown } from "lucide-react";

import type { TestConnectionResponse } from "../../api/llm";
import { useLlmConfig, type LlmConfig } from "../../hooks/useLlmConfig";

export interface LlmConfigFormProps {
    accessToken: string | undefined;
    onSaved?: (config: LlmConfig) => void;
    onCleared?: () => void;
}

const CUSTOM_MODEL_SENTINEL = "__custom__";

export default function LlmConfigForm({ accessToken, onSaved, onCleared }: LlmConfigFormProps) {
    const { config, save, clear, testConnection, listModels } = useLlmConfig();

    const [apiKey, setApiKey] = useState<string>(config?.apiKey ?? "");
    const [baseUrl, setBaseUrl] = useState<string>(config?.baseUrl ?? "https://api.openai.com/v1");
    const [model, setModel] = useState<string>(config?.model ?? "gpt-4o-mini");
    const [revealKey, setRevealKey] = useState<boolean>(false);

    const [probeState, setProbeState] = useState<"idle" | "probing" | "passed" | "failed">("idle");
    const [probeResult, setProbeResult] = useState<TestConnectionResponse | null>(null);
    const [probeError, setProbeError] = useState<string | null>(null);

    const [availableModels, setAvailableModels] = useState<string[] | null>(null);
    const [listingState, setListingState] = useState<"idle" | "loading" | "loaded" | "failed">("idle");
    const [useCustomModel, setUseCustomModel] = useState<boolean>(false);

    const customInputRef = useRef<HTMLInputElement | null>(null);
    const focusCustomOnNextRender = useRef<boolean>(false);

    // Focus the custom-model input the render after the user picks "Custom…".
    // A ref-driven effect is more reliable than setTimeout(0) — it runs after
    // React commits the DOM that includes the freshly-mounted input.
    useEffect(() => {
        if (useCustomModel && focusCustomOnNextRender.current) {
            customInputRef.current?.focus();
            focusCustomOnNextRender.current = false;
        }
    }, [useCustomModel]);

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

    // Debounced model-listing probe. Re-runs whenever (apiKey, baseUrl)
    // change; cancels any in-flight request via AbortController so rapid
    // edits don't pile up requests.
    useEffect(() => {
        const key = apiKey.trim();
        const url = baseUrl.trim();
        if (!key || !url || !accessToken) {
            setListingState("idle");
            setAvailableModels(null);
            return;
        }
        const controller = new AbortController();
        let cancelled = false;
        const timer = window.setTimeout(async () => {
            setListingState("loading");
            try {
                const result = await listModels(
                    { apiKey: key, baseUrl: url },
                    accessToken,
                    controller.signal,
                );
                if (cancelled) return;
                if (result.ok && result.models.length > 0) {
                    setAvailableModels(result.models);
                    setListingState("loaded");
                    // Always default to dropdown mode after a successful listing.
                    // If the current model isn't in the discovered list, snap to
                    // the first option so the dropdown shows a populated default
                    // instead of an empty selection.
                    setUseCustomModel(false);
                    if (!result.models.includes(model.trim())) {
                        setModel(result.models[0]);
                        // Inlined probe invalidation — changing the model
                        // must re-disable Save until the user re-tests.
                        // (Calling onEdit here would tie the effect to
                        // probeState via closure.)
                        setProbeState("idle");
                        setProbeResult(null);
                        setProbeError(null);
                    }
                } else {
                    setAvailableModels(null);
                    setListingState("failed");
                }
            } catch (err) {
                if (cancelled) return;
                // AbortError fires when the user edits again before the
                // request resolves — the next effect run resets state.
                if ((err as { name?: string })?.name === "AbortError") return;
                setAvailableModels(null);
                setListingState("failed");
            }
        }, 500);
        return () => {
            cancelled = true;
            controller.abort();
            window.clearTimeout(timer);
        };
        // model intentionally excluded — listing is keyed on (apiKey, baseUrl).
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [apiKey, baseUrl, accessToken, listModels]);

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
        setAvailableModels(null);
        setListingState("idle");
        setUseCustomModel(false);
        onCleared?.();
    }, [clear, onCleared]);

    const showDropdown =
        listingState === "loaded" &&
        availableModels !== null &&
        availableModels.length > 0 &&
        !useCustomModel;

    const handleModelDropdownChange = (value: string) => {
        if (value === CUSTOM_MODEL_SENTINEL) {
            focusCustomOnNextRender.current = true;
            setUseCustomModel(true);
            return;
        }
        setModel(value);
        onEdit();
    };

    const handleUseDropdown = () => {
        setUseCustomModel(false);
        if (availableModels && availableModels.length > 0 && !availableModels.includes(model.trim())) {
            setModel(availableModels[0]);
            onEdit();
        }
    };

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

            {/* Model */}
            <label className="block">
                <span className="text-[11px] font-medium text-astral-muted mb-1 flex items-center gap-1.5">
                    <span>Model</span>
                    {listingState === "loading" && (
                        <Loader2 size={11} className="animate-spin text-astral-muted/70" />
                    )}
                </span>
                {listingState === "failed" && (
                    <div className="text-[11px] text-astral-muted/80 mb-1">
                        Couldn't load models — enter manually.
                    </div>
                )}
                {showDropdown ? (
                    <div className="relative">
                        <select
                            value={availableModels!.includes(model) ? model : ""}
                            onChange={(e) => handleModelDropdownChange(e.target.value)}
                            className="w-full px-3 py-2 pr-8 text-sm bg-astral-bg border border-white/10 rounded-lg focus:outline-none focus:border-astral-primary/50 text-white appearance-none"
                        >
                            {!availableModels!.includes(model) && (
                                <option value="" disabled>Select a model…</option>
                            )}
                            {availableModels!.map((id) => (
                                <option key={id} value={id}>{id}</option>
                            ))}
                            <option value={CUSTOM_MODEL_SENTINEL}>Custom…</option>
                        </select>
                        <ChevronDown
                            size={14}
                            className="absolute right-2 top-1/2 -translate-y-1/2 text-astral-muted pointer-events-none"
                        />
                    </div>
                ) : (
                    <div className="relative">
                        <input
                            ref={customInputRef}
                            type="text"
                            value={model}
                            onChange={(e) => { setModel(e.target.value); onEdit(); }}
                            placeholder="gpt-4o-mini"
                            className={`w-full px-3 py-2 text-sm bg-astral-bg border border-white/10 rounded-lg focus:outline-none focus:border-astral-primary/50 text-white placeholder:text-astral-muted/50 ${
                                availableModels !== null && availableModels.length > 0 ? "pr-8" : ""
                            }`}
                        />
                        {availableModels !== null && availableModels.length > 0 && (
                            <button
                                type="button"
                                onClick={handleUseDropdown}
                                aria-label="Choose from discovered models"
                                title="Choose from discovered models"
                                className="absolute right-2 top-1/2 -translate-y-1/2 text-astral-muted hover:text-white"
                            >
                                <ChevronDown size={14} />
                            </button>
                        )}
                    </div>
                )}
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
