// Feature 053 — the app's "environment": where the backend lives, which Keycloak
// realm it trusts, and the per-platform OAuth client ids the AstralDeep clients
// ship with.
//
// The backend URL and realm are NO LONGER hardcoded per build configuration.
// They are resolved, in priority order:
//
//   1. a runtime override (iOS/macOS sign-in screen; on watchOS, an override
//      pushed opportunistically from the iPhone companion — see WatchOverrideSync)
//   2. the Info.plist keys `ASTRALServerBaseURL` / `ASTRALKeycloakAuthority`,
//      populated by build-setting substitution from Config/*.xcconfig
//   3. the compiled-in production fallbacks below
//
// Step 3 exists so `AstralCore`'s own unit tests — which run headlessly with no
// app bundle — still resolve, and so a malformed override can never strand the
// app on an unusable endpoint. Repointing a build therefore needs no source edit.
//
// NOTE: the Keycloak client ids (astral-mobile / astral-desktop / astral-watch)
// and the realm name (Astral) are BACKEND contracts shared with the Android and
// Windows clients — iOS shares `astral-mobile` with Android, and macOS shares
// `astral-desktop` with Windows. They stay `astral-*` regardless of the app name.
import Foundation

public enum AstralConfig {
    // MARK: - Info.plist / UserDefaults keys

    /// Info.plist key carrying `$(ASTRAL_SERVER_BASE_URL)` from the xcconfig.
    static let serverBaseURLInfoKey = "ASTRALServerBaseURL"
    /// Info.plist key carrying `$(ASTRAL_KEYCLOAK_AUTHORITY)` from the xcconfig.
    static let keycloakAuthorityInfoKey = "ASTRALKeycloakAuthority"

    /// UserDefaults key holding a runtime server override. Shared by the
    /// iOS/macOS sign-in screen and the watch's companion-pushed override.
    public static let serverOverrideDefaultsKey = "serverBase"
    /// UserDefaults key holding a runtime realm override (iOS/macOS only).
    public static let authorityOverrideDefaultsKey = "authority"

    // MARK: - Compiled-in fallbacks

    /// Used only when neither an override nor an Info.plist value resolves.
    public static let fallbackServerBaseURL = "https://sandbox.ai.uky.edu"
    /// Used only when neither an override nor an Info.plist value resolves.
    public static let fallbackKeycloakAuthority = "https://iam.ai.uky.edu/realms/Astral"

    // MARK: - Resolution

    /// Orchestrator base (REST + `/ws`), resolved from build configuration.
    public static var serverBaseURL: String { resolvedServerBaseURL() }

    /// Full Keycloak realm URL, resolved from build configuration.
    public static var keycloakAuthority: String { resolvedKeycloakAuthority() }

    /// Resolve the backend base URL. `override` wins when it is a usable endpoint.
    public static func resolvedServerBaseURL(
        bundle: Bundle = .main,
        override: String? = nil
    ) -> String {
        resolve(
            override: override,
            infoValue: bundle.object(forInfoDictionaryKey: serverBaseURLInfoKey) as? String,
            fallback: fallbackServerBaseURL)
    }

    /// Resolve the Keycloak authority. `override` wins when it is a usable endpoint.
    public static func resolvedKeycloakAuthority(
        bundle: Bundle = .main,
        override: String? = nil
    ) -> String {
        resolve(
            override: override,
            infoValue: bundle.object(forInfoDictionaryKey: keycloakAuthorityInfoKey) as? String,
            fallback: fallbackKeycloakAuthority)
    }

    /// The resolution ladder, isolated from `Bundle` so it can be tested headlessly.
    ///
    /// A value is only usable if it is a non-empty absolute `http`/`https` URL with
    /// a host. That single rule rejects every realistic failure: an empty string, a
    /// blank override, and — importantly — an *unsubstituted* build setting such as
    /// the literal `$(ASTRAL_SERVER_BASE_URL)`, which would otherwise silently
    /// become the endpoint in a project that forgot to wire the xcconfig.
    static func resolve(override: String?, infoValue: String?, fallback: String) -> String {
        usableEndpoint(override) ?? usableEndpoint(infoValue) ?? fallback
    }

    /// Returns the trimmed value when it is an absolute http(s) URL with a host,
    /// else `nil`. Clients use this to reject a junk override *before* storing it.
    public static func usableEndpoint(_ raw: String?) -> String? {
        guard let raw else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty,
            let url = URL(string: trimmed),
            let scheme = url.scheme?.lowercased(),
            scheme == "http" || scheme == "https",
            let host = url.host,
            !host.isEmpty
        else { return nil }
        return trimmed
    }

    // MARK: - OAuth identities (backend contracts)

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
