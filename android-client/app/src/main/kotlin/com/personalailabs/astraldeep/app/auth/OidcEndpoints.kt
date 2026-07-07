package com.personalailabs.astraldeep.app.auth

/** Keycloak OIDC endpoints for a realm. */
data class OidcEndpoints(
    val authorizationEndpoint: String,
    val tokenEndpoint: String,
    val endSessionEndpoint: String,
)

/**
 * Derive Keycloak's OIDC endpoints from a realm authority (e.g.
 * `https://iam.ai.uky.edu/realms/Astral`). Pure → unit-tested; avoids a network
 * discovery round-trip for the well-known Keycloak paths.
 */
fun keycloakEndpoints(authority: String): OidcEndpoints {
    val base = authority.trimEnd('/')
    return OidcEndpoints(
        authorizationEndpoint = "$base/protocol/openid-connect/auth",
        tokenEndpoint = "$base/protocol/openid-connect/token",
        endSessionEndpoint = "$base/protocol/openid-connect/logout",
    )
}
