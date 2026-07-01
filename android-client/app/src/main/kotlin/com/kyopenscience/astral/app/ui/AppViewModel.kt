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
import com.kyopenscience.astral.core.protocol.ChatAttachment
import com.kyopenscience.astral.core.protocol.ChatSummary
import com.kyopenscience.astral.core.protocol.DeviceCapabilities
import com.kyopenscience.astral.core.protocol.Inbound
import com.kyopenscience.astral.core.sdui.Canvas
import com.kyopenscience.astral.core.sdui.CanvasOp
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

/** A paperclip-staged upload chip (feature 031). */
data class StagedAttachment(
    val uid: Long,
    val filename: String,
    val category: String,
    val attachmentId: String?,
    /** "uploading" | "ready" | "failed" */
    val state: String,
    val note: String? = null,
)

/** A read-only snapshot of a past turn's finished canvas (client-side timeline). */
data class CanvasSnapshot(val label: String, val components: List<Component>)

data class UiState(
    val connection: ConnectionState = ConnectionState.Disconnected,
    val screen: Screen = Screen.Chat,
    val activeChatId: String? = null,
    val turns: List<ChatTurn> = emptyList(),
    // --- canvas lifecycle (commit-on-done) ---
    /** The committed, live canvas — the last FINAL SDUI the orchestrator produced. */
    val canvas: List<Component> = emptyList(),
    /** Buffer built from a replacing turn's ops; shown only when the turn is done. */
    val pendingCanvas: List<Component> = emptyList(),
    /** Orchestrator is working this turn (drives the thin progress indicator). */
    val turnActive: Boolean = false,
    /** This turn will REPLACE the canvas on completion (a user chat turn). */
    val pendingReplace: Boolean = false,
    /** Label describing the current committed canvas (the prompt that made it). */
    val canvasLabel: String = "",
    /** Label for the in-flight replacing turn. */
    val pendingLabel: String = "",
    /** Previous turns' finished canvases, oldest→newest (read-only timeline). */
    val canvasHistory: List<CanvasSnapshot> = emptyList(),
    /** When non-null, the canvas area shows this history entry read-only. */
    val viewingIndex: Int? = null,
    // --- input / chrome ---
    val staged: List<StagedAttachment> = emptyList(),
    val statusText: String? = null,
    val agents: List<Agent> = emptyList(),
    val history: List<ChatSummary> = emptyList(),
    val audit: List<AuditEvent> = emptyList(),
) {
    /** What the canvas area actually renders (a history entry, or the live canvas). */
    val visibleCanvas: List<Component>
        get() = viewingIndex?.let { canvasHistory.getOrNull(it)?.components } ?: canvas

    val isViewingHistory: Boolean get() = viewingIndex != null

    /**
     * Skeletons show for the whole in-flight replacing query (from send until the
     * final SDUI commits on `done`) — the canvas shows a loading state, never a
     * bare status line or stale content, while a query is being answered.
     */
    val showSkeleton: Boolean
        get() = pendingReplace && viewingIndex == null
}

/**
 * Owns the connection + derived UI state. Folds each [Inbound] into [state] and
 * sends chat/events out. The canvas follows a "commit-on-done" lifecycle so the
 * UI-generation area only ever shows a COMPLETE orchestrator canvas (or skeletons
 * while the first one is being produced): a replacing turn buffers its ops into
 * [UiState.pendingCanvas] and swaps them into [UiState.canvas] on `chat_status
 * done`, so a new user message never blanks the previous canvas. Each superseded
 * canvas is pushed onto [UiState.canvasHistory] for the read-only timeline.
 */
