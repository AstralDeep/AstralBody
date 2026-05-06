/**
 * Pure helpers that compute the agent rows shown under "My Agents" and
 * "Public Agents" in DashboardLayout's Agents modal.
 *
 * Extracted from inline JSX (Feature 013 / US1) so the rules can be
 * unit-tested without rendering the whole dashboard.
 *
 * Rules:
 *  - "My Agents" lists every agent the user owns regardless of lifecycle
 *    state (FR-001). Drafts the user owns are merged in with a synthetic
 *    `_draftStatus` so they render alongside live owned agents.
 *  - "Public Agents" lists every agent flagged public — including agents
 *    the current user owns AND has flagged public, intentionally
 *    surfacing them in BOTH tabs (FR-003 / Q4 clarification).
 */
import type { Agent } from "../hooks/useWebSocket";

export interface DraftSummary {
    id: string;
    agent_name: string;
    agent_slug: string;
    description: string;
    status: string;
}

export interface MyAgentEntry extends Agent {
    _draftStatus?: string;
    _draftId?: string;
}

/**
 * Compute the rows shown under "My Agents" — owned live agents merged
 * with the user's drafts (excluding drafts whose status is `live`,
 * which are already represented in the live `agents` list).
 */
export function buildMyAgents(
    agents: Agent[],
    drafts: DraftSummary[],
    userEmail: string | undefined,
): MyAgentEntry[] {
    if (!userEmail) {
        // No identity → cannot determine ownership; show nothing.
        return [];
    }
    const owned: MyAgentEntry[] = agents.filter(a => a.owner_email === userEmail);
    const draftEntries: MyAgentEntry[] = drafts
        .filter(d => d.status !== "live")
        .map(d => ({
            id: `draft:${d.id}`,
            name: d.agent_name,
            description: d.description,
            status: d.status,
            tools: [],
            owner_email: userEmail,
            is_public: false,
            _draftStatus: d.status,
            _draftId: d.id,
        } as MyAgentEntry));
    return [...owned, ...draftEntries];
}

/**
 * Compute the rows shown under "Public Agents" — every agent flagged
 * public. Owned-and-public agents intentionally appear here AND in
 * "My Agents" (FR-003).
 */
export function buildPublicAgents(agents: Agent[]): Agent[] {
    return agents.filter(a => a.is_public);
}
