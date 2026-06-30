package com.kyopenscience.astral.core.protocol

import com.kyopenscience.astral.core.sdui.CanvasOp
import com.kyopenscience.astral.core.sdui.Component

/**
 * Device capabilities reported in `register_ui` (maps to the server-side
 * `DeviceProfile`, `backend/rote/capabilities.py`). `supportedTypes` is the
 * client's capability negotiation — ROTE substitutes any primitive outside it.
 */
data class DeviceCapabilities(
    val screenWidth: Int,
    val screenHeight: Int,
    val viewportWidth: Int = screenWidth,
    val viewportHeight: Int = screenHeight,
    val pixelRatio: Double = 1.0,
    val hasTouch: Boolean = true,
    val supportedTypes: List<String> = emptyList(),
    val deviceType: String = "android",
)

/** A streaming error, as carried in a `ui_stream_data.error` or a `stream_error` payload. */
data class StreamError(
    val code: String?,
    val message: String?,
    val retryable: Boolean = false,
    val phase: String? = null,
)

data class Agent(
    val id: String,
    val name: String,
    val description: String,
    val isPublic: Boolean,
    val scopes: Map<String, Boolean>,
    val tools: List<String> = emptyList(),
    val toolDescriptions: Map<String, String> = emptyMap(),
    /** Effective per-tool enabled state (server-computed from scopes + overrides). */
    val permissions: Map<String, Boolean> = emptyMap(),
    /** Each tool's required permission kind (e.g. "tools:read"), for toggling. */
    val toolScopeMap: Map<String, String> = emptyMap(),
)

data class ChatSummary(val id: String, val title: String)

data class ChatTurn(val role: String, val content: String)

data class ChatTranscript(val id: String?, val messages: List<ChatTurn>)

/**
 * Inbound server → client messages the client acts on, plus an [Unknown]
 * fallback so an unrecognized `type` is ignored rather than fatal.
 */
sealed interface Inbound {
    data class UiRender(val target: String, val components: List<Component>) : Inbound

    data class UiUpsert(val chatId: String?, val ops: List<CanvasOp>) : Inbound

    data class UiStreamData(
        val streamId: String?,
        val sessionId: String?,
        val seq: Int?,
        val components: List<Component>,
        val terminal: Boolean,
        val error: StreamError?,
        val toolName: String?,
    ) : Inbound

    data class StreamSubscribed(val streamId: String?, val toolName: String?) : Inbound

    data class StreamErrorMsg(
        val requestAction: String?,
        val sessionId: String?,
        val streamId: String?,
        val toolName: String?,
        val error: StreamError,
    ) : Inbound

    data class StreamUnsubscribed(val toolName: String?) : Inbound

    data class ChatCreated(val chatId: String?) : Inbound

    data class ChatLoaded(val chat: ChatTranscript) : Inbound

    data class AgentList(val agents: List<Agent>) : Inbound

    data class HistoryList(val chats: List<ChatSummary>) : Inbound

    data class ChatStatus(val status: String?, val message: String?) : Inbound

    data class ChromeRender(val region: String, val html: String) : Inbound

    data class AuthRequired(val reason: String?) : Inbound

    data class Unknown(val type: String) : Inbound
}
