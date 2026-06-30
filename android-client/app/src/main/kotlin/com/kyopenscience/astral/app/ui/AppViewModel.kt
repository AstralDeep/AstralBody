package com.kyopenscience.astral.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.kyopenscience.astral.app.rest.AstralRest
import com.kyopenscience.astral.app.rest.AuditEvent
import com.kyopenscience.astral.app.transport.ConnectionState
import com.kyopenscience.astral.app.transport.OrchestratorClient
import com.kyopenscience.astral.core.protocol.Agent
import com.kyopenscience.astral.core.protocol.ChatSummary
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
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject

data class ChatTurn(val role: String, val text: String)

/** The top-level navigable surfaces (US4). */
enum class Screen { Chat, Agents, History, Audit }

data class UiState(
    val connection: ConnectionState = ConnectionState.Disconnected,
    val screen: Screen = Screen.Chat,
    val activeChatId: String? = null,
    val turns: List<ChatTurn> = emptyList(),
    val canvas: List<Component> = emptyList(),
    val statusText: String? = null,
    val agents: List<Agent> = emptyList(),
    val history: List<ChatSummary> = emptyList(),
    val audit: List<AuditEvent> = emptyList(),
)

/**
 * Owns the connection + derived UI state. Folds each [Inbound] into [state] and
 * sends chat/events out; the management surfaces (agents/history) ride the
 * existing WS data actions, and audit reads `GET /api/audit` via [rest]. The
 * bearer token from [start] authorizes both.
 */
class AppViewModel(
    private val client: OrchestratorClient,
    private val rest: AstralRest,
) : ViewModel() {
    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state.asStateFlow()

    private var session: Job? = null
    private var token: String? = null
    private val seqState = mutableMapOf<String, Int>()

    /** Begin (or restart) the session with a bearer token + device caps. */
    fun start(token: String, device: DeviceCapabilities) {
        this.token = token
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

    fun sendEvent(action: String, payload: JsonObject = JsonObject(emptyMap())) {
        client.sendEvent(action, _state.value.activeChatId, payload)
    }

    // --- US4 surfaces -------------------------------------------------------

    /** Switch surface and lazily fetch its data. */
    fun goTo(screen: Screen) {
        _state.value = _state.value.copy(screen = screen)
        when (screen) {
            Screen.Agents -> sendEvent("discover_agents")
            Screen.History -> sendEvent("get_history")
            Screen.Audit -> loadAudit()
            Screen.Chat -> Unit
        }
    }

    fun openChat(chatId: String) {
        sendEvent("load_chat", buildJsonObject { put("chat_id", chatId) })
        _state.value = _state.value.copy(screen = Screen.Chat)
    }

    /** Enable/disable a single tool of an agent (REST per-(tool,kind) write), then refresh. */
    fun setToolEnabled(agent: Agent, tool: String, enabled: Boolean) {
        val t = token ?: return
        val kind = agent.toolScopeMap[tool] ?: "tools:read"
        viewModelScope.launch {
            runCatching { rest.setToolPermission(t, agent.id, tool, kind, enabled) }
            sendEvent("discover_agents")
        }
    }

    /** Master toggle: enable/disable all of an agent's tools at once (WS scopes + overrides). */
    fun setAgentEnabled(agent: Agent, enabled: Boolean) {
        val kinds = agent.toolScopeMap.values.toSet().ifEmpty { agent.scopes.keys }
        sendEvent(
            "set_agent_permissions",
            buildJsonObject {
                put("agent_id", agent.id)
                putJsonObject("scopes") { kinds.forEach { put(it, enabled) } }
                putJsonObject("tool_overrides") { agent.tools.forEach { put(it, enabled) } }
            },
        )
        sendEvent("discover_agents")
    }

    fun enableRecommended() {
        sendEvent("enable_recommended_agents")
        sendEvent("discover_agents")
    }

    private fun loadAudit() {
        val t = token ?: return
        viewModelScope.launch {
            val events = runCatching { rest.audit(t) }.getOrDefault(emptyList())
            _state.value = _state.value.copy(audit = events)
        }
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
            is Inbound.AgentList -> s.copy(agents = msg.agents)
            is Inbound.HistoryList -> s.copy(history = msg.chats)
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
        fun factory(client: OrchestratorClient, rest: AstralRest) =
            viewModelFactory {
                initializer { AppViewModel(client, rest) }
            }
    }
}
