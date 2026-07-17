// Feature 051 — minimal any-JSON model.
// Server-driven UI payloads are decoded leniently into JSONValue so unknown
// fields and future additive wire changes never break a client (FR-003/FR-006).
import Foundation

public enum JSONValue: Codable, Equatable, Sendable {
    case null
    case bool(Bool)
    case number(Double)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let b = try? container.decode(Bool.self) {
            self = .bool(b)
        } else if let n = try? container.decode(Double.self) {
            self = .number(n)
        } else if let s = try? container.decode(String.self) {
            self = .string(s)
        } else if let a = try? container.decode([JSONValue].self) {
            self = .array(a)
        } else if let o = try? container.decode([String: JSONValue].self) {
            self = .object(o)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "unsupported JSON")
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null: try container.encodeNil()
        case .bool(let b): try container.encode(b)
        case .number(let n): try container.encode(n)
        case .string(let s): try container.encode(s)
        case .array(let a): try container.encode(a)
        case .object(let o): try container.encode(o)
        }
    }

    // MARK: convenience accessors

    public var stringValue: String? {
        if case .string(let s) = self { return s }
        return nil
    }

    public var numberValue: Double? {
        if case .number(let n) = self { return n }
        return nil
    }

    public var boolValue: Bool? {
        if case .bool(let b) = self { return b }
        return nil
    }

    public var arrayValue: [JSONValue]? {
        if case .array(let a) = self { return a }
        return nil
    }

    public var objectValue: [String: JSONValue]? {
        if case .object(let o) = self { return o }
        return nil
    }

    public subscript(key: String) -> JSONValue? {
        objectValue?[key]
    }

    /// Best-effort human text for fallback rendering.
    public var displayText: String {
        switch self {
        case .null: return ""
        case .bool(let b): return b ? "true" : "false"
        case .number(let n):
            return n == n.rounded() && abs(n) < 1e15
                ? String(Int64(n)) : String(n)
        case .string(let s): return s
        case .array(let a): return a.map(\.displayText).joined(separator: ", ")
        case .object: return ""
        }
    }
}

extension JSONValue {
    /// One-pass JSONSerialization parse. This is the hot path for every WS
    /// frame and REST body; the Codable route (`init(from:)`'s try-cascade)
    /// pays an internal error throw/catch per scalar, which dominates decode
    /// time on canvas-sized payloads. Same lenient any-JSON model.
    public static func parse(_ data: Data) throws -> JSONValue {
        JSONValue(bridging: try JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed]))
    }

    public func encoded() throws -> Data {
        try JSONEncoder().encode(self)
    }
}

extension JSONValue {
    fileprivate init(bridging value: Any) {
        switch value {
        case let dictionary as [String: Any]:
            var object = [String: JSONValue](minimumCapacity: dictionary.count)
            for (key, element) in dictionary { object[key] = JSONValue(bridging: element) }
            self = .object(object)
        case let array as [Any]:
            self = .array(array.map(JSONValue.init(bridging:)))
        case let string as String:
            self = .string(string)
        case let number as NSNumber:
            // JSON true/false arrive as CFBoolean, an NSNumber subclass —
            // type-check it or booleans would decode as numbers 1/0.
            self =
                CFGetTypeID(number) == CFBooleanGetTypeID()
                ? .bool(number.boolValue)
                : .number(number.doubleValue)
        default:
            self = .null  // NSNull (lenient model: never fail on a valid tree)
        }
    }
}
