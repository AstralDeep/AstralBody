/**
 * useLlmConfig — localStorage-backed personal LLM configuration
 * (feature 006-user-llm-config).
 *
 * The user's API key, base URL, and model live ONLY on this device.
 * The hook:
 *
 *   - Reads/writes localStorage key `astralbody.llm.config.v1`.
 *   - Exposes `save(c)` / `clear()` / `testConnection(c)`.
 *   - Emits a window `llm-config-changed` event on save/clear so the
 *     WebSocket hook can dispatch the corresponding `llm_config_set` /
 *     `llm_config_clear` message to the server.
 *   - Sets `connectedAt` on a successful Test Connection probe; clears
 *     it when `save()` is called without an immediately-prior probe.
 *   - Does NOT subscribe to auth-state changes — sign-out, token
 *     refresh, and session expiry leave the localStorage key untouched
 *     (FR-013).
 *
 * Persistence: localStorage. Threat model: the key resides on the
 * user's device. The settings panel surfaces a privacy notice making
 * this explicit. No server-side store is created.
 */
import { useCallback, useEffect, useState } from "react";

import { testLlmConnection, type TestConnectionResponse } from "../api/llm";

const STORAGE_KEY = "astralbody.llm.config.v1";

export interface LlmConfig {
    apiKey: string;
    baseUrl: string;
    model: string;
    connectedAt: string | null;
    schemaVersion: 1;
}

export interface UseLlmConfigResult {
    config: LlmConfig | null;
    save: (c: { apiKey: string; baseUrl: string; model: string; markConnected?: boolean }) => void;
    clear: () => void;
    testConnection: (
        c: { apiKey: string; baseUrl: string; model: string },
        token: string | undefined,
    ) => Promise<TestConnectionResponse>;
}

function readStorage(): LlmConfig | null {
    if (typeof window === "undefined") return null;
    try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (
            typeof parsed === "object" &&
            parsed !== null &&
            typeof parsed.apiKey === "string" &&
            typeof parsed.baseUrl === "string" &&
            typeof parsed.model === "string" &&
            parsed.schemaVersion === 1
        ) {
            return {
                apiKey: parsed.apiKey,
                baseUrl: parsed.baseUrl,
                model: parsed.model,
                connectedAt:
                    typeof parsed.connectedAt === "string" ? parsed.connectedAt : null,
                schemaVersion: 1,
            };
        }
    } catch {
        // Corrupt JSON — treat as absent. Do not throw into the UI.
    }
    return null;
}

function writeStorage(c: LlmConfig | null): void {
    if (typeof window === "undefined") return;
    if (c === null) {
        window.localStorage.removeItem(STORAGE_KEY);
    } else {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(c));
    }
}

function emitChange(action: "set" | "cleared", config: LlmConfig | null): void {
    if (typeof window === "undefined") return;
    window.dispatchEvent(
        new CustomEvent("llm-config-changed", { detail: { action, config } }),
    );
}

export function useLlmConfig(): UseLlmConfigResult {
    const [config, setConfig] = useState<LlmConfig | null>(() => readStorage());

    // Keep the in-memory state in sync if a different tab modifies the
    // same localStorage key (storage events fire only in OTHER tabs;
    // see MDN docs).
    useEffect(() => {
        if (typeof window === "undefined") return;
        const onStorage = (ev: StorageEvent) => {
            if (ev.key !== STORAGE_KEY && ev.key !== null) return;
            setConfig(readStorage());
        };
        window.addEventListener("storage", onStorage);
        return () => window.removeEventListener("storage", onStorage);
    }, []);

    const save = useCallback(
        (c: { apiKey: string; baseUrl: string; model: string; markConnected?: boolean }) => {
            const next: LlmConfig = {
                apiKey: c.apiKey,
                baseUrl: c.baseUrl.replace(/\/+$/, ""),
                model: c.model,
                connectedAt: c.markConnected ? new Date().toISOString() : null,
                schemaVersion: 1,
            };
            writeStorage(next);
            setConfig(next);
            emitChange("set", next);
        },
        [],
    );

    const clear = useCallback(() => {
        writeStorage(null);
        setConfig(null);
        emitChange("cleared", null);
    }, []);

    const testConnection = useCallback(
        async (
            c: { apiKey: string; baseUrl: string; model: string },
            token: string | undefined,
        ): Promise<TestConnectionResponse> => {
            if (!token) {
                throw new Error("Not signed in — cannot run Test Connection");
            }
            return await testLlmConnection(token, {
                api_key: c.apiKey,
                base_url: c.baseUrl,
                model: c.model,
            });
        },
        [],
    );

    return { config, save, clear, testConnection };
}
