import CryptoKit
// Feature 051 — OIDC Authorization Code + PKCE (S256), hand-rolled on Apple
// frameworks exactly as the Windows client hand-rolls it on the Python
// stdlib (research D5: zero third-party Swift dependencies).
import Foundation

public enum PKCE {
    /// RFC 7636 §4.1 — 32 random octets, base64url without padding.
    public static func makeVerifier() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        return base64url(Data(bytes))
    }

    /// RFC 7636 §4.2 — S256: BASE64URL(SHA256(ASCII(verifier))).
    public static func challenge(for verifier: String) -> String {
        let digest = SHA256.hash(data: Data(verifier.utf8))
        return base64url(Data(digest))
    }

    public static func base64url(_ data: Data) -> String {
        data.base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}

/// Builders for the authorize/token requests against a Keycloak realm
/// (`authority` = full realm URL, matching KEYCLOAK_AUTHORITY server-side).
public struct OIDCConfig: Sendable {
    public let authority: URL
    public let clientId: String
    public let redirectURI: String
    public let scope: String

    public init(
        authority: URL, clientId: String, redirectURI: String,
        scope: String = "openid profile email offline_access"
    ) {
        self.authority = authority
        self.clientId = clientId
        self.redirectURI = redirectURI
        self.scope = scope
    }

    public var authorizeEndpoint: URL {
        authority.appendingPathComponent("protocol/openid-connect/auth")
    }

    public var tokenEndpoint: URL {
        authority.appendingPathComponent("protocol/openid-connect/token")
    }

    public func authorizeURL(state: String, challenge: String) -> URL {
        var comps = URLComponents(url: authorizeEndpoint, resolvingAgainstBaseURL: false)!
        comps.queryItems = [
            URLQueryItem(name: "response_type", value: "code"),
            URLQueryItem(name: "client_id", value: clientId),
            URLQueryItem(name: "redirect_uri", value: redirectURI),
            URLQueryItem(name: "scope", value: scope),
            URLQueryItem(name: "state", value: state),
            URLQueryItem(name: "code_challenge", value: challenge),
            URLQueryItem(name: "code_challenge_method", value: "S256"),
        ]
        return comps.url!
    }

    public func tokenRequestBody(code: String, verifier: String) -> String {
        formEncode([
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirectURI,
            "client_id": clientId,
            "code_verifier": verifier,
        ])
    }

    public func refreshRequestBody(refreshToken: String) -> String {
        formEncode([
            "grant_type": "refresh_token",
            "refresh_token": refreshToken,
            "client_id": clientId,
        ])
    }
}

func formEncode(_ fields: [String: String]) -> String {
    var allowed = CharacterSet.alphanumerics
    allowed.insert(charactersIn: "-._~")
    return
        fields
        .sorted { $0.key < $1.key }
        .map { key, value in
            let k = key.addingPercentEncoding(withAllowedCharacters: allowed) ?? key
            let v = value.addingPercentEncoding(withAllowedCharacters: allowed) ?? value
            return "\(k)=\(v)"
        }
        .joined(separator: "&")
}

/// Decoded token response subset (shared by PKCE, device grant and refresh).
public struct TokenSet: Sendable, Equatable {
    public let accessToken: String
    public let refreshToken: String?
    public let expiresAt: Date

    public init(
        accessToken: String, refreshToken: String?, expiresIn: TimeInterval,
        now: Date = Date()
    ) {
        self.accessToken = accessToken
        self.refreshToken = refreshToken
        self.expiresAt = now.addingTimeInterval(expiresIn)
    }

    public init?(json: JSONValue, now: Date = Date()) {
        guard let access = json["access_token"]?.stringValue else { return nil }
        self.accessToken = access
        self.refreshToken = json["refresh_token"]?.stringValue
        self.expiresAt = now.addingTimeInterval(json["expires_in"]?.numberValue ?? 300)
    }

    /// Refresh 60 s before expiry (Windows-client contract).
    public func needsRefresh(now: Date = Date()) -> Bool {
        now >= expiresAt.addingTimeInterval(-60)
    }

    /// Non-validating claims decode (roles/identity display only — the
    /// server re-validates every token at the WS/REST gates).
    public var claims: JSONValue? {
        let parts = accessToken.split(separator: ".")
        guard parts.count >= 2 else { return nil }
        var b64 = String(parts[1]).replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        while b64.count % 4 != 0 { b64 += "=" }
        guard let data = Data(base64Encoded: b64) else { return nil }
        return try? JSONValue.parse(data)
    }

    public var subject: String { claims?["sub"]?.stringValue ?? "unknown" }

    public var displayName: String {
        claims?["name"]?.stringValue
            ?? claims?["preferred_username"]?.stringValue
            ?? subject
    }
}
