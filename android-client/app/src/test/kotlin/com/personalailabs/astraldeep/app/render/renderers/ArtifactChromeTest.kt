package com.personalailabs.astraldeep.app.render.renderers

import com.personalailabs.astraldeep.core.sdui.Component
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Feature 055 US4/US5 (T036/T040/T045) — the pure rules behind the shared
 * per-component chrome: provenance badge mapping (server-stamped field only,
 * absent = nothing), overflow-menu derivation (Refine target + export
 * entries with their exact REST URLs), and the `component_refine` payload.
 */
class ArtifactChromeTest {
    private fun comp(json: String): Component = Component.fromJson(Json.parseToJsonElement(json) as JsonObject)

    // --- provenance badge (T036, wire-contract §6) ---------------------------

    @Test
    fun the_three_canonical_stamps_map_to_their_badges() {
        assertEquals(Provenance.Grounded, provenanceOf(comp("""{"type":"card","provenance":"grounded"}""")))
        assertEquals(Provenance.Estimated, provenanceOf(comp("""{"type":"card","provenance":"estimated"}""")))
        assertEquals(Provenance.Generated, provenanceOf(comp("""{"type":"card","provenance":"generated"}""")))
    }

    @Test
    fun web_footer_synonyms_normalize_to_the_same_marks() {
        assertEquals(Provenance.Grounded, provenanceOf(comp("""{"type":"card","provenance":"verified"}""")))
        assertEquals(Provenance.Estimated, provenanceOf(comp("""{"type":"card","provenance":"low_confidence"}""")))
        assertEquals(Provenance.Generated, provenanceOf(comp("""{"type":"card","provenance":"AI"}""")))
    }

    @Test
    fun absent_blank_or_unknown_values_render_nothing() {
        assertNull(provenanceOf(comp("""{"type":"card"}""")))
        assertNull(provenanceOf(comp("""{"type":"card","provenance":"  "}""")))
        assertNull(provenanceOf(comp("""{"type":"card","provenance":"gospel"}""")))
    }

    @Test
    fun decorative_types_are_never_badged_even_when_stamped() {
        assertNull(provenanceOf(comp("""{"type":"divider","provenance":"grounded"}""")))
        assertNull(provenanceOf(comp("""{"type":"skeleton","provenance":"generated"}""")))
    }

    // --- overflow menu (T040/T045, contracts/rest-endpoints.md) --------------

    private val table = """{"type":"table","component_id":"wc_abc","title":"Q3 Sales","headers":["a"],"rows":[["1"]]}"""

    @Test
    fun a_table_with_identity_and_chat_gets_refine_and_both_exports() {
        val m = artifactMenu(comp(table), chatId = "chat-1", mutationsLocked = false)
        assertEquals("wc_abc", m.refineComponentId)
        assertEquals(
            listOf(
                "/api/export/component/wc_abc.csv?chat_id=chat-1",
                "/api/export/canvas/chat-1.html",
            ),
            m.exports.map { it.url },
        )
        assertEquals(listOf("Export table (CSV)", "Export canvas (HTML)"), m.exports.map { it.label })
    }

    @Test
    fun csv_export_is_table_only_but_canvas_export_stays() {
        val m = artifactMenu(comp("""{"type":"card","component_id":"wc_x"}"""), "chat-1", mutationsLocked = false)
        assertEquals(listOf("/api/export/canvas/chat-1.html"), m.exports.map { it.url })
    }

    @Test
    fun no_chat_id_means_no_exports() {
        assertTrue(artifactMenu(comp(table), chatId = null, mutationsLocked = false).exports.isEmpty())
        assertTrue(artifactMenu(comp(table), chatId = " ", mutationsLocked = false).exports.isEmpty())
    }

    @Test
    fun a_read_only_view_hides_refine_but_keeps_exports() {
        val m = artifactMenu(comp(table), "chat-1", mutationsLocked = true)
        assertNull(m.refineComponentId)
        assertEquals(2, m.exports.size)
    }

    @Test
    fun no_identity_means_no_refine_and_no_csv() {
        val m = artifactMenu(comp("""{"type":"table","headers":[],"rows":[]}"""), "chat-1", mutationsLocked = false)
        assertNull(m.refineComponentId)
        assertEquals(listOf("Export canvas (HTML)"), m.exports.map { it.label })
    }

    @Test
    fun the_menu_is_empty_without_identity_or_chat() {
        assertTrue(artifactMenu(comp("""{"type":"card"}"""), chatId = null, mutationsLocked = false).isEmpty)
    }

    @Test
    fun ids_are_url_encoded_into_both_routes() {
        val m = artifactMenu(comp("""{"type":"table","component_id":"wc a/b"}"""), "chat 1/x", mutationsLocked = false)
        assertEquals(
            listOf(
                "/api/export/component/wc+a%2Fb.csv?chat_id=chat+1%2Fx",
                "/api/export/canvas/chat+1%2Fx.html",
            ),
            m.exports.map { it.url },
        )
    }

    @Test
    fun export_filenames_prefer_the_title_and_are_sanitized() {
        val m = artifactMenu(comp(table), "chat-1", mutationsLocked = false)
        assertEquals("Q3 Sales.csv", m.exports[0].filename)
        assertEquals("canvas-chat-1.html", m.exports[1].filename)
        assertEquals("a_b_c.csv", exportFilename("a/b\\c", "csv"))
        assertEquals("export.html", exportFilename("   ", "html"))
    }

    // --- refine payload (T040, wire-contract §3) ------------------------------

    @Test
    fun refine_payload_carries_identity_and_trimmed_instruction() {
        val p = refinePayload("wc_abc", "  make it a bar chart  ")
        assertEquals("wc_abc", (p["component_id"] as JsonPrimitive).content)
        assertEquals("make it a bar chart", (p["instruction"] as JsonPrimitive).content)
    }
}
