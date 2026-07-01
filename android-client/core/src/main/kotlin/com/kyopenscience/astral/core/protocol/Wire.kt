package com.kyopenscience.astral.core.protocol

import com.kyopenscience.astral.core.sdui.CanvasOp
import com.kyopenscience.astral.core.sdui.Component
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.add
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject

/**
 * The wire codec. Tolerant decode (ignore-unknown-keys / lenient) of inbound
 * frames into [Inbound] variants, and encoders for the outbound frames
 * (`register_ui`, `ui_event` + helpers). Pure — no Android, JVM-unit-tested.
 */
object Wire {
    private val json =
        Json {
            ignoreUnknownKeys = true
            isLenient = true
            explicitNulls = false
        }

    fun decode(raw: String): Inbound {
        val root = runCatching { json.parseToJsonElement(raw) as? JsonObject }.getOrNull()
            ?: return Inbound.Unknown("")
        return decode(root)
    }

    fun decode(root: JsonObject): Inbound =
        when (val type = root.str("type").orEmpty()) {
            "ui_render" ->
                Inbound.UiRender(
                    target = root.str("target") ?: "canvas",
                    components = Component.listFromJson(root.arr("components")),
                )
            "ui_upsert" ->
                Inbound.UiUpsert(
                    chatId = root.str("chat_id"),
                    ops = opsFromJson(root.arr("ops")),
                )
            // The modern push system and the legacy poll system share the frame shape.
            "ui_stream_data", "stream_data" ->
                Inbound.UiStreamData(
                    streamId = root.str("stream_id"),
                    sessionId = root.str("session_id"),
                    seq = root.int("seq"),
                    components = Component.listFromJson(root.arr("components")),
                    terminal = root.bool("terminal") ?: false,
                    error = errorFromJson(root.obj("error")),
                    toolName = root.str("tool_name"),
                )
            "stream_subscribed" -> Inbound.StreamSubscribed(root.str("stream_id"), root.str("tool_name"))
            "stream_error" -> {
                val payload = root.obj("payload")
                Inbound.StreamErrorMsg(
                    requestAction = root.str("request_action"),
                    sessionId = root.str("session_id"),
                    streamId = payload?.str("stream_id"),
                    toolName = payload?.str("tool_name") ?: root.str("tool_name"),
                    error = errorFromJson(payload)
                        ?: StreamError(code = root.str("error"), message = root.str("error")),
                )
            }
            "stream_unsubscribed" -> Inbound.StreamUnsubscribed(root.str("tool_name"))
            "chat_created" -> Inbound.ChatCreated(root.obj("payload")?.str("chat_id") ?: root.str("chat_id"))
            "user_message_acked" ->
                Inbound.UserMessageAcked(
                    chatId = root.obj("payload")?.str("chat_id") ?: root.str("chat_id"),
                    messageId = root.obj("payload")?.str("message_id") ?: root.str("message_id"),
                )
            "chat_loaded" -> Inbound.ChatLoaded(transcriptFromJson(root.obj("chat")))
            "agent_list" -> Inbound.AgentList(agentsFromJson(root.arr("agents")))
            "history_list" -> Inbound.HistoryList(chatsFromJson(root.arr("chats")))
            "chat_status" -> Inbound.ChatStatus(root.str("status"), root.str("message"))
            "chrome_render" -> Inbound.ChromeRender(root.str("region") ?: "modal", root.str("html").orEmpty())
            "auth_required" -> Inbound.AuthRequired(root.str("reason"))
            else -> Inbound.Unknown(type)
        }

    // ---- outbound encoders ----

    fun encodeRegisterUi(token: String, sessionId: String?, device: DeviceCapabilities): String =
        buildJsonObject {
            put("type", "register_ui")
            put("token", token)
            putJsonArray("capabilities") {
                add("render")
                add("stream")
            }
            put("session_id", sessionId)
            putJsonObject("device") {
                put("device_type", device.deviceType)
                put("screen_width", device.screenWidth)
                put("screen_height", device.screenHeight)
                put("viewport_width", device.viewportWidth)
                put("viewport_height", device.viewportHeight)
                put("pixel_ratio", device.pixelRatio)
                put("has_touch", device.hasTouch)
                putJsonArray("supported_types") { device.supportedTypes.forEach { add(it) } }
            }
            put("resumed", false)
        }.toString()

    fun encodeUiEvent(action: String, sessionId: String?, payload: JsonObject = JsonObject(emptyMap())): String =
        buildJsonObject {
            put("type", "ui_event")
            put("action", action)
            put("session_id", sessionId)
            put("payload", payload)
        }.toString()

