package com.personalailabs.astraldeep.core.sdui

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotSame
import kotlin.test.assertSame

private fun comp(s: String) = Component.fromJson(Json.parseToJsonElement(s).jsonObject)

/**
 * Guards the Compose-skipping precondition (feature 052, SC-009): `Canvas.apply`
 * must return the SAME instances for components an op batch did not touch, so
 * stability-annotated composables can skip recomposing them. Only the upserted
 * id may get a new instance, and order must be preserved throughout.
 */
class CanvasIdentityTest {
    private val a = comp("""{"type":"text","component_id":"a"}""")
    private val b = comp("""{"type":"card","component_id":"b"}""")
    private val c = comp("""{"type":"alert","component_id":"c"}""")

    @Test
    fun upsert_keeps_reference_identity_of_untouched_components() {
        val replacement = comp("""{"type":"table","component_id":"b"}""")
        val out = Canvas.apply(listOf(a, b, c), listOf(CanvasOp("upsert", "b", replacement)))
        assertEquals(listOf("a", "b", "c"), out.map { it.id })
        assertSame(a, out[0])
        assertSame(replacement, out[1])
        assertNotSame(b, out[1])
        assertSame(c, out[2])
    }

    @Test
    fun append_keeps_reference_identity_of_existing_components() {
        val fresh = comp("""{"type":"chart","component_id":"d"}""")
        val out = Canvas.apply(listOf(a, b), listOf(CanvasOp("upsert", "d", fresh)))
        assertEquals(listOf("a", "b", "d"), out.map { it.id })
        assertSame(a, out[0])
        assertSame(b, out[1])
        assertSame(fresh, out[2])
    }

    @Test
    fun remove_keeps_reference_identity_of_survivors() {
        val out = Canvas.apply(listOf(a, b, c), listOf(CanvasOp("remove", "b")))
        assertEquals(listOf("a", "c"), out.map { it.id })
        assertSame(a, out[0])
        assertSame(c, out[1])
    }

    @Test
    fun mixed_batch_only_replaces_the_targeted_id() {
        val replacement = comp("""{"type":"badge","component_id":"c"}""")
        val out =
            Canvas.apply(
                listOf(a, b, c),
                listOf(CanvasOp("remove", "a"), CanvasOp("upsert", "c", replacement)),
            )
        assertEquals(listOf("b", "c"), out.map { it.id })
        assertSame(b, out[0])
        assertSame(replacement, out[1])
    }

    @Test
    fun empty_op_batch_returns_the_same_instances_in_order() {
        val out = Canvas.apply(listOf(a, b, c), emptyList())
        assertEquals(3, out.size)
        assertSame(a, out[0])
        assertSame(b, out[1])
        assertSame(c, out[2])
    }
}
