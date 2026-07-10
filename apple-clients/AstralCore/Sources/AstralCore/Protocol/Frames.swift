// Feature 051 — WS frame parsing (inbound) and builders (outbound).
// Inbound frames are decoded leniently: every frame becomes an InboundFrame
// (name + JSONValue payload) plus typed accessors for the handled set, so an
// unknown or future frame can never crash a client (FR-003).
import Foundation

public struct InboundFrame: Sendable, Equatable {
    public let name: String
    public let payload: JSONValue

    public init(name: String, payload: JSONValue) {
        self.name = name
        self.payload = payload
    }

    public static func parse(_ text: String) -> InboundFrame? {
        guard let data = text.data(using: .utf8),
              let json = try? JSONValue.parse(data),
              let type = json["type"]?.stringValue, !type.isEmpty else { return nil }
        return InboundFrame(name: type, payload: json)
    }

    // MARK: typed accessors (handled set)

    /// ui_render — components already ROTE-adapted for THIS socket.
    public var renderComponents: [AstralComponent] {
        AstralComponent.list(from: payload["components"])
    }

    public var renderTarget: String {
        payload["target"]?.stringValue ?? "canvas"
    }

    /// 051: spoken rendition (watch sockets only; absent elsewhere).
    public var speech: Speech? { Speech(json: payload["speech"]) }

    /// ui_upsert ops.
    public var upsertOps: [UpsertOp] {
        payload["ops"]?.arrayValue?.compactMap { UpsertOp(json: $0) } ?? []
    }

    public var chatId: String? {
        payload["chat_id"]?.stringValue ?? payload["chatId"]?.stringValue
    }

    /// ui_stream_data — incremental narrative components.
    public var streamComponents: [AstralComponent] {
        AstralComponent.list(from: payload["components"])
    }

    public var streamTerminal: Bool {
        payload["terminal"]?.boolValue ?? false
    }

    /// error / stream_error — normalized human message (044 contract).
    public var errorMessage: String {
        payload["message"]?.stringValue
            ?? payload["payload"]?["message"]?.stringValue
            ?? payload["error"]?.stringValue
            ?? "Something went wrong."
    }

    /// auth_required — reason: expired | invalid | hard_cap.
    public var authReason: String {
        payload["reason"]?.stringValue ?? "expired"
    }

    /// chrome_surface — presentation mode (054 first-run gate). "mandatory"
    /// means: accept the surface even though unsolicited and suppress every
    /// dismissal affordance until the server replaces or closes it. Additive
    /// field on an EXISTING frame type (no manifest change); absent on
    /// pre-054 servers ⇒ "replace".
    public var surfaceMode: String {
        payload["mode"]?.stringValue ?? "replace"
    }

    /// chat_status / chat_step progress text. The wire `status` is a MACHINE
    /// code ("thinking"/"executing"/"done"/…) and `message` carries the human
    /// text; `step` is an object on chat_step. Terminal codes resolve to nil
    /// so a finished turn clears the status line instead of sticking on a
    /// literal "done" (parity with the web client's status map).
    public var statusText: String? {
        let status = payload["status"]?.stringValue
        if status == "done" || status == "idle" { return nil }
        if let message = payload["message"]?.stringValue, !message.isEmpty { return message }
        switch status {
        case "thinking": return "Thinking…"
        case "executing", "processing_async", "fixing": return "Working…"
        default: break
        }
        if let step = payload["step"] {
            if let s = step.stringValue, !s.isEmpty { return s }
            if let name = step["name"]?.stringValue ?? step["kind"]?.stringValue, !name.isEmpty {
                return name
            }
        }
        if let status, !status.isEmpty { return status }
        return nil
    }
}

public struct UpsertOp: Sendable, Equatable {
    public let op: String                 // "upsert" | "remove"
    public let componentId: String?
    public let component: AstralComponent?

    public init(op: String, componentId: String?, component: AstralComponent?) {
        self.op = op
        self.componentId = componentId
        self.component = component
    }

    public init?(json: JSONValue) {
        guard let o = json.objectValue, let op = o["op"]?.stringValue else { return nil }
        self.op = op
        self.componentId = o["component_id"]?.stringValue
        self.component = o["component"].flatMap { AstralComponent(json: $0) }
    }
}

// MARK: - Outbound

/// Device identity reported in register_ui — drives the server-side ROTE
/// profile (FR-002). `supportedTypes` is the capability negotiation set: the
/// component types this client renders natively (everything else is
/// substituted server-side).
public struct DeviceDescriptor: Sendable {
    public var deviceType: String
    public var viewportWidth: Int
    public var viewportHeight: Int
    public var pixelRatio: Double
    public var hasTouch: Bool
    public var hasMicrophone: Bool
    public var supportedTypes: [String]
    public var userAgent: String

