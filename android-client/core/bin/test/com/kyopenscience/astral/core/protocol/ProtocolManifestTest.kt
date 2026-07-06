package com.kyopenscience.astral.core.protocol

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * Feature 044 — Android protocol-coverage drift guard. The committed manifest
 * (`backend/shared/ui_protocol.json`) is the single source of the server->client
 * frame vocabulary; the app's classification table must cover it exactly, so a
 * new server frame type fails the build until it is deliberately classified.
 */
class ProtocolManifestTest {
    private fun manifestFile(): File {
        var dir: File? = File(".").absoluteFile
        while (dir != null) {
            val candidate = File(dir, "backend/shared/ui_protocol.json")
            if (candidate.isFile) return candidate
            dir = dir.parentFile
        }
        error("backend/shared/ui_protocol.json not found walking up from ${File(".").absolutePath}")
    }

    private fun manifestPushTypes(): Set<String> {
        val root = Json.parseToJsonElement(manifestFile().readText()).jsonObject
        return root.getValue("push_types").jsonArray
            .map { it.jsonObject.getValue("name").jsonPrimitive.content }
            .toSet()
    }

    @Test
    fun classification_covers_manifest_exactly() {
        val push = manifestPushTypes()
        val classified = ProtocolManifest.classification.keys
        val missing = (push - classified).sorted()
        val stale = (classified - push).sorted()
        assertTrue(missing.isEmpty(), "server frame types the app has not classified: $missing")
        assertTrue(stale.isEmpty(), "app classifies frame types the server no longer sends: $stale")
    }

    @Test
    fun classification_values_are_valid() {
        val allowed = setOf(ProtocolManifest.HANDLED, ProtocolManifest.IGNORED)
        assertTrue(ProtocolManifest.classification.values.all { it in allowed })
    }

    @Test
    fun core_loop_frames_are_handled() {
        listOf(
            "ui_render", "ui_upsert", "chat_status", "error", "auth_required",
            "chrome_menu", "chrome_surface", "user_message_acked", "chat_step",
            "tool_progress", "task_started", "task_completed", "notification",
            "user_preferences", "workspace_timeline_mode",
        ).forEach { frame ->
            assertTrue(ProtocolManifest.isHandled(frame), "$frame must be handled per the parity matrix")
        }
    }
}
