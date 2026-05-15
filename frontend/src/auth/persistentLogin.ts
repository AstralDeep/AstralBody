/**
 * persistentLogin — Feature 016 client-side helpers for the
 * "stay signed in for 365 days" feature.
 *
 * Responsibilities (one file because the surface is tiny and the
 * concerns are tightly coupled):
 *
 *   1. **Anchor record** at localStorage key
 *      `astralbody.persistentLogin.v1` storing
 *      {schema_version, initial_login_at, last_user_sub, deployment_origin}.
 *      This is the FR-013 365-day-hard-max clock anchor and the FR-008
 *      user-switch detection key.
 *
 *   2. `checkOnLaunch()` — called from `main.tsx` BEFORE the
 *      `<AuthProvider>` mounts. Decides whether the stored OIDC user
 *      record should be honored or forcibly cleared:
 *      * unknown schema_version → clear + re-login (graceful migration)
 *      * `(now - initial_login_at) > 365d` → clear + "session expired"
 *      * `deployment_origin !== window.location.origin` → clear
 *
 *   3. `recordInteractiveLogin(sub)` — called from `onSigninCallback`
 *      after a fresh interactive login. Writes (overwrites) the
 *      anchor and, if the previous `last_user_sub` differs, enqueues
 *      a best-effort server-side revocation of the prior user's
 *      refresh token (FR-008).
 *
 *   4. `wasSilentResume(auth)` — returns true iff the current
 *      authenticated state was reached without a fresh interactive
 *      login on this page load. Drives the `resumed` flag on the
 *      `register_ui` WS message (FR-015).
 *
 *   5. `signOut(auth)` — synchronously clears local credentials
 *      (FR-009a), queues a server-side revocation that retries on
 *      next-online (FR-009b), and never blocks on (b) failing
 *      (FR-009c).
 *
 *   6. `retryWithBackoff()` — 3 attempts at 1s/3s/9s (FR-011);
 *      definitive 4xx aborts immediately.
 *
 *   7. `reportSessionResumeFailed()` — best-effort fire-and-forget
 *      POST to `/api/audit/session-resume-failed` (FR-015).
 *
 * **No new third-party dependencies** (Constitution V).
 */

import type { AuthContextProps } from "react-oidc-context";
import { revocationQueue } from "./revocationQueue";
import { BFF_URL } from "../config";

// ---------------------------------------------------------------------------
// Anchor record
// ---------------------------------------------------------------------------

/** localStorage key for the persistent-login anchor record. */
export const ANCHOR_KEY = "astralbody.persistentLogin.v1";
/** sessionStorage flag set by `onSigninCallback` to mark a fresh interactive login. */
export const JUST_INTERACTIVE_KEY = "astralbody.justInteractive";
/** Hard cap on credential lifetime from interactive login (FR-013). */
export const HARD_MAX_MS = 365 * 24 * 60 * 60 * 1000;
/** Current anchor schema version. Bump for incompatible changes. */
export const ANCHOR_SCHEMA_VERSION = 1 as const;

/** Shape of the persisted anchor record (contracts/oidc-storage.md §3). */
export interface PersistentLoginAnchor {
    schema_version: number;
    /** ISO-8601 UTC instant of the most recent successful interactive login. */
    initial_login_at: string;
    /** OIDC `sub` claim of the user who completed that login. */
    last_user_sub: string;
    /** `window.location.origin` at the moment of the login. */
    deployment_origin: string;
}

/**
 * Read the current anchor record from localStorage. Returns null when
 * absent, unparseable, or shaped wrong (the latter two are treated as
 * "no anchor", which forces re-login on next launch — the safest
 * behavior).
 */
export function getAnchor(): PersistentLoginAnchor | null {
    if (typeof window === "undefined" || !window.localStorage) return null;
    const raw = window.localStorage.getItem(ANCHOR_KEY);
    if (!raw) return null;
    try {
        const parsed = JSON.parse(raw) as Partial<PersistentLoginAnchor>;
        if (
            !parsed ||
            typeof parsed.schema_version !== "number" ||
            typeof parsed.initial_login_at !== "string" ||
            typeof parsed.last_user_sub !== "string" ||
            typeof parsed.deployment_origin !== "string"
        ) {
            return null;
        }
        return parsed as PersistentLoginAnchor;
    } catch {
        return null;
    }
}

/**
 * Write (or replace) the anchor record. Used only by
 * `recordInteractiveLogin` — every successful fresh interactive login
 * resets the 365-day clock by overwriting this record.
 *
 * @internal
 */
