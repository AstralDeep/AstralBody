// Feature 051 — REST surface shared by the three Apple clients: chat list /
// detail / creation, and the 044 native sign-out (client_id attribution).
import Foundation

public struct ChatSummary: Sendable, Identifiable, Equatable {
    public let id: String
    public let title: String
    public let updatedAt: String

    public init?(json: JSONValue) {
        guard let id = json["id"]?.stringValue
            ?? json["chat_id"]?.stringValue else { return nil }
        self.id = id
        self.title = json["title"]?.stringValue ?? "Untitled chat"
        self.updatedAt = json["updated_at"]?.stringValue ?? ""
    }
}

public struct RestClient: Sendable {
    public typealias Transport = @Sendable (URLRequest) async throws -> (Int, Data)

    public let serverBase: URL
    private let transport: Transport
    private let tokenProvider: @Sendable () async -> String?

    public init(serverBase: URL,
                tokenProvider: @escaping @Sendable () async -> String?,
                transport: Transport? = nil) {
        self.serverBase = serverBase
        self.tokenProvider = tokenProvider
        self.transport = transport ?? { request in
            let (data, response) = try await URLSession.shared.data(for: request)
            return ((response as? HTTPURLResponse)?.statusCode ?? 0, data)
        }
    }

    /// ws(s):// twin of the server base for the orchestrator socket.
    public var webSocketURL: URL {
        var comps = URLComponents(url: serverBase, resolvingAgainstBaseURL: false)!
        comps.scheme = comps.scheme == "https" ? "wss" : "ws"
        comps.path = "/ws"
        return comps.url!
    }

    func request(_ method: String, _ path: String, body: JSONValue? = nil) async throws -> (Int, JSONValue) {
        var request = URLRequest(url: serverBase.appendingPathComponent(path))
        request.httpMethod = method
        if let token = await tokenProvider() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try body.encoded()
        }
        let (status, data) = try await transport(request)
        return (status, (try? JSONValue.parse(data)) ?? .object([:]))
    }

    public func chats() async throws -> [ChatSummary] {
        let (status, json) = try await request("GET", "api/chats")
        guard status == 200 else { return [] }
        let items = json["chats"]?.arrayValue ?? json.arrayValue ?? []
        return items.compactMap { ChatSummary(json: $0) }
    }

    public func deleteChat(id: String) async throws -> Bool {
        let (status, _) = try await request("DELETE", "api/chats/\(id)")
        return (200...299).contains(status)
    }

    /// 044 native sign-out: server-side revocation attributed to this client.
    public func logout(clientId: String, refreshToken: String) async throws -> Bool {
        let (status, json) = try await request("POST", "api/auth/logout", body: .object([
            "client_id": .string(clientId),
            "refresh_token": .string(refreshToken),
        ]))
        let ok = json["revoked"]?.boolValue == true || json["queued"]?.boolValue == true
        return status == 200 && ok
    }
}
