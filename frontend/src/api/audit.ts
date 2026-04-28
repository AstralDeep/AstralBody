/**
 * REST client for the audit-log API (feature 003-agent-audit-log).
 *
 * The audit endpoints derive the owning user from the bearer token; this
 * client never sends a user_id parameter (FR-007 / FR-019). Cross-user
 * fetches return 404 indistinguishable from non-existent ids — the
 * client surfaces the same error in either case.
 */
import { API_URL } from "../config";
import type {
    AuditEvent,
    AuditListFilters,
    AuditListResponse,
} from "../types/audit";

function buildHeaders(token: string): HeadersInit {
    return {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
    };
}

function buildQuery(filters: AuditListFilters): string {
    const params = new URLSearchParams();
    if (filters.limit != null) params.set("limit", String(filters.limit));
    if (filters.cursor) params.set("cursor", filters.cursor);
    for (const ec of filters.event_class ?? []) params.append("event_class", ec);
    for (const oc of filters.outcome ?? []) params.append("outcome", oc);
    if (filters.from) params.set("from", filters.from);
    if (filters.to) params.set("to", filters.to);
    if (filters.q) params.set("q", filters.q);
    const s = params.toString();
    return s ? `?${s}` : "";
}

export async function listAudit(
    token: string,
    filters: AuditListFilters = {},
): Promise<AuditListResponse> {
    const url = `${API_URL}/api/audit${buildQuery(filters)}`;
    const resp = await fetch(url, { headers: buildHeaders(token) });
    if (!resp.ok) {
        const text = await resp.text().catch(() => resp.statusText);
        throw new Error(`audit list failed (${resp.status}): ${text}`);
    }
    return (await resp.json()) as AuditListResponse;
}

export async function getAudit(token: string, eventId: string): Promise<AuditEvent> {
    const url = `${API_URL}/api/audit/${encodeURIComponent(eventId)}`;
    const resp = await fetch(url, { headers: buildHeaders(token) });
    if (!resp.ok) {
        const text = await resp.text().catch(() => resp.statusText);
        throw new Error(`audit detail failed (${resp.status}): ${text}`);
    }
    return (await resp.json()) as AuditEvent;
}
