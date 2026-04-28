/**
 * useAuditStream — subscribes to live audit_append events and merges
 * them with a REST-fetched page of historical entries.
 *
 * The hook is owned by the audit panel; mounting it opens a
 * subscription to the `audit:append` window event broadcast by
 * useWebSocket. New entries are prepended to the list (most-recent
 * first per FR-006) and de-duplicated by event_id so a refresh
 * fetched concurrently with a live push does not double-render.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { listAudit } from "../api/audit";
import type { AuditEvent, AuditListFilters } from "../types/audit";

export interface UseAuditStreamResult {
    items: AuditEvent[];
    nextCursor: string | null;
    isLoading: boolean;
    error: string | null;
    refresh: () => Promise<void>;
    loadMore: () => Promise<void>;
}

const PAGE_SIZE = 50;

function dedupePrepend(prev: AuditEvent[], incoming: AuditEvent): AuditEvent[] {
    if (prev.some((p) => p.event_id === incoming.event_id)) return prev;
    // Insert in recorded_at-desc order. New live entries are almost
    // always strictly newer than the head, so the typical fast path is
    // a single prepend.
    const incomingTs = Date.parse(incoming.recorded_at);
    const headTs = prev.length > 0 ? Date.parse(prev[0].recorded_at) : -Infinity;
    if (incomingTs >= headTs) return [incoming, ...prev];
    const idx = prev.findIndex((p) => Date.parse(p.recorded_at) < incomingTs);
    if (idx === -1) return [...prev, incoming];
    return [...prev.slice(0, idx), incoming, ...prev.slice(idx)];
}

export function useAuditStream(token: string | undefined, filters: AuditListFilters): UseAuditStreamResult {
    const [items, setItems] = useState<AuditEvent[]>([]);
    const [nextCursor, setNextCursor] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const filtersRef = useRef(filters);

    useEffect(() => {
        filtersRef.current = filters;
    }, [filters]);

    const fetchInitial = useCallback(async () => {
        if (!token) {
            setItems([]);
            setNextCursor(null);
            return;
        }
        setIsLoading(true);
        setError(null);
        try {
            const resp = await listAudit(token, { ...filtersRef.current, limit: PAGE_SIZE });
            setItems(resp.items);
            setNextCursor(resp.next_cursor);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setIsLoading(false);
        }
    }, [token]);

    const loadMore = useCallback(async () => {
        if (!token || !nextCursor) return;
        setIsLoading(true);
        try {
            const resp = await listAudit(token, {
                ...filtersRef.current,
                limit: PAGE_SIZE,
                cursor: nextCursor,
            });
            setItems((prev) => {
                const seen = new Set(prev.map((e) => e.event_id));
                const merged = [...prev];
                for (const item of resp.items) {
                    if (!seen.has(item.event_id)) merged.push(item);
                }
                return merged;
            });
            setNextCursor(resp.next_cursor);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setIsLoading(false);
        }
    }, [token, nextCursor]);

    // Initial / filter-change fetch
    useEffect(() => {
        void fetchInitial();
    }, [fetchInitial, filters.event_class, filters.outcome, filters.from, filters.to, filters.q]);

    // Live append subscription
    useEffect(() => {
        const onAppend = (ev: Event) => {
            const detail = (ev as CustomEvent).detail as AuditEvent | undefined;
            if (!detail) return;
            setItems((prev) => dedupePrepend(prev, detail));
        };
        window.addEventListener("audit:append", onAppend as EventListener);
        return () => window.removeEventListener("audit:append", onAppend as EventListener);
    }, []);

    return { items, nextCursor, isLoading, error, refresh: fetchInitial, loadMore };
}
