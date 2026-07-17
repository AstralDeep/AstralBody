// Feature 051 — the pure canvas reducer + streaming consumer, ports of the
// Android `Canvas.kt` and `Streaming.kt`. `Canvas.apply` mutates an ordered
// component list by identity (upsert-in-place / remove); the stream helpers turn
// a `ui_stream_data` / `stream_*` frame into canvas ops keyed by a synthetic
// `stream-<id>` node (per-stream seq dedupe, session filter, terminal forget).
// Feature 055 (US2): a frame carrying `component_id` (a workspace-bridged
// stream) keys the node by that identity from the FIRST frame instead — the
// terminal persist `ui_upsert` then replaces it in place (wire-contract §2).
import Foundation

extension AstralComponent {
    /// A copy with its component identity forced to `id` (for synthetic nodes).
    public func withComponentId(_ id: String) -> AstralComponent {
        var obj = raw.objectValue ?? [:]
        obj["component_id"] = .string(id)
        return AstralComponent(type: type, raw: .object(obj))
    }
}

extension Array where Element == AstralComponent {
    /// Feature 055 (US1) — the uniform welcome purge: drops the ephemeral
    /// welcome components (identity prefixed `wel_`, stamped server-side on
    /// both `id` and `component_id`). iOS/macOS apply it at turn start and
    /// keep `wel_` out of every canvas-history archive; the watch — which has
    /// no turn state — applies it at every `ui_upsert` apply. Unconditional
    /// client-side: with the server flag off the welcome ships id-less,
    /// nothing matches, and this is a no-op (wire-contract §1).
    public func dropWelcome() -> [AstralComponent] {
        filter { $0.componentId?.hasPrefix("wel_") != true }
    }
}

public enum Canvas {
    /// Ordered, identity-keyed apply. `upsert` replaces in place (keeping
    /// position) or appends; `remove` drops by id. Returns a NEW list.
    public static func apply(_ current: [AstralComponent], _ ops: [UpsertOp]) -> [AstralComponent] {
        var order: [String] = []
        var byId: [String: AstralComponent] = [:]
        for (index, comp) in current.enumerated() {
            let key = comp.componentId ?? "anon-\(index)"
            if byId[key] == nil { order.append(key) }
            byId[key] = comp
        }
        for op in ops {
            guard let cid = op.componentId else { continue }
            if op.op == "remove" {
                if byId.removeValue(forKey: cid) != nil { order.removeAll { $0 == cid } }
            } else {
                guard let comp = op.component else { continue }
                if byId[cid] == nil { order.append(cid) }
                byId[cid] = comp
            }
        }
        return order.compactMap { byId[$0] }
    }
}

public let streamNodePrefix = "stream-"

func streamNodeId(_ streamId: String) -> String { "\(streamNodePrefix)\(streamId)" }

/// `componentId` (055) overrides the node — never the dedupe key, which stays
/// on `stream_id` — so a bridged stream never grows a `stream-<id>` twin.
private func nodeKey(
    streamId: String?, toolName: String?,
    componentId: String? = nil
) -> (node: String, key: String)? {
    let identity = componentId.flatMap { $0.isEmpty ? nil : $0 }
    if let streamId { return (identity ?? streamNodeId(streamId), streamId) }
    if let toolName { return (identity ?? "\(streamNodePrefix)tool-\(toolName)", "tool:\(toolName)") }
    return nil
}

private func alertComponent(
    node: String, message: String, retryable: Bool,
    title: String? = nil
) -> AstralComponent {
    AstralComponent(
        type: "alert",
        raw: .object([
            "type": .string("alert"),
            "component_id": .string(node),
            "variant": .string(retryable ? "warning" : "error"),
            "title": .string(title ?? (retryable ? "Live update interrupted" : "Live update failed")),
            "message": .string(message),
        ]))
}

private func containerOf(node: String, comps: [AstralComponent]) -> AstralComponent {
    AstralComponent(
        type: "container",
        raw: .object([
            "type": .string("container"),
            "component_id": .string(node),
            "content": .array(comps.map { $0.raw }),
        ]))
}

/// Translate a `ui_stream_data` / `stream_data` frame into canvas ops. Returns
/// `[]` when dropped (unaddressable / another chat / stale). `seqState`
/// (stream-key → last seq) is mutated in place.
public func streamFrameToOps(
    _ frame: InboundFrame, activeChat: String?,
    seqState: inout [String: Int]
) -> [UpsertOp] {
    let streamId = frame.payload["stream_id"]?.stringValue
    let toolName = frame.payload["tool_name"]?.stringValue
    let componentId = frame.payload["component_id"]?.stringValue
    guard
        let (node, key) = nodeKey(
            streamId: streamId, toolName: toolName,
            componentId: componentId)
    else { return [] }

    let session = frame.payload["session_id"]?.stringValue
    if let session, let activeChat, session != activeChat { return [] }

    if let seq = frame.payload["seq"]?.numberValue.map({ Int($0) }) {
        if let last = seqState[key], seq <= last { return [] }
        seqState[key] = seq
    }
    if frame.streamTerminal { seqState[key] = nil }

    if let error = frame.payload["error"], error.objectValue != nil {
        let message = error["message"]?.stringValue ?? error["code"]?.stringValue ?? "stream error"
        let retryable = error["retryable"]?.boolValue ?? false
        return [
            UpsertOp(
                op: "upsert", componentId: node,
                component: alertComponent(node: node, message: message, retryable: retryable))
        ]
    }

    let comps = frame.streamComponents
    if comps.isEmpty { return [] }
    let body = comps.count == 1 ? comps[0].withComponentId(node) : containerOf(node: node, comps: comps)
    return [UpsertOp(op: "upsert", componentId: node, component: body)]
}

/// A lightweight placeholder shown on `stream_subscribed`. `existingIds` —
/// identities the target canvas already holds — suppresses the placeholder so
/// a device joining mid-stream keeps the re-hydrated component instead of a
/// blank node (web twin: the `stream_subscribed` guard in client.js).
public func subscribeAckOps(_ frame: InboundFrame, existingIds: Set<String> = []) -> [UpsertOp] {
    let streamId = frame.payload["stream_id"]?.stringValue
    let toolName = frame.payload["tool_name"]?.stringValue
    let componentId = frame.payload["component_id"]?.stringValue
    guard
        let (node, _) = nodeKey(
            streamId: streamId, toolName: toolName,
            componentId: componentId)
    else { return [] }
    if existingIds.contains(node) { return [] }
    let tool = toolName ?? "tool"
    let comp = AstralComponent(
        type: "text",
        raw: .object([
            "type": .string("text"), "component_id": .string(node),
            "content": .string("Streaming \(tool)…"),
        ]))
    return [UpsertOp(op: "upsert", componentId: node, component: comp)]
}

/// A standalone `stream_error` control message → an alert at the stream node.
public func streamErrorOps(_ frame: InboundFrame) -> [UpsertOp] {
    let payload = frame.payload["payload"]
    let streamId = payload?["stream_id"]?.stringValue ?? frame.payload["stream_id"]?.stringValue
    let toolName = payload?["tool_name"]?.stringValue ?? frame.payload["tool_name"]?.stringValue
    guard let (node, _) = nodeKey(streamId: streamId, toolName: toolName) else { return [] }
    let message = payload?["message"]?.stringValue ?? frame.payload["error"]?.stringValue ?? "stream error"
    return [
        UpsertOp(
            op: "upsert", componentId: node,
            component: alertComponent(
                node: node, message: message, retryable: false,
                title: "Stream error"))
    ]
}
