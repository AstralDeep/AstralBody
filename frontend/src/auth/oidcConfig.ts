/**
 * oidcConfig — the production OIDC configuration object passed to
 * `react-oidc-context`'s `<AuthProvider>`.
 *
 * Extracted to its own module (feature 016 T015) so that integration
 * tests can import the EXACT object that `main.tsx` uses, catching
 * regressions in the storage / scope / endpoint wiring at test time.
 *
 * The headline change from the pre-feature-016 baseline is:
 *
 *   userStore + stateStore = SafeWebStorageStateStore(window.localStorage)
 *
 * which is what makes the user's signed-in state survive a full
 * browser/app restart for up to 365 days (FR-001, FR-005).
 */

import type { AuthProviderProps } from "react-oidc-context";
import { BFF_URL } from "../config";
import { SafeWebStorageStateStore } from "./safeStorageStore";
import { recordInteractiveLogin } from "./persistentLogin";

const AUTHORITY = import.meta.env.VITE_KEYCLOAK_AUTHORITY;
const CLIENT_ID = import.meta.env.VITE_KEYCLOAK_CLIENT_ID;

/**
 * Build the OIDC config. Implemented as a function (rather than a
 * top-level const) so the SafeWebStorageStateStore instances are
 * constructed lazily at module import time on real browsers, but
 * tests can call this multiple times against in-memory storage shims.
 */
function buildOidcConfig(): AuthProviderProps {
    const store: Storage | undefined =
        typeof window !== "undefined" && window.localStorage
            ? window.localStorage
            : undefined;

    return {
        authority: AUTHORITY,
        client_id: CLIENT_ID,
        redirect_uri: typeof window !== "undefined" ? window.location.origin : "",
        // Full OIDC metadata so discovery doesn't override our custom token_endpoint.
        // All endpoints point at Keycloak except token_endpoint which goes through our BFF.
        metadata: {
            issuer: AUTHORITY,
            authorization_endpoint: `${AUTHORITY}/protocol/openid-connect/auth`,
            token_endpoint: `${BFF_URL}/auth/token`,  // BFF proxy (injects client_secret server-side)
            userinfo_endpoint: `${AUTHORITY}/protocol/openid-connect/userinfo`,
            end_session_endpoint: `${AUTHORITY}/protocol/openid-connect/logout`,
            jwks_uri: `${AUTHORITY}/protocol/openid-connect/certs`,
            revocation_endpoint: `${AUTHORITY}/protocol/openid-connect/revoke`,
        },
        scope: "openid profile email offline_access",
        automaticSilentRenew: true,
        filterProtocolClaims: true,
        // Feature 016 (FR-001 / FR-005): persist the OIDC user record
        // across full browser/app restarts. Wraps localStorage with a
        // soft-failing `set()` per FR-006 so a quota / sandbox
        // failure doesn't abort the sign-in callback.
        userStore: store ? new SafeWebStorageStateStore({ store }) : undefined,
        stateStore: store ? new SafeWebStorageStateStore({ store }) : undefined,
        onSigninCallback: (user) => {
            // Feature 016 (FR-013): anchor the 365-day clock at this
            // interactive login, and (FR-008) detect/queue user-switch
            // revocation. Also primes wasSilentResume() to return false
            // on its first call after this callback.
            try {
                const sub = (user?.profile as { sub?: string } | undefined)?.sub;
                if (sub) {
                    recordInteractiveLogin(sub, AUTHORITY, CLIENT_ID);
                }
            } catch {
                // Defensive — never let an anchor write block the
                // user from reaching the dashboard.
            }
            // Strip the `?code=...&state=...` from the URL while
            // preserving any chat deep link.
            if (typeof window !== "undefined") {
                const chatParam = new URLSearchParams(window.location.search).get("chat");
                const newUrl = chatParam
                    ? `${window.location.pathname}?chat=${chatParam}`
                    : window.location.pathname;
                window.history.replaceState({}, document.title, newUrl);
            }
        },
    };
}

/** The production OIDC config. */
export const oidcConfig: AuthProviderProps = buildOidcConfig();
