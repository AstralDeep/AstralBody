/**
 * useTokenUsage — per-device token-usage counters for personal-LLM calls
 * (feature 006-user-llm-config, US3).
 *
 * Subscribes to the `llm-usage-report` window event (forwarded by
 * useWebSocket from the server's `llm_usage_report` WS message) and
 * accumulates four totals into localStorage:
 *
 *   - session   : tokens used in this browser-tab session
 *   - today     : tokens used today (local date), rolls over at the
 *                 device's local midnight
 *   - lifetime  : tokens used on this device, across all sessions and days
 *   - perModel  : map of model name → cumulative lifetime tokens
 *
 * A separate `unknownCalls` counter ticks up when the upstream omitted
 * the `usage` block (some endpoints do this for streamed responses).
 *
 * Reset rules:
 *   - session: reset whenever the hook mounts (i.e. on tab open / page reload / sign-in)
 *   - today: reset when the local-day boundary passes
 *   - lifetime, perModel, unknownCalls: reset only when the user clicks
 *     "Reset usage stats" (the `reset()` callback)
 *
 * Counters are NEVER incremented for events with `outcome: "failure"` —
 * a failed call did not produce billable tokens (or if it did, the
 * upstream didn't tell us, so omitting it is the conservative choice).
 *
 * Calls served using the operator's default credentials are NEVER
 * reported (server-side suppression — FR-016), so the counters here
 * only ever reflect the user's personal-credential spend.
 */
import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "astralbody.llm.config.v1";

interface PersistedShape {
    apiKey?: string;
    baseUrl?: string;
    model?: string;
    connectedAt?: string | null;
    schemaVersion?: 1;
    usage?: {
        today: number;
        todayDate: string;     // local YYYY-MM-DD
        lifetime: number;
        unknownCalls: number;
        perModel: Record<string, number>;
    };
}

export interface TokenUsage {
    session: number;
    today: number;
    todayDate: string;
    lifetime: number;
    unknownCalls: number;
    perModel: Record<string, number>;
}

export interface LLMUsageReportEvent {
    feature: string;
    model: string;
    total_tokens: number | null;
    prompt_tokens: number | null;
    completion_tokens: number | null;
    outcome: "success" | "failure";
    at: string;
}

function localDateString(): string {
    const d = new Date();
    const y = d.getFullYear().toString().padStart(4, "0");
    const m = (d.getMonth() + 1).toString().padStart(2, "0");
    const day = d.getDate().toString().padStart(2, "0");
    return `${y}-${m}-${day}`;
}

function readPersistedUsage(): TokenUsage {
    const today = localDateString();
    const empty: TokenUsage = {
        session: 0,
        today: 0,
        todayDate: today,
        lifetime: 0,
        unknownCalls: 0,
        perModel: {},
    };
    if (typeof window === "undefined") return empty;
    try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        if (!raw) return empty;
        const parsed: PersistedShape = JSON.parse(raw);
        const u = parsed.usage;
        if (!u) return empty;
        // Roll over `today` if the persisted date is stale.
        const persistedToday = typeof u.todayDate === "string" ? u.todayDate : "";
        const persistedTodayCount = persistedToday === today ? Number(u.today) || 0 : 0;
        return {
            session: 0,
            today: persistedTodayCount,
            todayDate: today,
            lifetime: Number(u.lifetime) || 0,
            unknownCalls: Number(u.unknownCalls) || 0,
            perModel: typeof u.perModel === "object" && u.perModel !== null
                ? { ...u.perModel }
                : {},
        };
    } catch {
        return empty;
    }
}

function writePersistedUsage(usage: TokenUsage): void {
    if (typeof window === "undefined") return;
    let existing: PersistedShape = {};
    try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        if (raw) existing = JSON.parse(raw);
    } catch {
        existing = {};
    }
    existing.usage = {
        today: usage.today,
        todayDate: usage.todayDate,
        lifetime: usage.lifetime,
        unknownCalls: usage.unknownCalls,
        perModel: usage.perModel,
    };
    // Only write back if there's a config OR usage to persist; if the
    // shape is otherwise empty, don't create a stub (the user has no
    // saved config and counters of 0).
    if (
        existing.apiKey ||
        existing.baseUrl ||
        existing.model ||
        usage.lifetime > 0 ||
        usage.today > 0 ||
        usage.unknownCalls > 0 ||
        Object.keys(usage.perModel).length > 0
    ) {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(existing));
    }
}

export interface UseTokenUsageResult {
    usage: TokenUsage;
    reset: () => void;
}

/**
 * Apply a single usage event to a TokenUsage state. Pure function —
 * exposed primarily for unit testing the increment / rollover /
 * failure-path semantics.
 */
export function applyUsageEvent(
    prev: TokenUsage,
    ev: LLMUsageReportEvent,
): TokenUsage {
    if (ev.outcome === "failure") {
        // Failures don't change numeric counters at all.
        return prev;
    }
    const today = localDateString();
    const baseToday = prev.todayDate === today ? prev.today : 0;
    if (ev.total_tokens === null || ev.total_tokens === undefined) {
        return {
            ...prev,
            todayDate: today,
            today: baseToday,
            unknownCalls: prev.unknownCalls + 1,
        };
    }
    const delta = Math.max(0, Math.floor(Number(ev.total_tokens)));
    const nextPerModel = { ...prev.perModel };
    nextPerModel[ev.model] = (nextPerModel[ev.model] || 0) + delta;
    return {
        ...prev,
        session: prev.session + delta,
        today: baseToday + delta,
        todayDate: today,
        lifetime: prev.lifetime + delta,
        perModel: nextPerModel,
    };
}

export function useTokenUsage(): UseTokenUsageResult {
    const [usage, setUsage] = useState<TokenUsage>(() => readPersistedUsage());

    useEffect(() => {
        if (typeof window === "undefined") return;
        const onReport = (e: Event) => {
            const ce = e as CustomEvent<LLMUsageReportEvent>;
            const detail = ce.detail;
            if (!detail) return;
            setUsage((prev) => {
                const next = applyUsageEvent(prev, detail);
                writePersistedUsage(next);
                return next;
            });
        };
        window.addEventListener("llm-usage-report", onReport);
        return () => window.removeEventListener("llm-usage-report", onReport);
    }, []);

    const reset = useCallback(() => {
        const today = localDateString();
        const cleared: TokenUsage = {
            session: 0,
            today: 0,
            todayDate: today,
            lifetime: 0,
            unknownCalls: 0,
            perModel: {},
        };
        setUsage(cleared);
        writePersistedUsage(cleared);
    }, []);

    return { usage, reset };
}
