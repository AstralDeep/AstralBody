package com.kyopenscience.astral.core.protocol

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

class WireTest {
    @Test
    fun decodes_ui_render() {
        val r =
            assertIs<Inbound.UiRender>(
                Wire.decode("""{"type":"ui_render","target":"canvas","components":[{"type":"text","component_id":"c1","content":"hi"}]}"""),
            )
        assertEquals("canvas", r.target)
        assertEquals(1, r.components.size)
        assertEquals("text", r.components[0].type)
        assertEquals("c1", r.components[0].id)
    }

    @Test
    fun decodes_ui_upsert_ops() {
        val r =
            assertIs<Inbound.UiUpsert>(
                Wire.decode(
                    """{"type":"ui_upsert","chat_id":"chatA","ops":[{"op":"upsert","component_id":"c1","component":{"type":"card"}},{"op":"remove","component_id":"c2"}]}""",
                ),
            )
        assertEquals("chatA", r.chatId)
        assertEquals(2, r.ops.size)
        assertEquals("upsert", r.ops[0].op)
        assertEquals("card", r.ops[0].component?.type)
        assertEquals("remove", r.ops[1].op)
    }

    @Test
    fun decodes_ui_stream_data() {
        val r =
            assertIs<Inbound.UiStreamData>(
                Wire.decode("""{"type":"ui_stream_data","stream_id":"s1","session_id":"chatA","seq":3,"components":[{"type":"text"}],"terminal":false}"""),
            )
        assertEquals("s1", r.streamId)
        assertEquals(3, r.seq)
        assertEquals(false, r.terminal)
        assertEquals(1, r.components.size)
    }

    @Test
    fun decodes_stream_error_push_shape() {
        val r =
            assertIs<Inbound.StreamErrorMsg>(
                Wire.decode("""{"type":"stream_error","request_action":"stream_subscribe","session_id":"chatA","payload":{"stream_id":"s1","code":"blocked","message":"no"}}"""),
            )
        assertEquals("s1", r.streamId)
        assertEquals("blocked", r.error.code)
        assertEquals("no", r.error.message)
    }

    @Test
    fun decodes_agent_list_with_scopes() {
        val r =
            assertIs<Inbound.AgentList>(
                Wire.decode("""{"type":"agent_list","agents":[{"id":"a1","name":"Weather","description":"d","is_public":true,"scopes":{"tools:read":true,"tools:write":false}}]}"""),
            )
        assertEquals(1, r.agents.size)
        assertTrue(r.agents[0].isPublic)
        assertEquals(true, r.agents[0].scopes["tools:read"])
        assertEquals(false, r.agents[0].scopes["tools:write"])
    }

    @Test
    fun decodes_chat_loaded_transcript() {
        val r =
            assertIs<Inbound.ChatLoaded>(
                Wire.decode("""{"type":"chat_loaded","chat":{"id":"chatA","messages":[{"role":"user","content":"hey"}]}}"""),
            )
        assertEquals("chatA", r.chat.id)
        assertEquals("user", r.chat.messages[0].role)
        assertEquals("hey", r.chat.messages[0].content)
    }

    @Test
    fun decodes_chrome_render_and_auth_required() {
        assertIs<Inbound.ChromeRender>(Wire.decode("""{"type":"chrome_render","region":"modal","html":"<div/>"}"""))
        assertIs<Inbound.AuthRequired>(Wire.decode("""{"type":"auth_required","reason":"x"}"""))
    }

    @Test
    fun unknown_type_falls_back() {
        val r = assertIs<Inbound.Unknown>(Wire.decode("""{"type":"totally_new_primitive"}"""))
        assertEquals("totally_new_primitive", r.type)
    }

    @Test
    fun malformed_json_is_unknown_not_throw() {
        assertIs<Inbound.Unknown>(Wire.decode("{not valid json"))
    }

    @Test
    fun encodes_register_ui_with_device_caps() {
        val out =
            Wire.encodeRegisterUi(
                token = "TOK",
                sessionId = "chatA",
                device = DeviceCapabilities(screenWidth = 1080, screenHeight = 2340, supportedTypes = listOf("text", "card")),
            )
        val o = Json.parseToJsonElement(out).jsonObject
        assertEquals("register_ui", o["type"]?.jsonPrimitive?.contentOrNull)
        assertEquals("TOK", o["token"]?.jsonPrimitive?.contentOrNull)
        val dev = o["device"]!!.jsonObject
        assertEquals("android", dev["device_type"]?.jsonPrimitive?.contentOrNull)
        assertEquals("1080", dev["screen_width"]?.jsonPrimitive?.contentOrNull)
        assertEquals(2, dev["supported_types"]!!.jsonArray.size)
    }

    @Test
    fun encodes_chat_message() {
        val o = Json.parseToJsonElement(Wire.encodeChatMessage("hello", "chatA")).jsonObject
        assertEquals("ui_event", o["type"]?.jsonPrimitive?.contentOrNull)
        assertEquals("chat_message", o["action"]?.jsonPrimitive?.contentOrNull)
        assertEquals("hello", o["payload"]!!.jsonObject["message"]?.jsonPrimitive?.contentOrNull)
        assertEquals("chatA", o["payload"]!!.jsonObject["chat_id"]?.jsonPrimitive?.contentOrNull)
    }
}