class AppViewModel(
    private val client: OrchestratorClient,
    private val rest: AstralRest,
) : ViewModel() {
    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state.asStateFlow()

    private var session: Job? = null
    private var token: String? = null
    private var attachSeq: Long = 0
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
                    client.state.collect { c ->
                        // A dropped socket ends any in-flight turn so the canvas
                        // area never gets stuck showing skeletons forever.
                        val cur = _state.value
                        _state.value =
                            if (c == ConnectionState.Disconnected) {
                                cur.copy(
                                    connection = c,
                                    turnActive = false,
                                    pendingReplace = false,
                                    pendingCanvas = emptyList(),
                                )
                            } else {
                                cur.copy(connection = c)
                            }
                    }
                }
            }
    }

    fun sendChat(text: String) {
        val s = _state.value
        val ready = s.staged.filter { it.state == "ready" && it.attachmentId != null }
        if (text.isBlank() && ready.isEmpty()) return
        val bubble =
            if (ready.isEmpty()) text
            else (text + "\n📎 " + ready.joinToString(", ") { it.filename }).trim()
        _state.value =
            s.copy(
                turns = s.turns + ChatTurn("user", bubble),
                turnActive = true,
                pendingReplace = true,
                pendingCanvas = emptyList(),
                pendingLabel = (text.ifBlank { ready.firstOrNull()?.filename ?: "" }).take(80),
                staged = emptyList(),
                viewingIndex = null,
                statusText = null,
            )
        val attachments = ready.map { ChatAttachment(it.attachmentId!!, it.filename, it.category) }
        client.sendChat(text, _state.value.activeChatId, attachments)
    }

    fun sendEvent(action: String, payload: JsonObject = JsonObject(emptyMap())) {
        client.sendEvent(action, _state.value.activeChatId, payload)
    }

    /** Start a fresh conversation (clears the canvas, timeline, and transcript). */
    fun newChat() {
        seqState.clear()
        _state.value =
            _state.value.copy(
                activeChatId = null,
                turns = emptyList(),
                canvas = emptyList(),
                pendingCanvas = emptyList(),
                canvasHistory = emptyList(),
                viewingIndex = null,
                turnActive = false,
                pendingReplace = false,
                canvasLabel = "",
                pendingLabel = "",
                staged = emptyList(),
                statusText = null,
            )
        sendEvent("new_chat")
    }

    // --- attachments (paperclip, feature 031) -------------------------------

    /** Stage + upload a picked file; the chip flips uploading→ready/failed. */
    fun stageAttachment(filename: String, mimeType: String?, bytes: ByteArray) {
        val t = token ?: return
        val uid = ++attachSeq
        _state.value =
            _state.value.copy(
                staged = _state.value.staged + StagedAttachment(uid, filename, "file", null, "uploading"),
            )
        viewModelScope.launch {
            val up = runCatching { rest.uploadAttachment(t, filename, mimeType, bytes) }.getOrNull()
            _state.value =
                _state.value.copy(
                    staged =
                        _state.value.staged.map { a ->
                            when {
                                a.uid != uid -> a
                                up == null -> a.copy(state = "failed", note = "upload failed")
                                else ->
                                    a.copy(
                                        attachmentId = up.attachmentId,
                                        category = up.category,
                                        state = "ready",
                                        note = parserNote(up.parserStatus),
                                    )
                            }
                        },
                )
        }
    }

    fun removeAttachment(uid: Long) {
        _state.value = _state.value.copy(staged = _state.value.staged.filterNot { it.uid == uid })
    }

    // --- read-only canvas timeline (US "previous canvases") -----------------

    fun viewCanvasSnapshot(index: Int) {
        if (index in _state.value.canvasHistory.indices) {
            _state.value = _state.value.copy(viewingIndex = index)
        }
    }

    fun backToLiveCanvas() {
        _state.value = _state.value.copy(viewingIndex = null)
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
        _state.value = _state.value.copy(screen = Screen.Chat, viewingIndex = null)
    }

    /** Enable/disable a single tool of an agent (REST per-(tool,kind) write), then refresh. */
    fun setToolEnabled(agent: Agent, tool: String, enabled: Boolean) {
        patchAgent(agent.id) { it.copy(permissions = it.permissions + (tool to enabled)) } // optimistic
        val t = token ?: return
        val kind = agent.toolScopeMap[tool] ?: "tools:read"
        viewModelScope.launch {
            runCatching { rest.setToolPermission(t, agent.id, tool, kind, enabled) }
            sendEvent("discover_agents")
        }
    }

    /** Master toggle: enable/disable all of an agent's tools at once (WS scopes + overrides). */
    fun setAgentEnabled(agent: Agent, enabled: Boolean) {
        patchAgent(agent.id) { a -> a.copy(permissions = a.tools.associateWith { enabled }) } // optimistic
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

    /**
     * Optimistically update one agent so a toggle responds instantly; the
     * subsequent discover_agents refresh reconciles with the server truth.
     */
    private fun patchAgent(agentId: String, transform: (Agent) -> Agent) {
        _state.value =
            _state.value.copy(
                agents = _state.value.agents.map { if (it.id == agentId) transform(it) else it },
            )
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

    // --- reducer ------------------------------------------------------------

    private fun reduce(s: UiState, msg: Inbound): UiState =
        when (msg) {
            is Inbound.UiRender ->
                if (msg.target == "chat") {
                    val text = flattenText(msg.components)
                    if (text.isBlank()) s else s.copy(turns = s.turns + ChatTurn("assistant", text))
                } else {
                    // Reasoning collapsibles (pushed via ui_render(canvas)) belong in
                    // the CHAT window as collapsible snippets, never on the canvas.
                    // Everything else is real canvas content.
                    val (reasoning, canvasComps) = msg.components.partition(::isReasoning)
                    val reasoningTurns =
                        reasoning.mapNotNull { r ->
                            flattenText(r.children).ifBlank { flattenText(listOf(r)) }
                                .takeIf { it.isNotBlank() }
                                ?.let { ChatTurn("reasoning", it) }
                        }
                    val s2 = if (reasoningTurns.isEmpty()) s else s.copy(turns = s.turns + reasoningTurns)
                    when {
                        canvasComps.isEmpty() -> s2
                        // In-turn renders are ADDITIVE overlays (native clients skip
                        // the designer); merge by identity so they never wipe the
                        // round's upserted components (charts/tables/etc.).
                        s2.pendingReplace ->
                            s2.copy(pendingCanvas = Canvas.apply(s2.pendingCanvas, renderToOps(canvasComps)))
                        // Out-of-turn full canvas (load_chat rehydration): commit now.
                        else -> s2.copy(canvas = canvasComps, pendingCanvas = emptyList())
                    }
                }
            is Inbound.UiUpsert ->
                // Drop only ops explicitly addressed to a DIFFERENT chat. On the
                // first turn `activeChatId` may not be set yet when the round's
                // upserts arrive — accept those rather than losing the canvas.
                if (msg.chatId != null && s.activeChatId != null && msg.chatId != s.activeChatId) {
                    s
                } else if (s.pendingReplace) {
                    s.copy(pendingCanvas = Canvas.apply(s.pendingCanvas, msg.ops))
                } else {
                    s.copy(canvas = Canvas.apply(s.canvas, msg.ops))
                }
            is Inbound.ChatCreated -> s.copy(activeChatId = msg.chatId ?: s.activeChatId)
            is Inbound.UserMessageAcked ->
                s.copy(
                    activeChatId = msg.chatId ?: s.activeChatId,
                    turnActive = true,
                    pendingReplace = true,
                    pendingCanvas = emptyList(),
                )
            is Inbound.ChatLoaded ->
                s.copy(
                    activeChatId = msg.chat.id ?: s.activeChatId,
                    turns = msg.chat.messages.map { ChatTurn(it.role, it.content) },
                    // A different conversation: reset the live canvas + timeline;
                    // the trailing ui_render(canvas) rehydrates `canvas`.
                    canvas = emptyList(),
                    pendingCanvas = emptyList(),
                    canvasHistory = emptyList(),
                    viewingIndex = null,
                    turnActive = false,
                    pendingReplace = false,
                    canvasLabel = "",
                    pendingLabel = "",
                    statusText = null,
                )
            is Inbound.ChatStatus -> reduceStatus(s, msg)
            is Inbound.AgentList -> s.copy(agents = msg.agents)
            is Inbound.HistoryList -> s.copy(history = msg.chats)
            is Inbound.UiStreamData ->
                applyCanvasOps(s, streamFrameToOps(msg, s.activeChatId, seqState))
            is Inbound.StreamSubscribed ->
                applyCanvasOps(s, subscribeAckOps(msg))
            is Inbound.StreamErrorMsg ->
                applyCanvasOps(s, streamErrorOps(msg))
            else -> s
        }

    /** Route streaming/patch ops to the buffer (mid-replace-turn) or live canvas. */
    private fun applyCanvasOps(s: UiState, ops: List<CanvasOp>): UiState {
        if (ops.isEmpty()) return s
        return if (s.pendingReplace) {
            s.copy(pendingCanvas = Canvas.apply(s.pendingCanvas, ops))
        } else {
            s.copy(canvas = Canvas.apply(s.canvas, ops))
        }
    }

    /**
     * Convert a bare `ui_render` component list into in-place upsert ops. A
     * component keeps its own id; an id-less overlay (the reasoning collapsible)
     * gets a STABLE synthetic id by type+position so repeated pushes update it in
     * place instead of duplicating — and it never collides with the round's
     * real component ids.
     */
    private fun renderToOps(components: List<Component>): List<CanvasOp> =
        components.mapIndexed { i, c ->
            val id = c.id ?: "xr-${c.type}-$i"
            CanvasOp(op = "upsert", componentId = id, component = if (c.id == null) c.copy(id = id) else c)
        }

    private fun reduceStatus(s: UiState, msg: Inbound.ChatStatus): UiState {
        val label = msg.message?.takeIf { it.isNotBlank() } ?: msg.status
        return when (msg.status) {
            "done" -> commitTurn(s)
            "thinking", "executing", "fixing", "processing_async" ->
                s.copy(turnActive = true, statusText = label)
            else -> s.copy(statusText = label) // "info" et al.: status only
        }
    }

    /**
     * A turn finished (`chat_status done`). For a replacing turn that produced a
     * canvas, swap the buffer in and push the prior canvas onto the timeline; a
     * text-only turn leaves the canvas untouched (never blank it).
     */
    private fun commitTurn(s: UiState): UiState {
        if (!s.pendingReplace) {
            return s.copy(turnActive = false, statusText = null)
        }
        if (s.pendingCanvas.isEmpty()) {
            return s.copy(turnActive = false, pendingReplace = false, statusText = null)
        }
        val newHistory =
            if (s.canvas.isNotEmpty()) {
                s.canvasHistory +
                    CanvasSnapshot(
                        label = s.canvasLabel.ifBlank { "Canvas ${s.canvasHistory.size + 1}" },
                        components = s.canvas,
                    )
            } else {
                s.canvasHistory
            }
        return s.copy(
            canvas = s.pendingCanvas,
            pendingCanvas = emptyList(),
            canvasHistory = newHistory,
            canvasLabel = s.pendingLabel,
            pendingLabel = "",
            turnActive = false,
            pendingReplace = false,
            statusText = null,
        )
    }

    /** A model "Reasoning" collapsible (routed to the chat, not the canvas). */
    private fun isReasoning(c: Component): Boolean =
        c.type.equals("collapsible", ignoreCase = true) &&
            ((c.attributes["title"] as? JsonPrimitive)?.contentOrNull ?: "")
                .equals("Reasoning", ignoreCase = true)

    private fun flattenText(components: List<Component>): String =
        components.joinToString("\n") { c ->
            val own =
                (c.attributes["content"] as? JsonPrimitive)?.contentOrNull
                    ?: (c.attributes["text"] as? JsonPrimitive)?.contentOrNull
                    ?: ""
            (own + "\n" + flattenText(c.children)).trim()
        }.trim()

    private fun parserNote(status: String?): String? =
        when (status) {
            "preparing" -> "preparing reader…"
            "pending_admin_approval" -> "reader pending admin"
            "unavailable" -> "no reader yet"
            else -> null
        }

    companion object {
        fun factory(client: OrchestratorClient, rest: AstralRest) =
            viewModelFactory {
                initializer { AppViewModel(client, rest) }
            }
    }
}
