// Feature 051 — the app's "environment" file: the default server URL, Keycloak
// realm, and per-platform OAuth client ids that the AstralDeep clients ship
// with. Sourced from the backend .env (edit here to repoint a build):
//
//   PUBLIC_BASE_URL       -> serverBaseURL (dev)      / sandbox (release)
//   KEYCLOAK_AUTHORITY    -> keycloakAuthority
//   KEYCLOAK_ALLOWED_AZP  -> {ios,macos,watch}ClientId
//
// NOTE: the Keycloak client ids (astral-mobile / astral-desktop / astral-watch)
// and the realm name (Astral) are BACKEND contracts shared with the Android and
// Windows clients — they stay `astral-*` regardless of the AstralDeep app name.
//
// These are DEFAULTS: the sign-in screen still lets a user override the server
// and realm at runtime.
import Foundation

public enum AstralConfig {
    /// Orchestrator base (REST + `/ws`). Dev builds talk to the local
    /// orchestrator (backend `.env` PUBLIC_BASE_URL); release builds talk to
    /// the hosted deployment.
    public static let serverBaseURL: String = {
        #if DEBUG
        return "http://localhost:8001"
        #else
        return "https://sandbox.ai.uky.edu"
        #endif
    }()

    /// Full Keycloak realm URL. Backend `.env` KEYCLOAK_AUTHORITY.
    public static let keycloakAuthority = "https://iam.ai.uky.edu/realms/Astral"

    /// Public OAuth client ids — MUST exist in the realm and appear in
    /// KEYCLOAK_ALLOWED_AZP (astral-desktop, astral-mobile, astral-watch).
    public static let iosClientId = "astral-mobile"
    public static let macosClientId = "astral-desktop"
    public static let watchClientId = "astral-watch"

    /// Custom-scheme PKCE redirect. Must match the Valid Redirect URI set on
    /// the Keycloak clients and the CFBundleURLSchemes entry in Info.plist.
    public static let redirectScheme = "com.personalailabs.astraldeep"
    // Single-slash form — must match the Keycloak Valid Redirect URI exactly.
    public static let redirectURI = "com.personalailabs.astraldeep:/oauth2redirect"
}
