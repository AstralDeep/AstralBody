/**
 * Tool-selection preference API client.
 *
 * Reads, writes, and clears the per-user, per-agent tool-selection
 * preference that narrows the orchestrator's tool set for chat queries.
 *
 * Backed by the `/api/users/me/tool-selection` endpoints (see
 * specs/013-agent-visibility-tool-picker/contracts/api-tool-selection-pref.md).
 */
import { API_URL } from "../config";

export interface ToolSelectionResponse {
    agent_id: string;
    /**
     * `null` when the user has not narrowed the selection for this agent
     * (orchestrator falls back to full permission-allowed set).
     * A non-null array is the user's explicit subset.
     */
    selected_tools: string[] | null;
}

async function jsonOrThrow<T>(resp: Response): Promise<T> {
    if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new Error(`HTTP ${resp.status}: ${text || resp.statusText}`);
    }
    return (await resp.json()) as T;
}

/**
 * Fetch the user's saved tool selection for the given agent.
 * Returns `selected_tools: null` when the user has not narrowed it.
 */
export async function getUserToolSelection(
    accessToken: string,
    agentId: string,
): Promise<ToolSelectionResponse> {
    const resp = await fetch(
        `${API_URL}/api/users/me/tool-selection?agent_id=${encodeURIComponent(agentId)}`,
        { headers: { Authorization: `Bearer ${accessToken}` } },
    );
    return jsonOrThrow<ToolSelectionResponse>(resp);
}

/**
 * Save (or replace) the user's tool selection for the given agent.
 * The backend rejects empty arrays — callers MUST gate at the UI layer
 * (FR-021) and pass a non-empty list.
 */
export async function setUserToolSelection(
    accessToken: string,
    agentId: string,
    selectedTools: string[],
): Promise<ToolSelectionResponse> {
    const resp = await fetch(`${API_URL}/api/users/me/tool-selection`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ agent_id: agentId, selected_tools: selectedTools }),
    });
    return jsonOrThrow<ToolSelectionResponse>(resp);
}

/**
 * Clear the user's saved selection for the given agent (FR-025 reset).
 * After this call, the orchestrator falls back to the agent's full
 * permission-allowed tool set.
 */
export async function clearUserToolSelection(
    accessToken: string,
    agentId: string,
): Promise<void> {
    const resp = await fetch(
        `${API_URL}/api/users/me/tool-selection?agent_id=${encodeURIComponent(agentId)}`,
        {
            method: "DELETE",
            headers: { Authorization: `Bearer ${accessToken}` },
        },
    );
    if (!resp.ok && resp.status !== 204) {
        const text = await resp.text().catch(() => "");
        throw new Error(`HTTP ${resp.status}: ${text || resp.statusText}`);
    }
}

/**
 * Feature 013 follow-up — per-user, agent-wide on/off switch.
 *
 * Disabling an agent does NOT change its scopes or per-tool permissions;
 * it just removes the agent from the orchestrator's chat dispatch for
 * the requesting user. Re-enabling resumes the prior permission state.
 */
export interface AgentEnabledResponse {
    agent_id: string;
    enabled: boolean;
}

export async function setUserAgentEnabled(
    accessToken: string,
    agentId: string,
    enabled: boolean,
): Promise<AgentEnabledResponse> {
    const resp = await fetch(`${API_URL}/api/users/me/agent-enabled`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ agent_id: agentId, enabled }),
    });
    return jsonOrThrow<AgentEnabledResponse>(resp);
}