function setAnchor(anchor: PersistentLoginAnchor): void {
    if (typeof window === "undefined" || !window.localStorage) return;
    try {
        window.localStorage.setItem(ANCHOR_KEY, JSON.stringify(anchor));
    } catch {
        // Soft-fail per FR-006. The SafeWebStorageStateStore on the
        // OIDC side surfaces the user-facing toast; here we just
        // tolerate the missing anchor and the next launch will
        // require a re-login (since checkOnLaunch will see no record).
    }
}

/**
 * Clear the anchor record. Also removes any stored OIDC user records
 * (every key beginning with `oidc.user:`) so the two storage records
 * stay in sync (invariant I-5).
 */
export function clear(): void {
    if (typeof window === "undefined" || !window.localStorage) return;
    try {
        window.localStorage.removeItem(ANCHOR_KEY);
    } catch {
        // Best-effort.
    }
    // Sweep all oidc-client-ts user records (the library keys them as
    // `oidc.user:<authority>:<client_id>`).
    try {
        const removable: string[] = [];
        for (let i = 0; i < window.localStorage.length; i++) {
            const k = window.localStorage.key(i);
            if (k && k.startsWith("oidc.user:")) removable.push(k);
        }
        for (const k of removable) window.localStorage.removeItem(k);
    } catch {
        // Best-effort.
    }
}

// ---------------------------------------------------------------------------
// Launch-time check
// ---------------------------------------------------------------------------

/** Reasons checkOnLaunch may discard a stored credential. */
export type CheckOnLaunchOutcome =
    | "ok"                              // anchor present and valid — proceed with silent resume
    | "no-anchor"                       // first-time install or post-signout state — normal login flow
    | "hard-max-exceeded"               // 365 days elapsed since interactive login
    | "deployment-mismatch"             // anchor was minted for a different origin
    | "unknown-schema-version"          // anchor has a schema_version we don't recognize
    | "orphaned-oidc-record";           // OIDC record present but no anchor (defensive)

/**
 * Inspect the stored anchor and the OIDC record at module-load time,
 * BEFORE `<AuthProvider>` mounts. Clears both records when the anchor
 * fails one of the spec invariants.
 *
 * Side effect: when this function returns anything other than `"ok"`
 * or `"no-anchor"`, it also fires a best-effort fire-and-forget POST
 * to `/api/audit/session-resume-failed` so the audit log captures the
 * silent expiry / mismatch.
 *
 * @returns Outcome string — the caller may log/branch on this.
 */
export function checkOnLaunch(): CheckOnLaunchOutcome {
    if (typeof window === "undefined") return "no-anchor";

    const anchor = getAnchor();

    // Defensive orphan check: anchor missing but OIDC record present →
    // discard the OIDC record so the user lands on the login screen
    // cleanly rather than entering a half-authenticated state.
    if (!anchor) {
        const hasOidcUser = (() => {
            try {
                for (let i = 0; i < window.localStorage.length; i++) {
                    const k = window.localStorage.key(i);
                    if (k && k.startsWith("oidc.user:")) return true;
                }
            } catch {
                /* ignore */
            }
            return false;
        })();
        if (hasOidcUser) {
            clear();
            return "orphaned-oidc-record";
        }
        return "no-anchor";
    }

    // FR-007 deployment-origin check (defense in depth).
    if (anchor.deployment_origin !== window.location.origin) {
        clear();
        void reportSessionResumeFailed({
            reason: "deployment-mismatch",
            attempts: 0,
            last_error: `anchor origin=${anchor.deployment_origin} but page origin=${window.location.origin}`,
        });
        return "deployment-mismatch";
    }

    // Unknown schema version (FR-008 migration edge case): bump in v2+.
    if (anchor.schema_version !== ANCHOR_SCHEMA_VERSION) {
        clear();
        void reportSessionResumeFailed({
            reason: "token-expired",
            attempts: 0,
            last_error: `unknown anchor schema_version=${anchor.schema_version}`,
        });
        return "unknown-schema-version";
    }

    // FR-013 365-day hard maximum.
    const initialLoginAt = Date.parse(anchor.initial_login_at);
    if (Number.isNaN(initialLoginAt)) {
        // Treat unparseable timestamp as if it failed the hard max.
        clear();
        void reportSessionResumeFailed({
            reason: "token-expired",
            attempts: 0,
            last_error: "anchor.initial_login_at unparseable",
        });
        return "hard-max-exceeded";
    }
    if (Date.now() - initialLoginAt > HARD_MAX_MS) {
        clear();
        void reportSessionResumeFailed({
            reason: "token-expired",
            attempts: 0,
            last_error: `365-day hard max exceeded (login at ${anchor.initial_login_at})`,
        });
        return "hard-max-exceeded";
    }

    return "ok";
}

// ---------------------------------------------------------------------------
// Interactive-login recording and user-switch detection
// ---------------------------------------------------------------------------

