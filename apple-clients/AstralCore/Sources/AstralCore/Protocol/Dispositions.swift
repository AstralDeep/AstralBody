// Feature 051 — per-client protocol dispositions (the parity matrix, as code).
//
// Every push frame type and component type in the committed manifest
// (backend/shared/ui_protocol.json) MUST have an explicit disposition here
// for each Apple client (FR-003/FR-004/FR-037). The drift-guard test fails
// whenever the manifest gains/loses a name that this table does not account
// for — the same contract as the Windows and Android guards (FR-038).
//
// `.ignored` is a DELIBERATE, documented channel decision (044 precedent:
// admin tools, HTML-only chrome, web-only media stay web-only).
import Foundation

public enum FrameDisposition: Equatable, Sendable {
    case handled
    case ignored(String)   // reason — documentation, not dead weight
}

public enum ComponentDisposition: Equatable, Sendable {
    case native
    case fallback(String)  // rendered via the readable-text fallback; reason
}

public struct ClientDispositions: Sendable {
    public let client: String
    public let frames: [String: FrameDisposition]
    public let components: [String: ComponentDisposition]

    public var nativeComponentTypes: [String] {
        components.compactMap { key, value in
            if case .native = value { return key }
            return nil
        }.sorted()
    }

    // MARK: shared vocabulary baselines

    /// Frames every Apple client handles the same way.
    private static let commonHandled: [String] = [
        "auth_required", "chat_created", "chat_deleted", "chat_loaded",
        "chat_status", "chat_step", "error", "heartbeat", "history_list",
        "notification", "rote_config", "stream_error", "system_config",
        "task_completed", "task_started", "tool_progress", "ui_append",
        "ui_render", "ui_stream_data", "ui_update", "ui_upsert",
        "user_message_acked", "user_preferences",
    ]

    /// Web-only or admin-only frames (044 channel decisions).
    private static let commonIgnored: [String: String] = [
        "audit_append": "admin audit surface is web-only (044)",
        "chrome_render": "raw-HTML chrome region is web-only; natives use chrome_surface",
        "stream_data": "legacy live-stream channel; natives consume ui_stream_data",
        "stream_list": "legacy live-stream channel",
        "stream_subscribed": "legacy live-stream channel",
        "stream_unsubscribed": "legacy live-stream channel",
        "workspace_timeline_mode": "timeline chrome surface is web-only (028)",
    ]

    private static func frames(extraHandled: [String],
                               extraIgnored: [String: String]) -> [String: FrameDisposition] {
        var table: [String: FrameDisposition] = [:]
        for name in commonHandled { table[name] = .handled }
        for (name, reason) in commonIgnored { table[name] = .ignored(reason) }
        for name in extraHandled { table[name] = .handled }
        for (name, reason) in extraIgnored { table[name] = .ignored(reason) }
        return table
    }

    // MARK: iOS (twin of Android — 041/044 dispositions)

    public static let ios = ClientDispositions(
        client: "ios",
        frames: frames(
            extraHandled: [
                "agent_list", "agent_permissions", "agent_permissions_updated",
                "agent_registered", "chrome_menu", "chrome_surface",
                "combine_error", "combine_status", "component_deleted",
                "component_save_error", "component_saved",
                "components_combined", "components_condensed",
                "llm_config_ack", "llm_usage_report", "saved_components_list",
            ],
            extraIgnored: [
                "agent_creation_progress": "agentic-creation drafting UX is web-only for now (matches Android)",
            ]),
        components: fullComponentSet(fallbacks: [
            "generative": "web-only media (044 channel decision)",
            "theme_apply": "themes apply via user_preferences on natives",
            "param_picker": "renders as read-only summary until native picker lands",
        ]))

    // MARK: macOS (twin of Windows — 044 dispositions)

    public static let macos = ClientDispositions(
        client: "macos",
        frames: ios.frames,   // identical frame surface to iOS by design
        components: fullComponentSet(fallbacks: [
            "generative": "web-only media (044 channel decision)",
            "theme_apply": "themes apply via user_preferences on natives",
            "param_picker": "renders as read-only summary until native picker lands",
        ]))

