// Feature 051 — token persistence (Keychain on device, in-memory for tests)
// and the refresh strategy per platform (research D7):
//   iOS/macOS → refresh directly against the IdP token endpoint (Windows
//               precedent, public client);
//   watch     → refresh via the backend broker (single TLS peer).
import Foundation
#if canImport(Security)
import Security
#endif

public protocol TokenStorage: Sendable {
    func load() -> StoredTokens?
    func save(_ tokens: StoredTokens)
    func wipe()
}

public struct StoredTokens: Codable, Sendable, Equatable {
    public var accessToken: String
    public var refreshToken: String?
    public var expiresAt: Date

    public init(from set: TokenSet) {
        self.accessToken = set.accessToken
        self.refreshToken = set.refreshToken
        self.expiresAt = set.expiresAt
    }

    public var tokenSet: TokenSet {
        TokenSet(accessToken: accessToken, refreshToken: refreshToken,
                 expiresIn: expiresAt.timeIntervalSinceNow)
    }
}

public final class InMemoryTokenStore: TokenStorage, @unchecked Sendable {
    private var tokens: StoredTokens?
    private let lock = NSLock()

    public init() {}

    public func load() -> StoredTokens? {
        lock.lock(); defer { lock.unlock() }
        return tokens
    }

    public func save(_ tokens: StoredTokens) {
        lock.lock(); defer { lock.unlock() }
        self.tokens = tokens
    }

    public func wipe() {
        lock.lock(); defer { lock.unlock() }
        tokens = nil
    }
}

#if canImport(Security)
/// Keychain-backed store (FR-007: tokens live in the platform keychain).
public final class KeychainTokenStore: TokenStorage, @unchecked Sendable {
    private let service: String

    public init(service: String = "com.kyopenscience.astral.tokens") {
        self.service = service
    }

    private var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: "session"]
    }

    public func load() -> StoredTokens? {
        var q = query
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess,
              let data = out as? Data else { return nil }
        return try? JSONDecoder().decode(StoredTokens.self, from: data)
    }

    public func save(_ tokens: StoredTokens) {
        guard let data = try? JSONEncoder().encode(tokens) else { return }
        var add = query
        add[kSecValueData as String] = data
        let status = SecItemAdd(add as CFDictionary, nil)
        if status == errSecDuplicateItem {
            SecItemUpdate(query as CFDictionary,
                          [kSecValueData as String: data] as CFDictionary)
        }
    }

    public func wipe() {
        SecItemDelete(query as CFDictionary)
    }
}
#endif

/// How a session obtains a fresh access token when the current one nears
/// expiry. Both paths keep the sign-in interactive anchor untouched — the
/// realm's session-max policy bounds them (research D7).
public enum RefreshStrategy: Sendable {
    /// Direct to the IdP token endpoint (iOS/macOS; Windows precedent).
    case direct(OIDCConfig)
    /// Via the backend broker (watch; single TLS peer, FR-021).
    case broker(DeviceLoginClient)

    public func refresh(refreshToken: String) async throws -> TokenSet {
        switch self {
        case .direct(let config):
            var request = URLRequest(url: config.tokenEndpoint)
            request.httpMethod = "POST"
            request.setValue("application/x-www-form-urlencoded",
                             forHTTPHeaderField: "Content-Type")
            request.httpBody = Data(config.refreshRequestBody(refreshToken: refreshToken).utf8)
            let (data, response) = try await URLSession.shared.data(for: request)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard status == 200, let json = try? JSONValue.parse(data),
                  let tokens = TokenSet(json: json) else {
                throw DeviceLoginError.unavailable("refresh rejected (HTTP \(status))")
            }
            return tokens
        case .broker(let client):
            return try await client.refresh(refreshToken: refreshToken)
        }
    }
}
