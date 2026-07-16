// Feature 051 — agent + audit models for the native settings screens, ports of
// the Android `agentsFromJson` (Wire.kt) and `parseAudit` (AstralRest.kt).
import Foundation

public struct Agent: Equatable, Sendable, Identifiable {
    public let id: String
    public let name: String
    public let description: String
    public let isPublic: Bool
    public let scopes: [String: Bool]
    public let tools: [String]
    public let toolDescriptions: [String: String]
    /// Effective per-tool enabled state (server-computed from scopes + overrides).
    public var permissions: [String: Bool]
    /// Each tool's required permission kind (e.g. "tools:read"), for toggling.
    public let toolScopeMap: [String: String]

    public init?(json: JSONValue) {
        guard let id = json["id"]?.stringValue else { return nil }
        self.id = id
        self.name = json["name"]?.stringValue ?? id
        self.description = json["description"]?.stringValue ?? ""
        self.isPublic = json["is_public"]?.boolValue ?? false
        self.scopes = Agent.boolMap(json["scopes"])
        let permissions = Agent.boolMap(json["permissions"])
        self.permissions = permissions
        // `tools` is a list of {name, description} OR plain strings; fall back to keys.
        let toolObjs = (json["tools"]?.arrayValue ?? []).filter { $0.objectValue != nil }
        if !toolObjs.isEmpty {
            self.tools = toolObjs.compactMap { $0["name"]?.stringValue }
            var descs: [String: String] = [:]
            for t in toolObjs {
                if let name = t["name"]?.stringValue { descs[name] = t["description"]?.stringValue ?? "" }
            }
            self.toolDescriptions = descs
        } else {
            let strTools = (json["tools"]?.arrayValue ?? []).compactMap { $0.stringValue }
            self.tools = strTools.isEmpty ? Array(permissions.keys) : strTools
            self.toolDescriptions = Agent.strMap(json["tool_descriptions"])
        }
        self.toolScopeMap = Agent.strMap(json["tool_scope_map"])
    }

    public init(
        id: String, name: String, description: String, isPublic: Bool,
        scopes: [String: Bool], tools: [String], toolDescriptions: [String: String],
        permissions: [String: Bool], toolScopeMap: [String: String]
    ) {
        self.id = id
        self.name = name
        self.description = description
        self.isPublic = isPublic
        self.scopes = scopes
        self.tools = tools
        self.toolDescriptions = toolDescriptions
        self.permissions = permissions
        self.toolScopeMap = toolScopeMap
    }

    public var enabledCount: Int { permissions.values.filter { $0 }.count }
    public var anyEnabled: Bool { permissions.values.contains(true) }

    public static func list(from json: JSONValue?) -> [Agent] {
        (json?.arrayValue ?? []).compactMap { Agent(json: $0) }
    }

    static func boolMap(_ v: JSONValue?) -> [String: Bool] {
        guard let o = v?.objectValue else { return [:] }
        var out: [String: Bool] = [:]
        for (k, value) in o { out[k] = value.boolValue ?? false }
        return out
    }

    static func strMap(_ v: JSONValue?) -> [String: String] {
        guard let o = v?.objectValue else { return [:] }
        var out: [String: String] = [:]
        for (k, value) in o { out[k] = value.stringValue ?? "" }
        return out
    }
}

public struct AuditEvent: Equatable, Sendable {
    public let id: String?
    public let eventClass: String?
    public let action: String?
    public let outcome: String?
    public let recordedAt: String?
    public let outcomeDetail: String?
    public let detail: String?

    /// A stable key for list rendering (server id, else a synthetic fallback).
    public var identity: String { id ?? "\(eventClass ?? "")-\(action ?? "")-\(recordedAt ?? "")" }

    public init(
        id: String?, eventClass: String?, action: String?, outcome: String?,
        recordedAt: String?, outcomeDetail: String? = nil, detail: String? = nil
    ) {
        self.id = id
        self.eventClass = eventClass
        self.action = action
        self.outcome = outcome
        self.recordedAt = recordedAt
        self.outcomeDetail = outcomeDetail
        self.detail = detail
    }

    /// Tolerant shaping of the `/api/audit` body (top-level array or {events|items|data}).
    public static func parse(_ data: Data) -> [AuditEvent] {
        guard let root = try? JSONValue.parse(data) else { return [] }
        let arr: [JSONValue]
        if let a = root.arrayValue {
            arr = a
        } else {
            arr = root["events"]?.arrayValue ?? root["items"]?.arrayValue ?? root["data"]?.arrayValue ?? []
        }
        return arr.compactMap { o in
            guard o.objectValue != nil else { return nil }
            func pick(_ keys: [String]) -> String? {
                for k in keys { if let v = o[k]?.stringValue { return v } }
                return nil
            }
            return AuditEvent(
                id: pick(["id", "event_id"]),
                eventClass: pick(["event_class", "class"]),
                action: pick(["action_type", "action"]),
                outcome: pick(["outcome", "result"]),
                recordedAt: pick(["recorded_at", "created_at", "timestamp"]),
                outcomeDetail: pick(["outcome_detail"]),
                detail: metaSummary(o))
        }
    }

    private static func metaSummary(_ o: JSONValue) -> String? {
        var parts: [String] = []
        if let inputs = o["inputs_meta"]?.objectValue, !inputs.isEmpty {
            parts.append("inputs: \(inputs.count) field(s)")
        }
        if let outputs = o["outputs_meta"]?.objectValue, !outputs.isEmpty {
            parts.append("outputs: \(outputs.count) field(s)")
        }
        let joined = parts.joined(separator: "\n")
        return joined.isEmpty ? nil : joined
    }
}