/**
 * Record the moment of a fresh interactive login.
 *
 * Resets the FR-013 365-day clock. If the previous `last_user_sub`
 * differs from the new `sub`, enqueues a best-effort revocation of
 * the prior user's refresh token (FR-008 user-switch) by snapshotting
 * it from the OIDC localStorage record BEFORE oidc-client-ts
 * overwrites that record.
 *
 * Called from `onSigninCallback` in `main.tsx`.
 *
 * @param sub - OIDC `sub` claim of the newly-signed-in user.
 * @param authority - The OIDC issuer URL (used to key the anchor and the revocation request).
 * @param clientId - The OIDC client_id (used to read the prior OIDC record key).
 */
export function recordInteractiveLogin(
    sub: string,
    authority: string,
    clientId: string,
): void {
    if (typeof window === "undefined" || !sub) return;

    // FR-008: detect user-switch and enqueue revocation of the prior
    // user's refresh token BEFORE we overwrite the anchor.
    try {
        const prior = getAnchor();
        if (prior && prior.last_user_sub && prior.last_user_sub !== sub) {
            const oidcKey = `oidc.user:${authority}:${clientId}`;
            const raw = window.localStorage.getItem(oidcKey);
            if (raw) {
                try {
                    const user = JSON.parse(raw) as { refresh_token?: string };
                    if (user && typeof user.refresh_token === "string" && user.refresh_token) {
                        revocationQueue.enqueue({
                            refresh_token: user.refresh_token,
                            authority,
                            client_id: clientId,
                            queued_at: new Date().toISOString(),
                            attempts: 0,
                        });
                    }
                } catch {
                    // Malformed OIDC record → nothing to revoke.
                }
            }
        }
    } catch {
        // Best-effort.
    }

    setAnchor({
        schema_version: ANCHOR_SCHEMA_VERSION,
        initial_login_at: new Date().toISOString(),
        last_user_sub: sub,
        deployment_origin: window.location.origin,
    });

    // Mark this page load as having seen the interactive callback so
    // wasSilentResume() returns false on its first read.
    try {
        window.sessionStorage.setItem(JUST_INTERACTIVE_KEY, "1");
    } catch {
        // sessionStorage rejection: wasSilentResume will fall back to
        // returning true, which is a small audit-attribution loss but
        // not a functional regression.
    }
}

// ---------------------------------------------------------------------------
// Silent-resume detection (drives register_ui.resumed)
// ---------------------------------------------------------------------------

/**
 * Returns true iff the current authenticated state was reached without
 * an interactive Keycloak round-trip on this page load.
 *
 * First call after an `onSigninCallback` reads and clears the
 * `astralbody.justInteractive` sessionStorage flag and returns false.
 * Subsequent calls (e.g., WebSocket reconnects in the same tab) return
 * true because the user did not re-authenticate — they are still on
 * the silently-resumed session.
 *
 * Returns false when the user is not authenticated.
 */
export function wasSilentResume(auth: Pick<AuthContextProps, "isAuthenticated">): boolean {
    if (!auth.isAuthenticated) return false;
    if (typeof window === "undefined" || !window.sessionStorage) return true;
    try {
        if (window.sessionStorage.getItem(JUST_INTERACTIVE_KEY) === "1") {
            window.sessionStorage.removeItem(JUST_INTERACTIVE_KEY);
            return false;
        }
    } catch {
        // If sessionStorage throws, the safest answer is "we don't
        // know — call it a resume". Audit-attribution loss only.
    }
    return true;
}

// ---------------------------------------------------------------------------
// Sign-out
// ---------------------------------------------------------------------------

/**
 * Sign the user out (FR-009).
 *
 * Behavior:
 *   1. SYNCHRONOUSLY clear the anchor record. The user MUST appear
 *      signed out locally regardless of network state (FR-009a).
 *   2. Snapshot the current refresh token and enqueue a best-effort
 *      server-side revocation. If the revoke call cannot complete now
 *      it stays in the queue for retry on next `online` event
 *      (FR-009b).
 *   3. Delegate to `auth.signoutRedirect()` which clears the OIDC
 *      record AND hits the Keycloak end-session endpoint.
 *
 * Step 3 may navigate away from the page; steps 1+2 happen first so
 * even an aborted navigation leaves the local state correctly cleared.
 *
 * @param auth - the `react-oidc-context` auth context.
 * @param oidcConfig - the OIDC configuration (needed to derive the
 *                     localStorage key for the refresh-token snapshot).
 */
