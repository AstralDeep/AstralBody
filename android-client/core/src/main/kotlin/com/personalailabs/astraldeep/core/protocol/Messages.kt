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

/**
 * Feature 060 account-scoped hydration request carried by `register_ui.resume`.
 * Android remains an author-only client and never attaches `agent_host`.
 */
data class ConversationResume(
    val activeChatId: String,
    val requestGeneration: String,
    val schemaVersion: Int = 1,
)

/**
 * Complete generation and revision fence on a disposable preview frame.
 * A null scope means the frame came from the bounded legacy compatibility
 * path; a partially present or malformed scope is rejected by [Wire].
 */
data class TransientFrameScope(
    val chatId: String,
    val connectionGeneration: String,
    val requestGeneration: String,
    val baseRenderRevision: ULong,
    val frameSequence: ULong,
)

/** Complete committed canvas carried atomically with a conversation transcript. */
data class SnapshotCanvas(
    val target: String,
    val components: List<Component>,
)

/** Stable safe error projection carried by a terminal `operation_status`. */
data class OperationStatusError(
    val code: String,
    val message: String,
)

/**
 * Structured v2 desktop-host advertisement. Android validates the shared
 * shape for parity but never emits it because Android is author-only.
 */
data class AgentHostRegistration(
    val hostId: String,
    val supportedRuntimeContractVersions: List<Int>,
    val runtimeLockSha256: String,
    val platform: String,
    val clientVersion: String,
)

/** Server acknowledgement for a validated desktop-host advertisement. */
data class AgentHostRegistered(
    val hostId: String,
    val hostSessionId: String,
    val inventoryRequired: Boolean,
    val acceptedAt: String,
)

/** Candidate-owned macOS personal-agent host applicability. */
data class PersonalAgentHostCapability(
    val supported: Boolean,
    val runtimeContractVersions: List<Int>,
    val sourceFeature: String?,
)

