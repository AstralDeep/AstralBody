package com.kyopenscience.astral.core.sdui

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

private fun obj(s: String) = Json.parseToJsonElement(s).jsonObject

private fun comp(s: String) = Component.fromJson(obj(s))

class ComponentTest {
    @Test
    fun identity_prefers_component_id_then_id_then_null() {
        assertEquals("wc1", comp("""{"type":"card","component_id":"wc1","id":"other"}""").id)
        assertEquals("only", comp("""{"type":"card","id":"only"}""").id)
        assertNull(comp("""{"type":"card"}""").id)
    }

    @Test
    fun decodes_children_from_content_and_children() {
        val fromContent = comp("""{"type":"card","content":[{"type":"text"},{"type":"button"}]}""")
        assertEquals(listOf("text", "button"), fromContent.children.map { it.type })
        val fromChildren = comp("""{"type":"container","children":[{"type":"alert"}]}""")
        assertEquals(listOf("alert"), fromChildren.children.map { it.type })
    }

    @Test
    fun attributes_keep_the_raw_object() {
        val c = comp("""{"type":"alert","variant":"error","message":"boom"}""")
        assertEquals("error", c.attributes["variant"]?.jsonPrimitive?.contentOrNull)
        assertEquals("boom", c.attributes["message"]?.jsonPrimitive?.contentOrNull)
    }

    @Test
    fun canvas_upsert_appends_then_replaces_in_place() {
        val start = listOf(comp("""{"type":"text","component_id":"a"}"""))
        val afterAdd =
            Canvas.apply(
                start,
                listOf(CanvasOp("upsert", "b", comp("""{"type":"card","component_id":"b"}"""))),
            )
        assertEquals(listOf("a", "b"), afterAdd.map { it.id })

        val replaced =
            Canvas.apply(
                afterAdd,
                listOf(CanvasOp("upsert", "a", comp("""{"type":"alert","component_id":"a"}"""))),
            )
        assertEquals("alert", replaced.first { it.id == "a" }.type)
        assertEquals(listOf("a", "b"), replaced.map { it.id }) // position preserved
    }

    @Test
    fun canvas_remove_drops_by_id() {
        val start =
            Canvas.apply(
                emptyList(),
                listOf(
                    CanvasOp("upsert", "a", comp("""{"type":"text","component_id":"a"}""")),
                    CanvasOp("upsert", "b", comp("""{"type":"text","component_id":"b"}""")),
                ),
            )
        val afterRemove = Canvas.apply(start, listOf(CanvasOp("remove", "a")))
        assertEquals(listOf("b"), afterRemove.map { it.id })
    }

    @Test
    fun canvas_upsert_without_component_is_ignored() {
        val start = listOf(comp("""{"type":"text","component_id":"a"}"""))
        val out = Canvas.apply(start, listOf(CanvasOp("upsert", "b", component = null)))
        assertEquals(listOf("a"), out.map { it.id })
    }
}
