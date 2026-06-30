package com.kyopenscience.astral.app.auth

/**
 * Debug-only sign-in shortcut. In debug builds this exposes the mock-auth
 * `dev-token` for local testing against a mock-auth orchestrator. The release
 * variant (src/release) returns null, so this path is compiled OUT of release
 * builds — real Keycloak is the product auth (FR-002).
 */
object DevAuth {
    val devToken: String? = "dev-token"
}