    public init(deviceType: String, viewportWidth: Int, viewportHeight: Int,
                pixelRatio: Double = 2.0, hasTouch: Bool = true,
                hasMicrophone: Bool = true, supportedTypes: [String],
                userAgent: String) {
        self.deviceType = deviceType
        self.viewportWidth = viewportWidth
        self.viewportHeight = viewportHeight
        self.pixelRatio = pixelRatio
        self.hasTouch = hasTouch
        self.hasMicrophone = hasMicrophone
        self.supportedTypes = supportedTypes
        self.userAgent = userAgent
    }

    public static func ios(viewportWidth: Int, viewportHeight: Int) -> DeviceDescriptor {
        DeviceDescriptor(deviceType: "ios", viewportWidth: viewportWidth,
                         viewportHeight: viewportHeight,
                         supportedTypes: ClientDispositions.ios.nativeComponentTypes,
                         userAgent: "AstralDeep-iOS/0.1")
    }

    public static func macos(viewportWidth: Int, viewportHeight: Int) -> DeviceDescriptor {
        DeviceDescriptor(deviceType: "macos", viewportWidth: viewportWidth,
                         viewportHeight: viewportHeight, pixelRatio: 2.0,
                         hasTouch: false,
                         supportedTypes: ClientDispositions.macos.nativeComponentTypes,
                         userAgent: "AstralDeep-macOS/0.1")
    }

    public static func watch(viewportWidth: Int, viewportHeight: Int) -> DeviceDescriptor {
        DeviceDescriptor(deviceType: "watch", viewportWidth: viewportWidth,
                         viewportHeight: viewportHeight,
                         supportedTypes: ClientDispositions.watch.nativeComponentTypes,
                         userAgent: "AstralDeep-watchOS/0.1")
    }

    var json: JSONValue {
        .object([
            "device_type": .string(deviceType),
            "screen_width": .number(Double(viewportWidth)),
            "screen_height": .number(Double(viewportHeight)),
            "viewport_width": .number(Double(viewportWidth)),
            "viewport_height": .number(Double(viewportHeight)),
            "pixel_ratio": .number(pixelRatio),
            "has_touch": .bool(hasTouch),
            "has_microphone": .bool(hasMicrophone),
            "has_camera": .bool(false),
            "has_file_system": .bool(deviceType != "watch"),
            "connection_type": .string("wifi"),
            "user_agent": .string(userAgent),
            "supported_types": .array(supportedTypes.map { .string($0) }),
        ])
    }
}

public struct ChatAttachmentRef: Sendable {
    public let attachmentId: String
    public let filename: String
    public let category: String

    public init(attachmentId: String, filename: String, category: String) {
        self.attachmentId = attachmentId
        self.filename = filename
        self.category = category
    }

    var json: JSONValue {
        .object(["attachment_id": .string(attachmentId),
                 "filename": .string(filename),
                 "category": .string(category)])
    }
}

public enum Outbound {
    static func encode(_ value: JSONValue) -> String {
        guard let data = try? value.encoded(),
              let text = String(data: data, encoding: .utf8) else { return "{}" }
        return text
    }

    public static func registerUI(token: String, sessionId: String?,
                                  device: DeviceDescriptor, resumed: Bool) -> String {
        encode(.object([
            "type": .string("register_ui"),
            "token": .string(token),
            "session_id": sessionId.map(JSONValue.string) ?? .null,
            "capabilities": .array([.string("render"), .string("stream")]),
            "device": device.json,
            "resumed": .bool(resumed),
        ]))
    }

    public static func chatMessage(_ message: String, sessionId: String?,
                                   displayMessage: String? = nil,
                                   attachments: [ChatAttachmentRef] = []) -> String {
        var payload: [String: JSONValue] = ["message": .string(message)]
        if let display = displayMessage { payload["display_message"] = .string(display) }
        if !attachments.isEmpty {
            payload["attachments"] = .array(attachments.map { $0.json })
        }
        return uiEvent(action: "chat_message", sessionId: sessionId, payload: .object(payload))
    }

    public static func newChat(sessionId: String?, agentId: String? = nil) -> String {
        var payload: [String: JSONValue] = [:]
        if let agent = agentId { payload["agent_id"] = .string(agent) }
        return uiEvent(action: "new_chat", sessionId: sessionId, payload: .object(payload))
    }

    public static func loadChat(sessionId: String?, chatId: String) -> String {
        uiEvent(action: "load_chat", sessionId: sessionId,
                payload: .object(["chat_id": .string(chatId)]))
    }

    public static func updateDevice(sessionId: String, device: DeviceDescriptor) -> String {
        // The orchestrator reads payload["device"] (orchestrator.py update_device
        // handler) — the descriptor must be NESTED, not spread into the payload.
        uiEvent(action: "update_device", sessionId: sessionId,
                payload: .object(["device": device.json]))
    }

    public static func uiEvent(action: String, sessionId: String?, payload: JSONValue) -> String {
        encode(.object([
            "type": .string("ui_event"),
            "action": .string(action),
            "session_id": sessionId.map(JSONValue.string) ?? .null,
            "payload": payload,
        ]))
    }
}
