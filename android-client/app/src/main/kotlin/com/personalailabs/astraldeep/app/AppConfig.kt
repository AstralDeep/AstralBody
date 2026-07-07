package com.personalailabs.astraldeep.app

/**
 * App configuration seams. The defaults point at the deployment; the Keycloak
 * authority + an in-app/override mechanism are finalized with auth in US1.
 */
object AppConfig {
    /**
     * Orchestrator endpoints. Debug builds target the LOCAL dev orchestrator;
     * release builds target the TLS deployment.
     *
     * From the Android emulator, the host machine's loopback is the special alias
     * 10.0.2.2 — NOT "localhost" (that is the emulator itself). A physical device
     * on the same Wi-Fi uses the host's LAN IP instead. The WS URL MUST use
     * ws://|wss:// and end in /ws.
     */
    val WS_URL: String = if (BuildConfig.DEBUG) "ws://10.0.2.2:8001/ws" else "wss://sandbox.ai.uky.edu/ws"

    /** REST base (audit, etc.) — same host as [WS_URL]. */
    val API_BASE: String = if (BuildConfig.DEBUG) "http://10.0.2.2:8001" else "https://sandbox.ai.uky.edu"

    /** Keycloak realm authority (OIDC discovery base) — used by US1 auth. */
    const val KEYCLOAK_AUTHORITY: String = "https://iam.ai.uky.edu/realms/Astral"

    /** Dedicated public client id (PKCE). */
    const val OIDC_CLIENT_ID: String = "astral-mobile"

    /** Custom-scheme redirect registered on the astral-mobile client. */
    const val OIDC_REDIRECT_URI: String = "com.personalailabs.astraldeep:/oauth2redirect"
}
