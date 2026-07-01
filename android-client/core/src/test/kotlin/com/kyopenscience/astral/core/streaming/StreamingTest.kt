package com.kyopenscience.astral.core.streaming

import com.kyopenscience.astral.core.protocol.Inbound
import com.kyopenscience.astral.core.protocol.StreamError
import com.kyopenscience.astral.core.sdui.Component
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

private fun comp(type: String): Component = Component(type, null, Json.parseToJsonElement("""{"type":"$type"}""").jsonObject, emptyList())

private fun frame(
    streamId: String? = "s1",
    sessionId: String? = null,
    seq: Int? = 1,
    components: List<Component> = listOf(comp("text")),
    terminal: Boolean = false,
    error: StreamError? = null,
    toolName: String? = null,
) = Inbound.UiStreamData(streamId, sessionId, seq, components, terminal, error, toolName)

class StreamingTest {
    @Test
    fun renders_components_in_place_keyed_by_stream() {
        val seq = mutableMapOf<String, Int>()
        val ops = streamFrameToOps(frame(components = listOf(comp("text"))), activeChat = null, seqState = seq)
        assertEquals(1, ops.size)
        assertEquals(streamNodeId("s1"), ops[0].componentId)
        assertEquals(streamNodeId("s1"), ops[0].component?.id) // stable node key for in-place updates
        assertEquals(1, seq["s1"])
    }

    @Test
    fun multiple_components_wrapped_in_container() {
        val ops = streamFrameToOps(frame(components = listOf(comp("text"), comp("card"))), null, mutableMapOf())
        assertEquals("container", ops[0].component?.type)
        assertEquals(2, ops[0].component?.children?.size)
    }

    @Test
    fun seq_dedupe_drops_stale_and_equal_keeps_newer() {
        val seq = mutableMapOf("s1" to 5)
        assertTrue(streamFrameToOps(frame(seq = 5), null, seq).isEmpty())
        assertTrue(streamFrameToOps(frame(seq = 4), null, seq).isEmpty())
        assertTrue(streamFrameToOps(frame(seq = 6), null, seq).isNotEmpty())
        assertEquals(6, seq["s1"])
    }

    @Test
    fun session_filter_drops_foreign_chat_keeps_match() {
        assertTrue(streamFrameToOps(frame(sessionId = "chatB"), "chatA", mutableMapOf()).isEmpty())
        assertTrue(streamFrameToOps(frame(sessionId = "chatA"), "chatA", mutableMapOf()).isNotEmpty())
    }

    @Test
    fun error_frame_renders_alert() {
        val ops = streamFrameToOps(frame(error = StreamError("tool_error", "boom", retryable = true)), null, mutableMapOf())
        assertEquals("alert", ops[0].component?.type)
    }

    @Test
    fun terminal_with_payload_renders_then_forgets_stream() {
        val seq = mutableMapOf("s1" to 1)
        val ops = streamFrameToOps(frame(seq = 2, terminal = true, components = listOf(comp("text"))), null, seq)
        assertTrue(ops.isNotEmpty())
        assertTrue("s1" !in seq)
    }

    @Test
    fun bare_terminal_frame_yields_no_ops_but_forgets() {
        val seq = mutableMapOf("s1" to 1)
        assertTrue(streamFrameToOps(frame(seq = 2, terminal = true, components = emptyList()), null, seq).isEmpty())
        assertTrue("s1" !in seq)
    }

    @Test
    fun unaddressable_frame_dropped() {
        assertTrue(streamFrameToOps(frame(streamId = null, toolName = null), null, mutableMapOf()).isEmpty())
    }

    @Test
    fun legacy_poll_frame_keyed_by_tool() {
        val ops = streamFrameToOps(frame(streamId = null, seq = null, toolName = "ticker"), null, mutableMapOf())
        assertEquals("stream-tool-ticker", ops[0].componentId)
    }

    @Test
    fun subscribe_ack_placeholder_for_node() {
        val ops = subscribeAckOps(Inbound.StreamSubscribed("s1", "ticker"))
        assertEquals(streamNodeId("s1"), ops[0].componentId)
    }

    @Test
    fun stream_error_control_targets_node() {
        val ops = streamErrorOps(Inbound.StreamErrorMsg("stream_subscribe", "chatA", "s1", null, StreamError("blocked", "no")))
        assertEquals(streamNodeId("s1"), ops[0].componentId)
        assertEquals("alert", ops[0].component?.type)
    }
}
