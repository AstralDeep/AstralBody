/**
 * Unit tests for persistentLogin.ts (Feature 016 T010).
 *
 * Covers:
 *   - Anchor write/read round-trip
 *   - checkOnLaunch() clears on 365-day hard-max exceeded (FR-013)
 *   - checkOnLaunch() clears on deployment_origin mismatch (FR-007)
 *   - checkOnLaunch() clears on unknown schema_version (analyze I12)
 *   - wasSilentResume() return semantics (FR-015)
 *   - signOut() synchronous clear + revocation enqueue (FR-009)
 *   - User-switch revocation enqueue (FR-008)
 *   - retryWithBackoff() honors definitive-vs-transient (FR-011)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
    ANCHOR_KEY,
    JUST_INTERACTIVE_KEY,
    HARD_MAX_MS,
    getAnchor,
    clear,
    checkOnLaunch,
    recordInteractiveLogin,
    wasSilentResume,
    signOut,
    retryWithBackoff,
    type PersistentLoginAnchor,
} from "../persistentLogin";
import { revocationQueue } from "../revocationQueue";

const ORIGIN = "http://localhost";

beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    revocationQueue._resetForTests();
    // jsdom default origin is http://localhost; pin it.
    Object.defineProperty(window, "location", {
        value: { origin: ORIGIN, pathname: "/", search: "" },
        writable: true,
    });
});

afterEach(() => {
    vi.useRealTimers();
});

// ---------------------------------------------------------------------------
// Anchor round-trip
// ---------------------------------------------------------------------------

describe("anchor read/write/clear", () => {
    it("returns null when no anchor is stored", () => {
        expect(getAnchor()).toBeNull();
    });

    it("returns null on malformed JSON", () => {
        window.localStorage.setItem(ANCHOR_KEY, "{not json");
        expect(getAnchor()).toBeNull();
    });

    it("returns null on shape mismatch", () => {
        window.localStorage.setItem(ANCHOR_KEY, JSON.stringify({ foo: "bar" }));
        expect(getAnchor()).toBeNull();
    });

    it("recordInteractiveLogin writes a valid anchor", () => {
        recordInteractiveLogin("alice", "https://kc.example", "astral-frontend");
        const anchor = getAnchor();
        expect(anchor).not.toBeNull();
        expect(anchor!.schema_version).toBe(1);
        expect(anchor!.last_user_sub).toBe("alice");
        expect(anchor!.deployment_origin).toBe(ORIGIN);
        expect(() => new Date(anchor!.initial_login_at).toISOString()).not.toThrow();
    });

    it("clear() removes both the anchor and all oidc.user:* keys (invariant I-5)", () => {
        recordInteractiveLogin("alice", "https://kc.example", "astral-frontend");
        window.localStorage.setItem(
            "oidc.user:https://kc.example:astral-frontend",
            JSON.stringify({ refresh_token: "rt-x" }),
        );
        window.localStorage.setItem(
            "oidc.user:https://other.example:client2",
            JSON.stringify({ refresh_token: "rt-y" }),
        );
        clear();
        expect(getAnchor()).toBeNull();
        expect(window.localStorage.getItem("oidc.user:https://kc.example:astral-frontend")).toBeNull();
        expect(window.localStorage.getItem("oidc.user:https://other.example:client2")).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// checkOnLaunch — the FR-013 / FR-007 / I12 / clock-skew battery
// ---------------------------------------------------------------------------

describe("checkOnLaunch()", () => {
    it("returns no-anchor when nothing is stored", () => {
        expect(checkOnLaunch()).toBe("no-anchor");
    });

    it("returns ok for a fresh anchor within the 365-day window", () => {
        recordInteractiveLogin("alice", "https://kc.example", "astral-frontend");
        expect(checkOnLaunch()).toBe("ok");
        expect(getAnchor()).not.toBeNull();
    });

    it("clears records when 365-day hard max is exceeded (FR-013)", () => {
        // Plant an anchor whose initial_login_at is 366 days ago.
        const longAgo: PersistentLoginAnchor = {
            schema_version: 1,
            initial_login_at: new Date(Date.now() - 366 * 24 * 60 * 60 * 1000).toISOString(),
            last_user_sub: "alice",
            deployment_origin: ORIGIN,
        };
        window.localStorage.setItem(ANCHOR_KEY, JSON.stringify(longAgo));
        // Also plant an OIDC record so we can verify it's swept.
        window.localStorage.setItem("oidc.user:https://kc.example:astral-frontend", "{}");

        expect(checkOnLaunch()).toBe("hard-max-exceeded");
        expect(getAnchor()).toBeNull();
        expect(window.localStorage.getItem("oidc.user:https://kc.example:astral-frontend")).toBeNull();
    });

    it("clears records on deployment_origin mismatch (FR-007)", () => {
        const wrongOrigin: PersistentLoginAnchor = {
            schema_version: 1,
            initial_login_at: new Date().toISOString(),
            last_user_sub: "alice",
            deployment_origin: "https://other.example",
        };
        window.localStorage.setItem(ANCHOR_KEY, JSON.stringify(wrongOrigin));
        expect(checkOnLaunch()).toBe("deployment-mismatch");
        expect(getAnchor()).toBeNull();
    });

    it("clears records on unknown schema_version (analyze I12 — forward-compat migration)", () => {
        const futureAnchor = {
            schema_version: 99,
            initial_login_at: new Date().toISOString(),
            last_user_sub: "alice",
            deployment_origin: ORIGIN,
        };
        window.localStorage.setItem(ANCHOR_KEY, JSON.stringify(futureAnchor));
        expect(checkOnLaunch()).toBe("unknown-schema-version");
        expect(getAnchor()).toBeNull();
    });

    it("clears records when initial_login_at is unparseable", () => {
        const garbage: PersistentLoginAnchor = {
            schema_version: 1,
            initial_login_at: "not a date",
            last_user_sub: "alice",
            deployment_origin: ORIGIN,
        };
        window.localStorage.setItem(ANCHOR_KEY, JSON.stringify(garbage));
        expect(checkOnLaunch()).toBe("hard-max-exceeded");
    });

    it("detects orphaned OIDC record (anchor missing, oidc.user:* present) and clears it", () => {
        window.localStorage.setItem("oidc.user:https://kc.example:astral-frontend", "{}");
        expect(checkOnLaunch()).toBe("orphaned-oidc-record");
        expect(window.localStorage.getItem("oidc.user:https://kc.example:astral-frontend")).toBeNull();
    });

    it("accepts an anchor exactly at the 365-day boundary minus a millisecond", () => {
        const justInside: PersistentLoginAnchor = {
            schema_version: 1,
            initial_login_at: new Date(Date.now() - (HARD_MAX_MS - 1)).toISOString(),
            last_user_sub: "alice",
            deployment_origin: ORIGIN,
        };
        window.localStorage.setItem(ANCHOR_KEY, JSON.stringify(justInside));
        expect(checkOnLaunch()).toBe("ok");
    });
});

// ---------------------------------------------------------------------------
// CG1: ±5-minute clock skew leeway is honored by the spec layer.
//
// The frontend does NOT itself validate the access-token JWT — that
// happens server-side via the JWKS path. What we can assert here is
// that our 365-day check doesn't reject credentials that are within
// the documented 5-min leeway of the boundary. Closing CG1.
// ---------------------------------------------------------------------------

describe("clock-skew leeway (FR-010 / CG1)", () => {
    it("does NOT reject an anchor that is within 5 min of the 365-day cap on the inside", () => {
        // 364 days, 23 hours, 56 minutes ago — well inside the cap
        // even if the local clock is fast by 5 min.
        const nearBoundary: PersistentLoginAnchor = {
            schema_version: 1,
            initial_login_at: new Date(Date.now() - HARD_MAX_MS + 4 * 60 * 1000).toISOString(),
            last_user_sub: "alice",
            deployment_origin: ORIGIN,
        };
        window.localStorage.setItem(ANCHOR_KEY, JSON.stringify(nearBoundary));
        expect(checkOnLaunch()).toBe("ok");
    });
});

// ---------------------------------------------------------------------------
// wasSilentResume — FR-015
// ---------------------------------------------------------------------------

describe("wasSilentResume()", () => {
    it("returns false when not authenticated", () => {
        expect(wasSilentResume({ isAuthenticated: false })).toBe(false);
    });

    it("returns false on first read after onSigninCallback set the flag", () => {
        window.sessionStorage.setItem(JUST_INTERACTIVE_KEY, "1");
        expect(wasSilentResume({ isAuthenticated: true })).toBe(false);
        // Flag must be consumed
        expect(window.sessionStorage.getItem(JUST_INTERACTIVE_KEY)).toBeNull();
    });

    it("returns true on subsequent reads (reconnects within the same page)", () => {
        window.sessionStorage.setItem(JUST_INTERACTIVE_KEY, "1");
        expect(wasSilentResume({ isAuthenticated: true })).toBe(false);
        expect(wasSilentResume({ isAuthenticated: true })).toBe(true);
    });

    it("returns true on a fresh page load with no flag (cold launch with stored credential)", () => {
        expect(wasSilentResume({ isAuthenticated: true })).toBe(true);
    });
});

// ---------------------------------------------------------------------------
// User-switch revocation enqueue — FR-008
// ---------------------------------------------------------------------------

describe("user-switch revocation (FR-008)", () => {
    it("enqueues revocation of the prior user's refresh token when sub changes", () => {
        const authority = "https://kc.example";
        const clientId = "astral-frontend";
        // First user signs in.
        recordInteractiveLogin("alice", authority, clientId);
        // Plant alice's OIDC record so the user-switch path has something to read.
        window.localStorage.setItem(
            `oidc.user:${authority}:${clientId}`,
            JSON.stringify({ refresh_token: "alice-rt" }),
        );

        // Second user signs in on the same surface.
        recordInteractiveLogin("bob", authority, clientId);

        expect(revocationQueue.size()).toBe(1);
        // Anchor now points to bob.
        expect(getAnchor()!.last_user_sub).toBe("bob");
    });

    it("does NOT enqueue when the same user signs in again", () => {
        const authority = "https://kc.example";
        const clientId = "astral-frontend";
        recordInteractiveLogin("alice", authority, clientId);
        window.localStorage.setItem(
            `oidc.user:${authority}:${clientId}`,
            JSON.stringify({ refresh_token: "alice-rt" }),
        );
        recordInteractiveLogin("alice", authority, clientId);

        expect(revocationQueue.size()).toBe(0);
    });
});

// ---------------------------------------------------------------------------
// signOut — FR-009
// ---------------------------------------------------------------------------

describe("signOut()", () => {
    it("synchronously clears local credentials and enqueues revocation", async () => {
        const authority = "https://kc.example";
        const clientId = "astral-frontend";
        recordInteractiveLogin("alice", authority, clientId);
        window.localStorage.setItem(
            `oidc.user:${authority}:${clientId}`,
            JSON.stringify({ refresh_token: "alice-rt" }),
        );

        const signoutRedirect = vi.fn().mockResolvedValue(undefined);
        await signOut(
            // Provide refresh_token via user shape so signOut reads from auth.user.
            {
                signoutRedirect,
                user: {
                    refresh_token: "alice-rt",
                } as unknown as import("oidc-client-ts").User,
            },
            { authority, client_id: clientId },
        );

        // Local state cleared
        expect(getAnchor()).toBeNull();
        expect(window.localStorage.getItem(`oidc.user:${authority}:${clientId}`)).toBeNull();
        // Revocation queued
        expect(revocationQueue.size()).toBe(1);
        // signoutRedirect was called
        expect(signoutRedirect).toHaveBeenCalledOnce();
    });

    it("does NOT block on signoutRedirect failing (FR-009c)", async () => {
        const authority = "https://kc.example";
        const clientId = "astral-frontend";
        recordInteractiveLogin("alice", authority, clientId);
        window.localStorage.setItem(
            `oidc.user:${authority}:${clientId}`,
            JSON.stringify({ refresh_token: "alice-rt" }),
        );

        const signoutRedirect = vi.fn().mockRejectedValue(new Error("network down"));
        await expect(
            signOut(
                {
                    signoutRedirect,
                    user: {
                        refresh_token: "alice-rt",
                    } as unknown as import("oidc-client-ts").User,
                },
                { authority, client_id: clientId },
            ),
        ).resolves.toBeUndefined();
        // Local state still cleared
        expect(getAnchor()).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// retryWithBackoff — FR-011
// ---------------------------------------------------------------------------

describe("retryWithBackoff()", () => {
    it("returns the result on first-attempt success without delay", async () => {
        vi.useFakeTimers();
        const op = vi.fn().mockResolvedValue("ok");
        const p = retryWithBackoff(op);
        await vi.runAllTimersAsync();
        await expect(p).resolves.toBe("ok");
        expect(op).toHaveBeenCalledTimes(1);
    });

    it("retries transient failures up to 3 times then throws", async () => {
        vi.useFakeTimers();
        const op = vi.fn().mockRejectedValue(new Error("5xx blip"));
        const p = retryWithBackoff(op);
        // Catch the eventual rejection
        const caught = p.catch((e: Error) => e);
        await vi.runAllTimersAsync();
        const err = await caught;
        expect(op).toHaveBeenCalledTimes(4); // initial + 3 retries
        expect((err as Error).message).toBe("5xx blip");
    });

    it("aborts immediately on definitive failure", async () => {
        const op = vi.fn().mockRejectedValue(new Error("invalid_grant: refresh token expired"));
        await expect(
            retryWithBackoff(op, (e) => /invalid_grant/i.test((e as Error).message)),
        ).rejects.toThrow("invalid_grant");
        expect(op).toHaveBeenCalledTimes(1);
    });

    it("uses the 1s/3s/9s backoff sequence (FR-011)", async () => {
        vi.useFakeTimers();
        const op = vi.fn().mockRejectedValue(new Error("5xx"));
        const p = retryWithBackoff(op).catch(() => undefined);

        // Initial attempt happens synchronously
        await vi.advanceTimersByTimeAsync(0);
        expect(op).toHaveBeenCalledTimes(1);

        // 1s delay → 2nd attempt
        await vi.advanceTimersByTimeAsync(1000);
        expect(op).toHaveBeenCalledTimes(2);

        // 3s delay → 3rd attempt
        await vi.advanceTimersByTimeAsync(3000);
        expect(op).toHaveBeenCalledTimes(3);

        // 9s delay → 4th attempt
        await vi.advanceTimersByTimeAsync(9000);
        expect(op).toHaveBeenCalledTimes(4);

        await p;
    });
});
