/**
 * T041 — useLlmConfig + useTokenUsage hook tests.
 *
 * Covers:
 *   - Round-trip through localStorage (save/clear).
 *   - "llm-config-changed" event fires on save and on clear.
 *   - Sign-out simulation does NOT clear the localStorage key (FR-013).
 *   - applyUsageEvent: increments by total_tokens, ignores failure events,
 *     handles total_tokens=null as unknownCalls++, rolls over on local-day boundary.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useLlmConfig } from "../hooks/useLlmConfig";
import { applyUsageEvent, type LLMUsageReportEvent } from "../hooks/useTokenUsage";

// Provide a working fetch stub for testConnection (we don't call it in
// most tests, but the import path requires a global fetch).
beforeEach(() => {
    window.localStorage.clear();
    vi.useRealTimers();
});

const STORAGE_KEY = "astralbody.llm.config.v1";

describe("useLlmConfig — localStorage round-trip", () => {
    it("starts with null when storage is empty", () => {
        const { result } = renderHook(() => useLlmConfig());
        expect(result.current.config).toBeNull();
    });

    it("save() writes to localStorage and dispatches llm-config-changed", () => {
        const handler = vi.fn();
        window.addEventListener("llm-config-changed", handler);
        try {
            const { result } = renderHook(() => useLlmConfig());
            act(() => {
                result.current.save({
                    apiKey: "sk-mykey1234567890abcdef",
                    baseUrl: "https://x.example/v1",
                    model: "m",
                    markConnected: true,
                });
            });
            expect(result.current.config?.apiKey).toBe("sk-mykey1234567890abcdef");
            expect(result.current.config?.connectedAt).toBeTruthy();
            expect(handler).toHaveBeenCalledTimes(1);
            const ev = handler.mock.calls[0][0] as CustomEvent;
            expect(ev.detail.action).toBe("set");
            // Persisted in localStorage
            const persisted = JSON.parse(window.localStorage.getItem(STORAGE_KEY)!);
            expect(persisted.apiKey).toBe("sk-mykey1234567890abcdef");
        } finally {
            window.removeEventListener("llm-config-changed", handler);
        }
    });

    it("clear() removes from localStorage and dispatches llm-config-changed", () => {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
            apiKey: "sk-x", baseUrl: "u", model: "m",
            connectedAt: null, schemaVersion: 1,
        }));
        const handler = vi.fn();
        window.addEventListener("llm-config-changed", handler);
        try {
            const { result } = renderHook(() => useLlmConfig());
            expect(result.current.config?.apiKey).toBe("sk-x");
            act(() => result.current.clear());
            expect(result.current.config).toBeNull();
            expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
            expect(handler).toHaveBeenCalledTimes(1);
            expect((handler.mock.calls[0][0] as CustomEvent).detail.action).toBe("cleared");
        } finally {
            window.removeEventListener("llm-config-changed", handler);
        }
    });

    it("strips trailing slash from baseUrl on save", () => {
        const { result } = renderHook(() => useLlmConfig());
        act(() => result.current.save({
            apiKey: "k", baseUrl: "https://x.example/v1/", model: "m",
        }));
        expect(result.current.config?.baseUrl).toBe("https://x.example/v1");
    });

    it("FR-013: simulating sign-out does NOT remove the localStorage entry", () => {
        // The hook deliberately does NOT subscribe to auth-state changes.
        // This test asserts the contract by demonstrating that any event
        // we might fire to simulate sign-out leaves the key intact.
        const { result } = renderHook(() => useLlmConfig());
        act(() => result.current.save({ apiKey: "k", baseUrl: "u", model: "m" }));
        // Fire several common "sign-out" indicators — none of these
        // should affect our localStorage.
        window.dispatchEvent(new Event("auth:logout"));
        window.dispatchEvent(new Event("storage")); // unrelated key change
        // Hook still reports the same config; storage still populated.
        expect(result.current.config?.apiKey).toBe("k");
        expect(window.localStorage.getItem(STORAGE_KEY)).not.toBeNull();
    });
});

describe("applyUsageEvent — pure increment / rollover / failure semantics", () => {
    const today = (() => {
        const d = new Date();
        return `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, "0")}-${d.getDate().toString().padStart(2, "0")}`;
    })();

    const baseUsage = {
        session: 0, today: 0, todayDate: today,
        lifetime: 0, unknownCalls: 0, perModel: {} as Record<string, number>,
    };

    const evSuccess = (n: number, model = "m"): LLMUsageReportEvent => ({
        feature: "test", model,
        total_tokens: n, prompt_tokens: n, completion_tokens: 0,
        outcome: "success", at: new Date().toISOString(),
    });

    it("adds total_tokens to session/today/lifetime/perModel", () => {
        const out = applyUsageEvent(baseUsage, evSuccess(100));
        expect(out.session).toBe(100);
        expect(out.today).toBe(100);
        expect(out.lifetime).toBe(100);
        expect(out.perModel).toEqual({ m: 100 });
    });

    it("accumulates over multiple events", () => {
        let u = baseUsage;
        u = applyUsageEvent(u, evSuccess(100));
        u = applyUsageEvent(u, evSuccess(200));
        u = applyUsageEvent(u, evSuccess(300));
        expect(u.session).toBe(600);
        expect(u.lifetime).toBe(600);
        expect(u.perModel).toEqual({ m: 600 });
    });

    it("total_tokens=null increments unknownCalls but not numerics", () => {
        const u = applyUsageEvent(baseUsage, {
            ...evSuccess(0), total_tokens: null,
        });
        expect(u.session).toBe(0);
        expect(u.lifetime).toBe(0);
        expect(u.unknownCalls).toBe(1);
    });

    it("outcome=failure does not change any counter", () => {
        const seeded = applyUsageEvent(baseUsage, evSuccess(100));
        const out = applyUsageEvent(seeded, {
            ...evSuccess(500), outcome: "failure",
        });
        expect(out).toEqual(seeded);
    });

    it("rolls over today when stale todayDate is present", () => {
        const stale = { ...baseUsage, today: 999, todayDate: "1999-01-01" };
        const out = applyUsageEvent(stale, evSuccess(100));
        expect(out.todayDate).toBe(today);
        // today resets to 0 then adds the new event
        expect(out.today).toBe(100);
        // lifetime keeps growing across the boundary
        expect(out.lifetime).toBe(100);
    });

    it("per-model breakdown tracks each model independently", () => {
        let u = baseUsage;
        u = applyUsageEvent(u, evSuccess(100, "model-a"));
        u = applyUsageEvent(u, evSuccess(50, "model-b"));
        u = applyUsageEvent(u, evSuccess(25, "model-a"));
        expect(u.perModel).toEqual({ "model-a": 125, "model-b": 50 });
    });
});