export async function signOut(
    auth: {
        signoutRedirect: () => Promise<unknown>;
        user?: { refresh_token?: string } | null;
    },
    oidcConfig: { authority: string; client_id: string },
): Promise<void> {
    // Snapshot the refresh token BEFORE clearing anything — once
    // signoutRedirect runs, oidc-client-ts will erase its record.
    let refreshToken: string | undefined;
    try {
        const directUser = auth.user;
        if (directUser && typeof directUser.refresh_token === "string") {
            refreshToken = directUser.refresh_token;
        } else if (typeof window !== "undefined" && window.localStorage) {
            const raw = window.localStorage.getItem(
                `oidc.user:${oidcConfig.authority}:${oidcConfig.client_id}`,
            );
            if (raw) {
                const parsed = JSON.parse(raw) as { refresh_token?: string };
                refreshToken = parsed?.refresh_token;
            }
        }
    } catch {
        // Best-effort. If we can't read it, we can't revoke it.
    }

    // FR-009a: synchronous local clear.
    clear();

    // FR-009b: enqueue revocation. The queue is sessionStorage-backed,
    // FIFO, capped at 16 entries.
    if (refreshToken) {
        revocationQueue.enqueue({
            refresh_token: refreshToken,
            authority: oidcConfig.authority,
            client_id: oidcConfig.client_id,
            queued_at: new Date().toISOString(),
            attempts: 0,
        });
    }

    // FR-009c: never block the user on (b). Even if signoutRedirect
    // fails (e.g., network), the local clear above already happened.
    try {
        await auth.signoutRedirect();
    } catch {
        // Acceptable — the local state is already cleared, the
        // revocation is queued. Worst case the Keycloak server-side
        // SSO session lingers until its own timeout, which the
        // revocation queue will close on next online event.
    }
}

// ---------------------------------------------------------------------------
// Retry policy (FR-011)
// ---------------------------------------------------------------------------

/** Configurable retry budget — exported so tests can override it. */
export const RETRY_DELAYS_MS = [1000, 3000, 9000] as const;

/**
 * 3-attempt exponential backoff wrapper for transient silent-renew
 * failures (FR-011). Aborts immediately on definitive failures (caller
 * decides — the wrapper itself can't distinguish 4xx from 5xx without
 * domain knowledge of the operation).
 *
 * @param op - the operation to retry. Throws to signal failure.
 * @param isDefinitive - predicate that returns true when the caught
 *                       error should NOT be retried (e.g., 4xx auth
 *                       errors). Defaults to "never definitive".
 * @returns the resolved value of `op` on success.
 * @throws the last error if all retries are exhausted, OR the first
 *         error for which `isDefinitive` returned true.
 */
export async function retryWithBackoff<T>(
    op: () => Promise<T>,
    isDefinitive: (err: unknown) => boolean = () => false,
): Promise<T> {
    let lastErr: unknown;
    for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
        try {
            return await op();
        } catch (err) {
            lastErr = err;
            if (isDefinitive(err)) {
                throw err;
            }
            if (attempt === RETRY_DELAYS_MS.length) {
                break;
            }
            const delay = RETRY_DELAYS_MS[attempt];
            await new Promise((resolve) => setTimeout(resolve, delay));
        }
    }
    throw lastErr;
}

// ---------------------------------------------------------------------------
// Audit POST (FR-015)
// ---------------------------------------------------------------------------

/** Body of `POST /api/audit/session-resume-failed` (contracts/audit-actions.md §3). */
export interface SessionResumeFailedReport {
    reason: "retry-budget-exhausted" | "definitive-4xx" | "token-expired" | "deployment-mismatch";
    attempts: number;
    last_error: string;
}

/**
 * Fire-and-forget POST to record an `auth.session_resume_failed`
 * audit event. Best-effort — the call returns immediately and any
 * network failure is swallowed (audit gap acceptable; the in-app
 * recovery UX is not affected).
 *
 * @param report - what to record.
 * @param accessToken - optional bearer token (almost certainly stale,
 *                      but useful for attribution on the server side).
 */
export async function reportSessionResumeFailed(
    report: SessionResumeFailedReport,
    accessToken?: string,
): Promise<void> {
    if (typeof fetch === "undefined") return;
    try {
        const headers: Record<string, string> = {
            "content-type": "application/json",
        };
        if (accessToken) headers["authorization"] = `Bearer ${accessToken}`;
        // Use BFF_URL so the request goes through the configured backend
        // even on Flutter WebView builds that don't share an origin with
        // the API host.
        await fetch(`${BFF_URL}/api/audit/session-resume-failed`, {
            method: "POST",
            headers,
            body: JSON.stringify(report),
            // keepalive lets the request survive page unload, which is
            // exactly what we want when the user is being redirected
            // to the login screen.
            keepalive: true,
        });
    } catch {
        // Network down, CORS blocked, whatever — drop silently.
    }
}
