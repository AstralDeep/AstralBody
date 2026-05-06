/**
 * Feature 013 / US1 — agent tab filter rules.
 *
 * Covers FR-001 (every owned agent under My Agents regardless of
 * lifecycle), FR-003 (owned-and-public agents appear in BOTH tabs),
 * and the absence-of-userEmail edge case.
 */
import { describe, it, expect } from "vitest";
import type { Agent } from "../../../hooks/useWebSocket";
import { buildMyAgents, buildPublicAgents, type DraftSummary } from "../../agentTabFilters";

const me = "alice@example.com";
const someoneElse = "bob@example.com";

const ownedPrivate: Agent = {
    id: "a1",
    name: "Alice's private",
    tools: [],
    status: "connected",
    owner_email: me,
    is_public: false,
};
const ownedPublic: Agent = {
    id: "a2",
    name: "Alice's public",
    tools: [],
    status: "connected",
    owner_email: me,
    is_public: true,
};
const othersPublic: Agent = {
    id: "b1",
    name: "Bob's public",
    tools: [],
    status: "connected",
    owner_email: someoneElse,
    is_public: true,
};
const othersPrivate: Agent = {
    id: "b2",
    name: "Bob's private",
    tools: [],
    status: "connected",
    owner_email: someoneElse,
    is_public: false,
};
const unowned: Agent = {
    // pre-013 the `|| !a.owner_email` clause was masking the bug; verify
    // unowned agents no longer leak into My Agents.
    id: "x1",
    name: "Unowned legacy",
    tools: [],
    status: "connected",
    is_public: false,
};

const draftPending: DraftSummary = {
    id: "d1",
    agent_name: "Alice's draft",
    agent_slug: "alices-draft",
    description: "wip",
    status: "pending",
};
const draftLive: DraftSummary = {
    // Drafts that are already live are represented in the live `agents`
    // list, so they MUST NOT be merged again under My Agents.
    id: "d2",
    agent_name: "Alice's published",
    agent_slug: "alices-published",
    description: "shipped",
    status: "live",
};

describe("buildMyAgents — FR-001 every owned agent under My Agents", () => {
    it("includes agents whose owner_email matches the current user", () => {
        const my = buildMyAgents(
            [ownedPrivate, ownedPublic, othersPublic, othersPrivate, unowned],
            [],
            me,
        );
        const ids = my.map(a => a.id).sort();
        expect(ids).toEqual(["a1", "a2"]);
    });

    it("merges in owned drafts that are not yet live, sorted live-then-draft", () => {
        const my = buildMyAgents([ownedPrivate], [draftPending], me);
        expect(my.map(a => a.id)).toEqual(["a1", "draft:d1"]);
        // Drafts carry the synthetic _draftStatus/_draftId fields so the
        // renderer can route to the resume flow + show the lifecycle badge.
        const draftEntry = my.find(a => a.id === "draft:d1");
        expect(draftEntry?._draftStatus).toBe("pending");
        expect(draftEntry?._draftId).toBe("d1");
    });

    it("excludes drafts whose status is 'live' (already represented in agents)", () => {
        const my = buildMyAgents([ownedPrivate], [draftPending, draftLive], me);
        const ids = my.map(a => a.id).sort();
        expect(ids).toEqual(["a1", "draft:d1"]);
    });

    it("returns nothing when userEmail is missing (cannot determine ownership)", () => {
        expect(buildMyAgents([ownedPrivate, ownedPublic], [draftPending], undefined)).toEqual([]);
    });

    it("does NOT include unowned/legacy agents — pre-013 || !a.owner_email clause removed", () => {
        const my = buildMyAgents([unowned], [], me);
        expect(my).toEqual([]);
    });
});

describe("buildPublicAgents — FR-003 owned-and-public agents appear here too", () => {
    it("includes every agent flagged public regardless of owner", () => {
        const pub = buildPublicAgents([ownedPrivate, ownedPublic, othersPublic, othersPrivate]);
        expect(pub.map(a => a.id).sort()).toEqual(["a2", "b1"]);
    });

    it("the same owned-and-public agent appears in BOTH My Agents and Public Agents", () => {
        const my = buildMyAgents([ownedPublic, othersPublic], [], me);
        const pub = buildPublicAgents([ownedPublic, othersPublic]);
        expect(my.find(a => a.id === "a2")).toBeDefined();
        expect(pub.find(a => a.id === "a2")).toBeDefined();
        // Identity is preserved across tabs (same id) — FR-003.
        expect(my.find(a => a.id === "a2")?.name).toBe(pub.find(a => a.id === "a2")?.name);
    });
});
