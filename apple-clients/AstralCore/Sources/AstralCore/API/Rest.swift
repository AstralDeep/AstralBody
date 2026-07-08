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

    /// The per-user, hash-chained audit log (`GET /api/audit`).
    public func audit() async -> [AuditEvent] {
        var req = URLRequest(url: serverBase.appendingPathComponent("api/audit"))
        if let token = await tokenProvider() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        guard let (data, response) = try? await URLSession.shared.data(for: req),
              (response as? HTTPURLResponse)?.statusCode == 200 else { return [] }
        return AuditEvent.parse(data)
    }

    /// Upload one file (`POST /api/upload`, multipart `file` field) — the exact
    /// web/Android contract. Returns the attachment metadata or nil on failure.
    public func uploadAttachment(filename: String, mimeType: String?,
                                 data fileData: Data) async -> AttachmentUpload? {
        let boundary = "Boundary-\(UUID().uuidString)"
        var req = URLRequest(url: serverBase.appendingPathComponent("api/upload"))
        req.httpMethod = "POST"
        if let token = await tokenProvider() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        var body = Data()
        let mime = mimeType ?? "application/octet-stream"
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: \(mime)\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        req.httpBody = body
        guard let (respData, response) = try? await URLSession.shared.data(for: req),
              (200...299).contains((response as? HTTPURLResponse)?.statusCode ?? 0),
              let json = try? JSONValue.parse(respData),
              let id = json["attachment_id"]?.stringValue else { return nil }
        return AttachmentUpload(
            attachmentId: id,
            filename: json["filename"]?.stringValue ?? filename,
            category: json["category"]?.stringValue ?? "file",
            parserStatus: json["parser_status"]?.stringValue)
    }

    /// Download a server file with Bearer auth — the native twin of the web's
    /// cookie-carrying anchor click on `file_download` components. Handles the
    /// root-relative `/api/download/{session}/{filename}` URLs agents emit by
    /// resolving them against `serverBase`; absolute OFF-origin URLs (e.g. a
    /// `download_card`'s GitHub release asset) are fetched WITHOUT the token —
    /// credentials never leave our origin. Returns a temporary file URL whose
    /// last path component is the intended filename (for share/save UIs).
    public func downloadFile(from urlString: String,
                             suggestedFilename: String? = nil) async throws -> URL {
        guard let url = URL(string: urlString, relativeTo: serverBase)?.absoluteURL else {
            throw URLError(.badURL)
        }
        var req = URLRequest(url: url)
        if url.host == serverBase.host, let token = await tokenProvider() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse,
              (200...299).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        var name = suggestedFilename ?? http.suggestedFilename ?? url.lastPathComponent
        if name.isEmpty || name == "/" { name = "download" }
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("astral-downloads", isDirectory: true)
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let destination = dir.appendingPathComponent(name)
        try data.write(to: destination)
        return destination
    }

    /// Toggle one tool's permission (feature-013 per-(tool,kind) shape):
    /// `PUT /api/agents/{id}/permissions {per_tool_permissions:{tool:{kind:enabled}}}`.
    @discardableResult
    public func setToolPermission(agentId: String, tool: String, kind: String,
                                  enabled: Bool) async -> Bool {
        let body = JSONValue.object([
            "per_tool_permissions": .object([tool: .object([kind: .bool(enabled)])]),
        ])
        let result = try? await request("PUT", "api/agents/\(agentId)/permissions", body: body)
        return (200...299).contains(result?.0 ?? 0)
    }
}

/// Metadata returned by `POST /api/upload` for a staged attachment (feature 031).
public struct AttachmentUpload: Sendable {
    public let attachmentId: String
    public let filename: String
    public let category: String
    /// covered | preparing | pending_admin_approval | unavailable
    public let parserStatus: String?
}
