package com.kyopenscience.astral.core.protocol

/**
 * Frame classification for the Android client (feature 044).
 *
 * Every server->client WS frame type in the committed UI-protocol manifest
 * (`backend/shared/ui_protocol.json`) is classified as either [HANDLED] (the
 * reducer consumes it) or [IGNORED] (a deliberate, logged drop recorded in the
 * parity matrix). There is no third state: `ProtocolManifestTest` asserts this
 * table covers the manifest exactly, so a new server frame type fails the build
 * until it is classified — never a silent drop (FR-001/FR-002/FR-023).
 */
object ProtocolManifest {
    const val HANDLED = "handled"
    const val IGNORED = "ignored"

    val classification: Map<String, String> =
        mapOf(
            // bootstrap
            "rote_config" to IGNORED, // natives are full-capability; profile unused
            "chrome_menu" to HANDLED,
            "user_preferences" to HANDLED, // theme boot (044)
            "system_config" to IGNORED, // web dashboard payload; app uses agent_list
            "agent_list" to HANDLED,
            "agent_registered" to IGNORED,
            // auth
            "auth_required" to HANDLED,
            // canvas / SDUI
            "ui_render" to HANDLED,
            "ui_update" to IGNORED, // legacy frame; server no longer targets natives
            "ui_upsert" to HANDLED,
            "ui_append" to IGNORED, // legacy frame
            "ui_stream_data" to HANDLED,
            // chrome
            "chrome_render" to IGNORED, // web HTML region push; native gets chrome_surface
            "chrome_surface" to HANDLED,
            // chat lifecycle / progress
            "chat_status" to HANDLED,
            "chat_step" to HANDLED,
            "chat_created" to HANDLED,
            "chat_loaded" to HANDLED,
            "chat_deleted" to IGNORED, // cross-tab concern; app is single-window
            "history_list" to HANDLED,
            "user_message_acked" to HANDLED,
            "task_started" to HANDLED,
            "task_completed" to HANDLED,
            "tool_progress" to HANDLED,
            "workspace_timeline_mode" to HANDLED,
            "heartbeat" to IGNORED, // transport keepalive
            // streaming
            "stream_subscribed" to HANDLED,
            "stream_unsubscribed" to HANDLED,
            "stream_list" to IGNORED, // no app surface enumerates streams
            "stream_data" to HANDLED,
            "stream_error" to HANDLED,
            // workspace component verbs (web workspace acks; app canvas is ui_* driven)
            "component_saved" to IGNORED,
            "component_save_error" to IGNORED,
            "saved_components_list" to IGNORED,
            "component_deleted" to IGNORED,
            "combine_status" to IGNORED,
            "combine_error" to IGNORED,
            "components_combined" to IGNORED,
            "components_condensed" to IGNORED,
            // permissions (capability lives in the native Agents screen)
            "agent_permissions" to IGNORED,
            "agent_permissions_updated" to IGNORED,
            // llm (app uses the LLM settings surface round-trip)
            "llm_config_ack" to IGNORED,
            "llm_usage_report" to IGNORED,
            // audit (app fetches audit via REST)
            "audit_append" to IGNORED,
            // creation (draft cards carry state in-chat)
            "agent_creation_progress" to IGNORED,
            // scheduler notifications + errors (044)
            "notification" to HANDLED,
            "error" to HANDLED,
        )

    fun isHandled(frameType: String): Boolean = classification[frameType] == HANDLED

    fun isClassified(frameType: String): Boolean = frameType in classification
}
