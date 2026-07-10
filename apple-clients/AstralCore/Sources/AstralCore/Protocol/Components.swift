// Feature 051 — server-driven UI component model.
// The server (astralprims → orchestrator → ROTE) owns WHAT is shown; the
// client renders each `type` natively and falls back to readable text for
// anything else (FR-004, FR-032/033 on watch — the server has already
// adapted the payload per this socket's profile).
import Foundation

public struct AstralComponent: Equatable, Sendable {
    public let type: String
    public let raw: JSONValue

    public init(type: String, raw: JSONValue) {
        self.type = type
        self.raw = raw
    }

    public init?(json: JSONValue) {
        guard let t = json["type"]?.stringValue, !t.isEmpty else { return nil }
        self.type = t
        self.raw = json
    }

    public static func list(from json: JSONValue?) -> [AstralComponent] {
        guard let arr = json?.arrayValue else { return [] }
        return arr.compactMap { AstralComponent(json: $0) }
    }

    // MARK: common fields (astralprims conventions)

    public var componentId: String? {
        raw["component_id"]?.stringValue ?? raw["id"]?.stringValue
    }

    public var title: String? { raw["title"]?.stringValue }
    public var content: JSONValue? { raw["content"] }
    public var textContent: String? {
        raw["content"]?.stringValue ?? raw["text"]?.stringValue
    }
    public var message: String? { raw["message"]?.stringValue }
    public var variant: String? { raw["variant"]?.stringValue }
    public var label: String? { raw["label"]?.stringValue }
    public var value: String? {
        raw["value"]?.stringValue ?? raw["value"].map { $0.displayText }
    }
    public var url: String? { raw["url"]?.stringValue }

    public var children: [AstralComponent] {
        for key in ["content", "children"] {
            if let arr = raw[key]?.arrayValue {
                return arr.compactMap { AstralComponent(json: $0) }
            }
        }
        return []
    }

    public var tableHeaders: [String] {
        raw["headers"]?.arrayValue?.map { $0.displayText } ?? []
    }

    public var tableRows: [[String]] {
        raw["rows"]?.arrayValue?.map { row in
            row.arrayValue?.map { $0.displayText } ?? [row.displayText]
        } ?? []
    }

    public var listItems: [String] {
        raw["items"]?.arrayValue?.map { item in
            if let s = item.stringValue { return s }
            if let s = item["text"]?.stringValue ?? item["label"]?.stringValue { return s }
            // Detailed-variant items are {title, url, subtitle, description} —
            // compose a readable line or every web_search result is a blank bullet.
            let headline = item["title"]?.stringValue ?? ""
            let detail = item["subtitle"]?.stringValue ?? item["description"]?.stringValue ?? ""
            let joined = [headline, detail].filter { !$0.isEmpty }.joined(separator: " — ")
            return joined.isEmpty ? item.displayText : joined
        } ?? []
    }

    public var keyValuePairs: [(String, String)] {
        // The wire key is `items[]` of {label, value, hint} (astralprims KeyValue —
        // the web/voice/ROTE renderers all read it); `pairs[]` is a legacy alias.
        let entries = raw["items"]?.arrayValue ?? raw["pairs"]?.arrayValue ?? []
        return entries.compactMap { pair in
            guard let o = pair.objectValue else { return nil }
            let k = o["label"]?.displayText ?? o["key"]?.displayText ?? ""
            let v = o["value"]?.displayText ?? ""
            return (k, v)
        }
    }

    /// Fallback text used when a client has no native renderer for `type`
    /// (parity disposition `.fallback`) — never blank if the server sent
    /// anything human-readable.
    public var fallbackText: String {
        let candidates = [
            title, message, textContent, label, value,
            raw["heading"]?.stringValue, raw["subheading"]?.stringValue,
        ]
        let joined = candidates.compactMap { $0 }.filter { !$0.isEmpty }
        if !joined.isEmpty { return joined.joined(separator: " — ") }
        let kids = children.map(\.fallbackText).filter { !$0.isEmpty }
        if !kids.isEmpty { return kids.joined(separator: "\n") }
        return "[\(type)]"
    }
}

/// Spoken rendition attached by the orchestrator to watch-bound deliveries
/// (contracts/spoken-rendition.md). Absent field ⇒ silent delivery.
public struct Speech: Equatable, Sendable {
    public let ssml: String
    public let text: String

    public init?(json: JSONValue?) {
        guard let o = json?.objectValue else { return nil }
        let ssml = o["ssml"]?.stringValue ?? ""
        let text = o["text"]?.stringValue ?? ""
        if ssml.isEmpty && text.isEmpty { return nil }
        self.ssml = ssml
        self.text = text
    }

    public init(ssml: String, text: String) {
        self.ssml = ssml
        self.text = text
    }
}
