/**
 * REST client for the component-feedback subsystem (feature 004).
 *
 * User-side endpoints derive the owning user from the bearer token —
 * cross-user fetches return 404 indistinguishably from not-found. Admin
 * endpoints additionally require the `admin` Keycloak role.
 */
import { API_URL } from "../config";
import type {
    AcceptProposalRequest,
    ComponentFeedback,
    FeedbackAmendRequest,
    FeedbackSubmitAck,
    FeedbackSubmitRequest,
    FlaggedToolEvidence,
    FlaggedToolsResponse,
    ListFeedbackResponse,
    ProposalDetail,
    ProposalsResponse,
    QuarantineListResponse,
    RejectProposalRequest,
} from "../types/feedback";

function headers(token: string): HeadersInit {
    return {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
    };
}

async function fetchJson<T>(url: string, init: RequestInit): Promise<T> {
    const resp = await fetch(url, init);
    if (!resp.ok) {
        const text = await resp.text().catch(() => resp.statusText);
        throw new Error(`${resp.status} ${text}`);
    }
    return (await resp.json()) as T;
}

// ---- User endpoints ----

export async function submitFeedback(
    token: string, body: FeedbackSubmitRequest,
): Promise<FeedbackSubmitAck> {
    return fetchJson<FeedbackSubmitAck>(`${API_URL}/api/feedback`, {
        method: "POST",
        headers: headers(token),
        body: JSON.stringify(body),
    });
}

export interface ListMyFeedbackOpts {
    limit?: number;
    cursor?: string | null;
    lifecycle?: "active" | "superseded" | "retracted";
    source_tool?: string;
    source_agent?: string;
}

export async function listMyFeedback(
    token: string, opts: ListMyFeedbackOpts = {},
): Promise<ListFeedbackResponse> {
    const params = new URLSearchParams();
    if (opts.limit != null) params.set("limit", String(opts.limit));
    if (opts.cursor) params.set("cursor", opts.cursor);
    if (opts.lifecycle) params.set("lifecycle", opts.lifecycle);
    if (opts.source_tool) params.set("source_tool", opts.source_tool);
    if (opts.source_agent) params.set("source_agent", opts.source_agent);
    const q = params.toString();
    return fetchJson<ListFeedbackResponse>(
        `${API_URL}/api/feedback${q ? `?${q}` : ""}`,
        { headers: headers(token) },
    );
}

export async function getMyFeedback(token: string, id: string): Promise<ComponentFeedback> {
    return fetchJson<ComponentFeedback>(
        `${API_URL}/api/feedback/${encodeURIComponent(id)}`,
        { headers: headers(token) },
    );
}

export async function retractMyFeedback(
    token: string, id: string,
): Promise<{ feedback_id: string; lifecycle: string }> {
    return fetchJson(`${API_URL}/api/feedback/${encodeURIComponent(id)}/retract`, {
        method: "POST", headers: headers(token),
    });
}

export async function amendMyFeedback(
    token: string, id: string, body: FeedbackAmendRequest,
): Promise<{ feedback_id: string; prior_id: string; lifecycle: string; comment_safety: string }> {
    return fetchJson(`${API_URL}/api/feedback/${encodeURIComponent(id)}`, {
        method: "PATCH", headers: headers(token), body: JSON.stringify(body),
    });
}

// ---- Admin endpoints ----

export async function listFlaggedTools(
    token: string, opts: { limit?: number; cursor?: string } = {},
): Promise<FlaggedToolsResponse> {
    const params = new URLSearchParams();
    if (opts.limit != null) params.set("limit", String(opts.limit));
    if (opts.cursor) params.set("cursor", opts.cursor);
    const q = params.toString();
    return fetchJson<FlaggedToolsResponse>(
        `${API_URL}/api/admin/feedback/quality/flagged${q ? `?${q}` : ""}`,
        { headers: headers(token) },
    );
}

export async function getFlaggedToolEvidence(
    token: string, agentId: string, toolName: string,
): Promise<FlaggedToolEvidence> {
    return fetchJson<FlaggedToolEvidence>(
        `${API_URL}/api/admin/feedback/quality/flagged/${encodeURIComponent(agentId)}/${encodeURIComponent(toolName)}/evidence`,
        { headers: headers(token) },
    );
}

export async function listProposals(
    token: string, opts: { status?: string; limit?: number; cursor?: string } = {},
): Promise<ProposalsResponse> {
    const params = new URLSearchParams();
    params.set("status", opts.status ?? "pending");
    if (opts.limit != null) params.set("limit", String(opts.limit));
    if (opts.cursor) params.set("cursor", opts.cursor);
    return fetchJson<ProposalsResponse>(
        `${API_URL}/api/admin/feedback/proposals?${params.toString()}`,
        { headers: headers(token) },
    );
}

export async function getProposal(token: string, id: string): Promise<ProposalDetail> {
    return fetchJson<ProposalDetail>(
        `${API_URL}/api/admin/feedback/proposals/${encodeURIComponent(id)}`,
        { headers: headers(token) },
    );
}

export async function acceptProposal(
    token: string, id: string, body: AcceptProposalRequest = {},
): Promise<{ id: string; status: string; applied_at: string | null }> {
    return fetchJson(
        `${API_URL}/api/admin/feedback/proposals/${encodeURIComponent(id)}/accept`,
        { method: "POST", headers: headers(token), body: JSON.stringify(body) },
    );
}

export async function rejectProposal(
    token: string, id: string, body: RejectProposalRequest,
): Promise<{ id: string; status: string; reviewed_at: string | null }> {
    return fetchJson(
        `${API_URL}/api/admin/feedback/proposals/${encodeURIComponent(id)}/reject`,
        { method: "POST", headers: headers(token), body: JSON.stringify(body) },
    );
}

export async function listQuarantine(
    token: string, opts: { status?: "held" | "released" | "dismissed"; limit?: number } = {},
): Promise<QuarantineListResponse> {
    const params = new URLSearchParams();
    params.set("status", opts.status ?? "held");
    if (opts.limit != null) params.set("limit", String(opts.limit));
    return fetchJson<QuarantineListResponse>(
        `${API_URL}/api/admin/feedback/quarantine?${params.toString()}`,
        { headers: headers(token) },
    );
}

export async function releaseQuarantine(
    token: string, feedbackId: string,
): Promise<{ feedback_id: string; status: string }> {
    return fetchJson(
        `${API_URL}/api/admin/feedback/quarantine/${encodeURIComponent(feedbackId)}/release`,
        { method: "POST", headers: headers(token) },
    );
}

export async function dismissQuarantine(
    token: string, feedbackId: string,
): Promise<{ feedback_id: string; status: string }> {
    return fetchJson(
        `${API_URL}/api/admin/feedback/quarantine/${encodeURIComponent(feedbackId)}/dismiss`,
        { method: "POST", headers: headers(token) },
    );
}
