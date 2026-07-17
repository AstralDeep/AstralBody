package com.personalailabs.astraldeep.app.render.renderers

import com.personalailabs.astraldeep.app.render.Emit
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/** The primitive may emit work on Done, but Compose retains native IME dismissal. */
class InputImeActionTest {
    @Test
    fun done_emits_the_action_before_invoking_the_native_keyboard_action() {
        val calls = mutableListOf<String>()
        val emit =
            Emit { action, payload ->
                calls += "$action:${payload.getValue("value").jsonPrimitive.content}"
            }

        dispatchInputDone("search", "native dismissal", emit) { calls += "native_done" }

        assertEquals(listOf("search:native dismissal", "native_done"), calls)
    }

    @Test
    fun done_without_an_action_still_invokes_the_native_keyboard_action() {
        val calls = mutableListOf<String>()

        dispatchInputDone(null, "ignored", Emit { _, _ -> calls += "emit" }) {
            calls += "native_done"
        }

        assertEquals(listOf("native_done"), calls)
    }

    @Test
    fun native_keyboard_action_is_not_suppressed_when_action_emission_fails() {
        var nativeDone = false
        val failure = Emit { _, _ -> error("send failed") }

        assertFailsWith<IllegalStateException> {
            dispatchInputDone("search", "query", failure) { nativeDone = true }
        }

        assertEquals(true, nativeDone)
    }
}
