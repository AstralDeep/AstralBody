package com.kyopenscience.astral.app

/**
 * App configuration seams. The defaults point at the deployment; the Keycloak
 * authority + an in-app/override mechanism are finalized with auth in US1.
 */
object AppConfig {
    /** Orchestrator WebSocket endpoint. */
    const val WS_URL: String = "wss://sandbox.ai.uky.edu/ws"

    /** REST base (audit, etc.) — same origin as [WS_URL]. */
    const val API_BASE: String = "https://sandbox.ai.uky.edu"

    /** Keycloak realm authority (OIDC discovery base) — used by US1 auth. */
    const val KEYCLOAK_AUTHORITY: String = "https://iam.ai.uky.edu/realms/Astral"

    /** Dedicated public client id (PKCE). */
    const val OIDC_CLIENT_ID: String = "astral-mobile"

    /** Custom-scheme redirect registered on the astral-mobile client. */
    const val OIDC_REDIRECT_URI: String = "com.kyopenscience.astral:/oauth2redirect"
}
