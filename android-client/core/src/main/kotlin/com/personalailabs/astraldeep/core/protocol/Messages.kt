package com.personalailabs.astraldeep.core.protocol

import com.personalailabs.astraldeep.core.chrome.ChromeMenuModel
import com.personalailabs.astraldeep.core.sdui.CanvasOp
import com.personalailabs.astraldeep.core.sdui.Component
import kotlinx.serialization.json.JsonObject

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

/**
 * A staged upload referenced from an outbound `chat_message` (feature 031). The
 * server resolves the [attachmentId] (ownership-validated) and injects the
 * "Attachments on this turn" reader block. Mirrors the web payload shape
 * `{attachment_id, filename, category}`.
 */
data class ChatAttachment(
    val attachmentId: String,
    val filename: String,
    val category: String,
)

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

    /** Authoritative "a new user turn has started" (emitted once per chat turn). */
    data class UserMessageAcked(val chatId: String?, val messageId: String?) : Inbound

    data class ChatLoaded(val chat: ChatTranscript) : Inbound

    data class AgentList(val agents: List<Agent>) : Inbound

    data class HistoryList(val chats: List<ChatSummary>) : Inbound

    data class ChatStatus(val status: String?, val message: String?) : Inbound

    data class ChromeRender(val region: String, val html: String) : Inbound

    /** Feature 042 — the server-owned chrome model (top bar + settings menu). */
    data class ChromeMenu(val model: ChromeMenuModel) : Inbound

    /**
     * Feature 043 — a settings surface delivered as SDUI components (native).
     * [mode] is the reserved delivery field (feature 054): `"replace"` (the
     * default, and the value when absent) is today's behavior; `"mandatory"`
     * marks the first-run LLM-setup gate — render even though unsolicited and
     * suppress every dismissal until the server closes the surface.
     */
    data class ChromeSurface(
        val surfaceKey: String,
        val title: String,
        val components: List<Component>,
        val mode: String = "replace",
    ) : Inbound

    data class AuthRequired(val reason: String?) : Inbound

    /** Feature 044 — a server `error` reply, normalized from its three wire shapes. */
    data class ErrorFrame(val code: String?, val message: String) : Inbound

    /** One step of the running turn's execution trail (`chat_step`). */
    data class ChatStep(val id: String?, val name: String?, val status: String?) : Inbound

    /** A live progress line from an executing tool (`tool_progress`), pre-composed. */
    data class ToolProgress(val label: String) : Inbound

    /** The turn detached into a background task (`task_started`). */
    data class TaskStarted(val taskId: String?) : Inbound

    /** A background task finished (`task_completed`). */
    data class TaskCompleted(val taskId: String?, val chatId: String?) : Inbound

    /** A scheduler/system push (`notification`, feature 044). */
    data class Notification(val title: String?, val body: String?, val level: String?) : Inbound

    /**
     * Boot/refresh of stored user preferences (`user_preferences`, feature 044).
     * [theme] is the raw `preferences.theme` object (preset|colors|color_key+value);
     * the :app reducer interprets it into the live palette (US5 restyle).
     */
    data class UserPreferences(val theme: JsonObject?) : Inbound

    /**
     * The read-only workspace timeline is being entered/left
     * (`workspace_timeline_mode`, feature 028/044). While [active], the client
     * disables mutating affordances (input/send + component actions).
     */
    data class WorkspaceTimelineMode(val active: Boolean) : Inbound

    data class Unknown(val type: String) : Inbound
}
