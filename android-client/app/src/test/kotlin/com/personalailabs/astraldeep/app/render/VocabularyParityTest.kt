package com.personalailabs.astraldeep.app.render

import com.personalailabs.astraldeep.app.render.renderers.registerAllRenderers
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Guards the advertised vocabulary (the Android twin of the Windows
 * `test_no_silent_backend_vocabulary_drift`). Since feature 044 the expected
 * set is anchored on the committed UI-protocol manifest
 * (`backend/shared/ui_protocol.json`) — the same file the backend keeps equal
 * to `webrender.allowed_primitive_types()` — so a backend vocabulary change
 * fails this test until the app either renders the new type or deliberately
 * excludes it. Pure JVM — the @Composable renderers are stored, not invoked.
 */
class VocabularyParityTest {
    /** Backend primitives deliberately NOT rendered natively on Android; ROTE
     * substitutes them server-side (sanctioned web-only per FR-026). */
    private val excluded = setOf("audio", "generative")

    private fun manifestComponentTypes(): Set<String> {
        var dir: File? = File(".").absoluteFile
        while (dir != null) {
            val candidate = File(dir, "backend/shared/ui_protocol.json")
            if (candidate.isFile) {
                val root = Json.parseToJsonElement(candidate.readText()).jsonObject
                return root.getValue("component_types").jsonArray
                    .map { it.jsonPrimitive.content }
                    .toSet()
            }
            dir = dir.parentFile
        }
        error("backend/shared/ui_protocol.json not found walking up from ${File(".").absolutePath}")
    }

    private fun renderer() = Renderer(Emit { _, _ -> }).registerAllRenderers()

    @Test
    fun registers_exactly_the_backend_vocabulary_minus_exclusions() {
        assertEquals(manifestComponentTypes() - excluded, renderer().supportedTypes)
    }

    @Test
    fun excludes_web_only_or_unimplemented_types() {
        val supported = renderer().supportedTypes
        excluded.forEach { assertTrue(it !in supported, "$it must not be advertised") }
    }

    @Test
    fun excluded_types_are_real_backend_types() {
        // Guard the guard: a stale exclusion (type no longer in the backend
        // vocabulary) should be cleaned up.
        assertTrue(excluded.all { it in manifestComponentTypes() })
    }
}