    fun encodeChatMessage(
        message: String,
        chatId: String?,
        attachments: List<ChatAttachment> = emptyList(),
    ): String =
        encodeUiEvent(
            action = "chat_message",
            sessionId = chatId,
            payload =
                buildJsonObject {
                    put("message", message)
                    if (chatId != null) put("chat_id", chatId)
                    if (attachments.isNotEmpty()) {
                        putJsonArray("attachments") {
                            attachments.forEach { a ->
                                add(
                                    buildJsonObject {
                                        put("attachment_id", a.attachmentId)
                                        put("filename", a.filename)
                                        put("category", a.category)
                                    },
                                )
                            }
                        }
                    }
                },
        )

    // ---- helpers ----

    private fun JsonObject.str(key: String): String? = (this[key] as? JsonPrimitive)?.contentOrNull
    private fun JsonObject.int(key: String): Int? = (this[key] as? JsonPrimitive)?.intOrNull
    private fun JsonObject.bool(key: String): Boolean? = (this[key] as? JsonPrimitive)?.booleanOrNull
    private fun JsonObject.arr(key: String): JsonArray? = this[key] as? JsonArray
    private fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject

    private fun JsonObject.boolMap(key: String): Map<String, Boolean> =
        (this[key] as? JsonObject)?.entries
            ?.associate { (k, v) -> k to ((v as? JsonPrimitive)?.booleanOrNull ?: false) } ?: emptyMap()

    private fun JsonObject.strMap(key: String): Map<String, String> =
        (this[key] as? JsonObject)?.entries
            ?.associate { (k, v) -> k to ((v as? JsonPrimitive)?.contentOrNull ?: "") } ?: emptyMap()

    private fun JsonObject.strList(key: String): List<String> =
        (this[key] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull } ?: emptyList()

    private fun opsFromJson(arr: JsonArray?): List<CanvasOp> =
        arr?.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val cid = o.str("component_id") ?: return@mapNotNull null
            CanvasOp(
                op = o.str("op") ?: "upsert",
                componentId = cid,
                component = o.obj("component")?.let { Component.fromJson(it) },
            )
        } ?: emptyList()

    private fun errorFromJson(o: JsonObject?): StreamError? =
        o?.let {
            StreamError(
                code = it.str("code"),
                message = it.str("message"),
                retryable = it.bool("retryable") ?: false,
                phase = it.str("phase"),
            )
        }

    private fun agentsFromJson(arr: JsonArray?): List<Agent> =
        arr?.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.str("id") ?: return@mapNotNull null
            val permissions = o.boolMap("permissions")
            // `tools` is a list of {name, description} (send_agent_list) OR plain
            // strings (dashboard); fall back to the permission keys.
            val toolObjs = (o["tools"] as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()
            val tools: List<String>
            val toolDescriptions: Map<String, String>
            if (toolObjs.isNotEmpty()) {
                tools = toolObjs.mapNotNull { it.str("name") }
                toolDescriptions =
                    toolObjs.mapNotNull { t -> t.str("name")?.let { it to t.str("description").orEmpty() } }.toMap()
            } else {
                tools = o.strList("tools").ifEmpty { permissions.keys.toList() }
                toolDescriptions = o.strMap("tool_descriptions")
            }
            Agent(
                id = id,
                name = o.str("name") ?: id,
                description = o.str("description").orEmpty(),
                isPublic = o.bool("is_public") ?: false,
                scopes = o.boolMap("scopes"),
                tools = tools,
                toolDescriptions = toolDescriptions,
                permissions = permissions,
                toolScopeMap = o.strMap("tool_scope_map"),
            )
        } ?: emptyList()

    private fun chatsFromJson(arr: JsonArray?): List<ChatSummary> =
        arr?.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.str("id") ?: return@mapNotNull null
            ChatSummary(id, o.str("title").orEmpty())
        } ?: emptyList()

    private fun transcriptFromJson(o: JsonObject?): ChatTranscript {
        if (o == null) return ChatTranscript(null, emptyList())
        val msgsArr = (o["messages"] as? JsonArray) ?: (o["history"] as? JsonArray)
        val msgs =
            msgsArr?.mapNotNull { el ->
                val m = el as? JsonObject ?: return@mapNotNull null
                val content = m.str("content") ?: m.str("text") ?: ""
                val role = m.str("role") ?: if (m.bool("is_user") == true) "user" else "assistant"
                ChatTurn(role, content)
            } ?: emptyList()
        return ChatTranscript(o.str("id"), msgs)
    }
}