    // MARK: watch (server pre-degrades via the `watch` ROTE profile)

    public static let watch = ClientDispositions(
        client: "watch",
        frames: frames(
            extraHandled: [],
            extraIgnored: [
                "agent_creation_progress": "no drafting UX on the wrist",
                "agent_list": "agent management happens on phone/desktop/web",
                "agent_permissions": "managed on larger clients",
                "agent_permissions_updated": "managed on larger clients",
                "agent_registered": "managed on larger clients",
                "chrome_menu": "no chrome surfaces on the wrist",
                "chrome_surface": "no chrome surfaces on the wrist",
                "combine_error": "workspace curation is a larger-screen task",
                "combine_status": "workspace curation is a larger-screen task",
                "component_deleted": "workspace curation is a larger-screen task",
                "component_save_error": "workspace curation is a larger-screen task",
                "component_saved": "workspace curation is a larger-screen task",
                "components_combined": "workspace curation is a larger-screen task",
                "components_condensed": "workspace curation is a larger-screen task",
                "llm_config_ack": "LLM config is managed on larger clients",
                "llm_usage_report": "usage reporting is a larger-screen surface",
                "saved_components_list": "workspace browsing is a larger-screen task",
            ]),
        components: watchComponentSet())

    // MARK: component tables

    /// The full 35-type vocabulary. iOS/macOS render everything natively
    /// except the listed fallbacks (renderer subset grows during US1/US2 —
    /// a type flips to .native only when its renderer lands and the parity
    /// row is verified).
    private static func fullComponentSet(fallbacks: [String: String]) -> [String: ComponentDisposition] {
        var table: [String: ComponentDisposition] = [:]
        for name in allComponentTypes { table[name] = .native }
        for (name, reason) in fallbacks { table[name] = .fallback(reason) }
        return table
    }

    /// Watch: the server has already degraded the payload (watch ROTE
    /// profile); the client natively renders the compact set the profile can
    /// emit and text-falls-back for anything else (FR-032/033).
    private static func watchComponentSet() -> [String: ComponentDisposition] {
        let native: Set<String> = [
            "alert", "badge", "card", "container", "divider", "keyvalue",
            "list", "metric", "progress", "text",
        ]
        var table: [String: ComponentDisposition] = [:]
        for name in allComponentTypes {
            if native.contains(name) {
                table[name] = .native
            } else {
                table[name] = .fallback("outside the watch profile; server degrades or client text-falls-back")
            }
        }
        return table
    }

    /// Mirror of the committed manifest vocabulary; the drift-guard test
    /// asserts this list — and every per-client table — matches
    /// backend/shared/ui_protocol.json exactly.
    public static let allComponentTypes: [String] = [
        "alert", "audio", "badge", "bar_chart", "button", "card",
        "chat_history", "code", "collapsible", "color_picker", "container",
        "divider", "download_card", "file_download", "file_upload",
        "generative", "grid", "hero", "image", "input", "keyvalue",
        "line_chart", "list", "metric", "param_picker", "pie_chart",
        "plotly_chart", "progress", "rating", "skeleton", "table", "tabs",
        "text", "theme_apply", "timeline",
    ]

    public static let allPushTypes: [String] = [
        "agent_creation_progress", "agent_list", "agent_permissions",
        "agent_permissions_updated", "agent_registered", "audit_append",
        "auth_required", "chat_created", "chat_deleted", "chat_loaded",
        "chat_status", "chat_step", "chrome_menu", "chrome_render",
        "chrome_surface", "combine_error", "combine_status",
        "component_deleted", "component_save_error", "component_saved",
        "components_combined", "components_condensed", "error", "heartbeat",
        "history_list", "llm_config_ack", "llm_usage_report", "notification",
        "rote_config", "saved_components_list", "stream_data", "stream_error",
        "stream_list", "stream_subscribed", "stream_unsubscribed",
        "system_config", "task_completed", "task_started", "tool_progress",
        "ui_append", "ui_render", "ui_stream_data", "ui_update", "ui_upsert",
        "user_message_acked", "user_preferences", "workspace_timeline_mode",
    ]
}
