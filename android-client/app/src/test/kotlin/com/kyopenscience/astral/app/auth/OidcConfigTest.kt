package com.kyopenscience.astral.app.auth

import kotlin.test.Test
import kotlin.test.assertEquals

class OidcConfigTest {
    @Test
    fun derives_keycloak_endpoints() {
        val e = keycloakEndpoints("https://iam.ai.uky.edu/realms/Astral")
        assertEquals("https://iam.ai.uky.edu/realms/Astral/protocol/openid-connect/auth", e.authorizationEndpoint)
        assertEquals("https://iam.ai.uky.edu/realms/Astral/protocol/openid-connect/token", e.tokenEndpoint)
        assertEquals("https://iam.ai.uky.edu/realms/Astral/protocol/openid-connect/logout", e.endSessionEndpoint)
    }

    @Test
    fun trims_trailing_slash() {
        val e = keycloakEndpoints("https://iam.ai.uky.edu/realms/Astral/")
        assertEquals("https://iam.ai.uky.edu/realms/Astral/protocol/openid-connect/token", e.tokenEndpoint)
    }
}