/** Exact immutable capability map shared by the dashboard and `system_config`. */
data class CandidateCapabilityMap(
    val macosPersonalAgentHost: PersonalAgentHostCapability,
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
    data class UiRender(
        val target: String,
        val components: List<Component>,
        val scope: TransientFrameScope? = null,
    ) : Inbound

    data class UiUpsert(
        val chatId: String?,
        val ops: List<CanvasOp>,
        val scope: TransientFrameScope? = null,
    ) : Inbound

    data class UiStreamData(
        val streamId: String?,
        val sessionId: String?,
        val seq: Int?,
        val components: List<Component>,
        val terminal: Boolean,
        val error: StreamError?,
        val toolName: String?,
        /** 055 additive field — workspace identity when the stream is bridged; absent on legacy streams. */
        val componentId: String? = null,
        val scope: TransientFrameScope? = null,
    ) : Inbound

    data class StreamSubscribed(
        val streamId: String?,
        val toolName: String?,
        val componentId: String? = null,
    ) : Inbound

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

    /**
     * Feature 060 authoritative committed transcript + canvas projection.
     * Every top-level field and every semantic transcript part is validated
     * before this variant is constructed.
     */
    data class ConversationSnapshot(
        val schemaVersion: Int,
        val snapshotId: String,
        val chatId: String,
        val connectionGeneration: String,
        val requestGeneration: String,
        val snapshotPurpose: String,
        val renderRevision: ULong,
        val committedAt: String,
        val transcript: List<JsonObject>,
        val canvas: SnapshotCanvas,
    ) : Inbound

    /**
     * Strict prelude that opens a commit-purpose request fence for a detached
     * or server-originated update before its authoritative snapshot arrives.
     */
    data class ConversationCommitReady(
        val schemaVersion: Int,
        val chatId: String,
        val connectionGeneration: String,
        val requestGeneration: String,
        val renderRevision: ULong,
    ) : Inbound

    data class AgentList(val agents: List<Agent>) : Inbound

    data class HistoryList(val chats: List<ChatSummary>) : Inbound

    data class ChatStatus(val status: String?, val message: String?) : Inbound

    /** Feature 060 server-owned durable operation projection. */
    data class OperationStatus(
        val operationId: String,
        val action: String,
        val surface: String,
        val chatId: String?,
        val connectionGeneration: String,
        val requestGeneration: String,
        val sequence: ULong,
        val state: String,
        val phase: String,
        val label: String,
        val terminal: Boolean,
        val retryable: Boolean,
        val error: OperationStatusError?,
        val retryAfterMs: ULong?,
        val updatedAt: String,
    ) : Inbound

    /** Feature 060 generation-fenced personal-agent runtime projection. */
    data class AgentLifecycle(
        val agentId: String,
        val revisionId: String?,
        val runtimeInstanceId: String?,
        val lifecycleGeneration: ULong,
        val stateRevision: ULong,
        val state: String,
        val reasonCode: String?,
        val label: String,
        val updatedAt: String,
    ) : Inbound

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

    /** Exact pre-admission refusal correlated to one client-only submission. */
    data class AdmissionRefusal(
        val submissionId: String,
        val code: String,
        val message: String,
        val retryable: Boolean,
        val retryAfterMs: ULong?,
    ) : Inbound

    /** Feature 044/060 — normalized error plus optional submission/conversation fence. */
    data class ErrorFrame(
        val code: String?,
        val message: String,
        val chatId: String? = null,
        val connectionGeneration: String? = null,
        val requestGeneration: String? = null,
        val retryable: Boolean = false,
        /** Present with [accepted] false when durable admission refused local work. */
        val submissionId: String? = null,
        val accepted: Boolean? = null,
    ) : Inbound

    /** One step of the running turn's execution trail (`chat_step`). */
    data class ChatStep(val id: String?, val name: String?, val status: String?) : Inbound

    /** A live progress line from an executing tool (`tool_progress`), pre-composed. */
    data class ToolProgress(val label: String) : Inbound

    /** The turn detached into a background task (`task_started`). */
    data class TaskStarted(val taskId: String?, val chatId: String? = null) : Inbound

    /** A background task finished (`task_completed`). */
    data class TaskCompleted(val taskId: String?, val chatId: String?) : Inbound

    /**
     * A scheduler/system push (`notification`, feature 044). [chatId] names the
     * chat the job wrote into (055 continuity — the open chat reloads on it).
     */
    data class Notification(
        val title: String?,
        val body: String?,
        val level: String?,
        val chatId: String? = null,
    ) : Inbound

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

    // --- workspace component verbs (055 US3, wire-contract §4) — promoted
    // ignored → handled; the server's ui_upsert/ui_render fan-outs stay
    // authoritative, these give the issuing socket immediate feedback. ---

    /** A `save_component` ack (`component_saved`); [title] names the saved row. */
    data class ComponentSaved(val title: String?) : Inbound

    /** `component_save_error` — a save/delete failure. */
    data class ComponentSaveError(val error: String?) : Inbound

    /** `component_deleted` — an identity-keyed remove of [componentId]. */
    data class ComponentDeleted(val componentId: String?) : Inbound

    /** `combine_status` — combine/condense progress. */
    data class CombineStatus(val status: String?, val message: String?) : Inbound

    /** `combine_error` — a combine/condense failure. */
    data class CombineError(val error: String?) : Inbound

    /**
     * `components_combined` / `components_condensed` — the consumed identities
     * to remove plus the carried result component(s), identity-assigned at
     * decode (workspace id when stamped, else the fresh saved-row id).
     */
    data class ComponentsReplaced(
        val removedIds: List<String>,
        val newComponents: List<Component>,
    ) : Inbound

    /** `saved_components_list` — [count] rows; no native surface consumes the rows yet. */
    data class SavedComponentsList(val count: Int) : Inbound

    data class Unknown(val type: String) : Inbound
}
