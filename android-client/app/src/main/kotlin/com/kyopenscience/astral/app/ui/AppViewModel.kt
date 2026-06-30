package com.kyopenscience.astral.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.kyopenscience.astral.app.transport.ConnectionState
import com.kyopenscience.astral.app.transport.OrchestratorClient
import com.kyopenscience.astral.core.protocol.DeviceCapabilities
import com.kyopenscience.astral.core.protocol.Inbound
import com.kyopenscience.astral.core.sdui.Canvas
import com.kyopenscience.astral.core.sdui.Component
import com.kyopenscience.astral.core.streaming.streamErrorOps
import com.kyopenscience.astral.core.streaming.streamFrameToOps
import com.kyopenscience.astral.core.streaming.subscribeAckOps
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

data class ChatTurn(val role: String, val text: String)

data class UiState(
    val connection: ConnectionState = ConnectionState.Disconnected,
    val activeChatId: String? = null,
    val turns: List<ChatTurn> = emptyList(),
    val canvas: List<Component> = emptyList(),
    val statusText: String? = null,
)

/**
 * Owns the connection + derived UI state. Collects the transport's inbound flow
 * and folds each [Inbound] into [state]; sends chat/events out. The bearer token
 * is supplied by [start] (US1 wires real OIDC); the ViewModel is auth-agnostic.
 *
 * Streaming (`ui_stream_data`) and the management surfaces (agents/history/audit)
 * are folded in by their own stories (US2/US4); foundational handles chat + canvas.
 */
class AppViewModel(private val client: OrchestratorClient) : ViewModel() {
    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state.asStateFlow()

    private var session: Job? = null
    private val seqState = mutableMapOf<String, Int>()

    /** Begin (or restart) the session with a bearer token + device caps. */
    fun start(token: String, device: DeviceCapabilities) {
        session?.cancel()
        seqState.clear()
        session =
            viewModelScope.launch {
                launch {
                    client.stream(token, device, _state.value.activeChatId).collect { msg ->
                        _state.value = reduce(_state.value, msg)
                    }
                }
                launch {
                    client.state.collect { c -> _state.value = _state.value.copy(connection = c) }
                }
            }
    }

    fun sendChat(text: String) {
        if (text.isBlank()) return
        _state.value = _state.value.copy(turns = _state.value.turns + ChatTurn("user", text))
        client.sendChat(text, _state.value.activeChatId)
    }

    fun sendEvent(action: String, payload: JsonObject) {
        client.sendEvent(action, _state.value.activeChatId, payload)
    }

    private fun reduce(s: UiState, msg: Inbound): UiState =
        when (msg) {
            is Inbound.UiRender ->
                if (msg.target == "chat") {
                    val text = flattenText(msg.components)
                    if (text.isBlank()) s else s.copy(turns = s.turns + ChatTurn("assistant", text))
                } else {
                    s.copy(canvas = msg.components)
                }
            is Inbound.UiUpsert ->
                if (msg.chatId == null || msg.chatId == s.activeChatId) {
                    s.copy(canvas = Canvas.apply(s.canvas, msg.ops))
                } else {
                    s
                }
            is Inbound.ChatCreated -> s.copy(activeChatId = msg.chatId ?: s.activeChatId)
            is Inbound.ChatLoaded ->
                s.copy(
                    activeChatId = msg.chat.id ?: s.activeChatId,
                    turns = msg.chat.messages.map { ChatTurn(it.role, it.content) },
                )
            is Inbound.ChatStatus -> s.copy(statusText = msg.message ?: msg.status)
            is Inbound.UiStreamData ->
                s.copy(canvas = Canvas.apply(s.canvas, streamFrameToOps(msg, s.activeChatId, seqState)))
            is Inbound.StreamSubscribed ->
                s.copy(canvas = Canvas.apply(s.canvas, subscribeAckOps(msg)))
            is Inbound.StreamErrorMsg ->
                s.copy(canvas = Canvas.apply(s.canvas, streamErrorOps(msg)))
            else -> s
        }

    private fun flattenText(components: List<Component>): String =
        components.joinToString("\n") { c ->
            val own =
                (c.attributes["content"] as? JsonPrimitive)?.contentOrNull
                    ?: (c.attributes["text"] as? JsonPrimitive)?.contentOrNull
                    ?: ""
            (own + "\n" + flattenText(c.children)).trim()
        }.trim()

    companion object {
        fun factory(client: OrchestratorClient) =
            viewModelFactory {
                initializer { AppViewModel(client) }
            }
    }
}
