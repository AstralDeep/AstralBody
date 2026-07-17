package com.personalailabs.astraldeep.core.protocol

import com.personalailabs.astraldeep.core.sdui.CanvasOp
import com.personalailabs.astraldeep.core.sdui.Component
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.add
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import java.time.Instant
import java.util.UUID

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
        val root =
            runCatching { json.parseToJsonElement(raw) as? JsonObject }.getOrNull()
                ?: return Inbound.Unknown("")
        return decode(root)
    }

    fun decode(root: JsonObject): Inbound =
        when (val type = root.str("type").orEmpty()) {
            "ui_render" -> uiRenderFromJson(root, type)
            "ui_upsert" -> uiUpsertFromJson(root, type)
            // The modern push system and the legacy poll system share the frame shape.
            "ui_stream_data", "stream_data" -> uiStreamDataFromJson(root, type)
            "stream_subscribed" ->
                Inbound.StreamSubscribed(root.str("stream_id"), root.str("tool_name"), root.str("component_id"))
            "stream_error" -> {
                val payload = root.obj("payload")
                Inbound.StreamErrorMsg(
                    requestAction = root.str("request_action"),
                    sessionId = root.str("session_id"),
                    streamId = payload?.str("stream_id"),
                    toolName = payload?.str("tool_name") ?: root.str("tool_name"),
                    error =
                        errorFromJson(payload)
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
            "conversation_snapshot" -> conversationSnapshotFromJson(root) ?: Inbound.Unknown(type)
            "conversation_commit_ready" -> conversationCommitReadyFromJson(root) ?: Inbound.Unknown(type)
            "agent_list" -> Inbound.AgentList(agentsFromJson(root.arr("agents")))
            "history_list" -> Inbound.HistoryList(chatsFromJson(root.arr("chats")))
            "chat_status" -> Inbound.ChatStatus(root.str("status"), root.str("message"))
            "operation_status" -> operationStatusFromJson(root) ?: Inbound.Unknown(type)
            "agent_lifecycle" -> agentLifecycleFromJson(root) ?: Inbound.Unknown(type)
            "chrome_render" -> Inbound.ChromeRender(root.str("region") ?: "modal", root.str("html").orEmpty())
            "chrome_menu" ->
                com.personalailabs.astraldeep.core.chrome.ChromeMenuModel.fromJson(root.obj("model"))
                    ?.let { Inbound.ChromeMenu(it) } ?: Inbound.Unknown(type)
            "chrome_surface" ->
                Inbound.ChromeSurface(
                    surfaceKey = root.str("surface_key").orEmpty(),
                    title = root.str("title").orEmpty(),
                    components = Component.listFromJson(root.arr("components")),
                    // Reserved delivery field (054): absent == "replace" (today's
                    // behavior); "mandatory" == the first-run LLM-setup gate.
                    mode = root.str("mode") ?: "replace",
                )
            "auth_required" -> Inbound.AuthRequired(root.str("reason"))
            // Server error replies arrive in three shapes: {code,message},
            // {payload:{message}}, {message} — normalize; never silent (FR-002).
            "error" ->
                admissionRefusalFromJson(root)
                    ?: Inbound.ErrorFrame(
                        code = root.str("code"),
                        message = root.str("message") ?: root.obj("payload")?.str("message") ?: "Something went wrong.",
                        chatId = root.str("chat_id"),
                        connectionGeneration = root.str("connection_generation"),
                        requestGeneration = root.str("request_generation"),
                        retryable = root.bool("retryable") ?: false,
                        submissionId = canonicalUuid4(root.str("submission_id")),
                        accepted = root.bool("accepted"),
                    )
            "chat_step" -> {
                val step = root.obj("step")
                Inbound.ChatStep(
                    id = step?.str("id"),
                    name = step?.str("name") ?: step?.str("kind"),
                    status = step?.str("status"),
                )
            }
            "tool_progress" -> {
                // Compose a short human label from whatever fields arrived (all
                // optional): "tool: message (pct%)".
                val head = listOfNotNull(root.str("tool_name"), root.str("message")).joinToString(": ")
                val pct = root.str("percentage")?.let { " ($it%)" }.orEmpty()
                Inbound.ToolProgress(label = (head + pct).ifBlank { "Working…" })
            }
            // Task frames nest their fields under `payload` (older emitters were flat).
            "task_started" ->
                Inbound.TaskStarted(
                    taskId = root.obj("payload")?.str("task_id") ?: root.str("task_id"),
                    chatId = root.obj("payload")?.str("chat_id") ?: root.str("chat_id"),
                )
            "task_completed" ->
                Inbound.TaskCompleted(
                    taskId = root.obj("payload")?.str("task_id") ?: root.str("task_id"),
                    chatId = root.obj("payload")?.str("chat_id") ?: root.str("chat_id"),
                )
            "notification" ->
                Inbound.Notification(
                    title = root.str("title"),
                    body = root.str("body"),
                    level = root.str("level"),
                    chatId = root.str("chat_id"),
                )
            // Stored preferences at boot ({preferences:{theme:{…}}}); the app folds
            // `theme` into the live palette (US5 restyle).
            "user_preferences" -> Inbound.UserPreferences(theme = root.obj("preferences")?.obj("theme"))
            // Read-only workspace timeline toggle ({active}); `on` is tolerated.
            "workspace_timeline_mode" ->
                Inbound.WorkspaceTimelineMode(active = root.bool("active") ?: root.bool("on") ?: false)
            // Workspace verb acks (055 US3, wire-contract §4).
            "component_saved" -> Inbound.ComponentSaved(title = root.obj("component")?.str("title"))
            "component_save_error" -> Inbound.ComponentSaveError(root.str("error"))
            "component_deleted" -> Inbound.ComponentDeleted(root.str("component_id"))
            "combine_status" -> Inbound.CombineStatus(root.str("status"), root.str("message"))
            "combine_error" -> Inbound.CombineError(root.str("error"))
            "components_combined", "components_condensed" ->
                Inbound.ComponentsReplaced(
                    removedIds = root.strList("removed_ids"),
                    newComponents = replacementsFromJson(root.arr("new_components")),
                )
            "saved_components_list" -> Inbound.SavedComponentsList(count = root.arr("components")?.size ?: 0)
            else -> Inbound.Unknown(type)
        }

    /** Validate the shared structured-v2 host advertisement without emitting it. */
    fun decodeAgentHostRegistration(raw: String): AgentHostRegistration? = parseObject(raw)?.let(::agentHostRegistrationFromJson)

    /** Validate the host acknowledgement that author-only Android deliberately ignores. */
    fun decodeAgentHostRegistered(raw: String): AgentHostRegistered? = parseObject(raw)?.let(::agentHostRegisteredFromJson)

    /** Parse the immutable candidate capability map; malformed/missing data stays unknown. */
    fun decodeCandidateCapabilityMap(raw: String): CandidateCapabilityMap? = parseObject(raw)?.let(::candidateCapabilityMapFromJson)

    fun decodeCandidateCapabilityMap(root: JsonObject): CandidateCapabilityMap? = candidateCapabilityMapFromJson(root)

    // ---- outbound encoders ----

    fun encodeRegisterUi(
        token: String,
        sessionId: String?,
        device: DeviceCapabilities,
        connectionGeneration: String? = null,
        resume: ConversationResume? = null,
    ): String {
        require(connectionGeneration == null || canonicalUuid4(connectionGeneration) != null) {
            "connectionGeneration must be a canonical UUID4"
        }
        if (resume != null) {
            require(connectionGeneration != null) { "resume requires connectionGeneration" }
            require(resume.schemaVersion == 1) { "resume schemaVersion must be 1" }
            require(canonicalUuid4(resume.activeChatId) != null) { "resume activeChatId must be a canonical UUID4" }
            require(canonicalUuid4(resume.requestGeneration) != null) {
                "resume requestGeneration must be a canonical UUID4"
            }
        }
        return buildJsonObject {
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
            if (connectionGeneration != null) put("connection_generation", connectionGeneration)
            if (resume != null) {
                putJsonObject("resume") {
                    put("schema_version", resume.schemaVersion)
                    put("active_chat_id", resume.activeChatId)
                    put("request_generation", resume.requestGeneration)
                }
            }
        }.toString()
    }

    fun encodeUiEvent(
        action: String,
        sessionId: String?,
        payload: JsonObject = JsonObject(emptyMap()),
        requestGeneration: String? = null,
        submissionId: String? = null,
    ): String {
        require(requestGeneration == null || canonicalUuid4(requestGeneration) != null) {
            "requestGeneration must be a canonical UUID4"
        }
        require(submissionId == null || canonicalUuid4(submissionId) != null) {
            "submissionId must be a canonical UUID4"
        }
        val identifiedPayload =
            buildJsonObject {
                payload.forEach(::put)
                if (submissionId != null) put("submission_id", submissionId)
                if (requestGeneration != null) put("request_generation", requestGeneration)
            }
        return buildJsonObject {
            put("type", "ui_event")
            put("action", action)
            put("session_id", sessionId)
            if (submissionId != null) put("submission_id", submissionId)
            if (requestGeneration != null) put("request_generation", requestGeneration)
            put("payload", identifiedPayload)
        }.toString()
    }

    fun encodeChatMessage(
        message: String,
        chatId: String?,
        attachments: List<ChatAttachment> = emptyList(),
        requestGeneration: String? = null,
        submissionId: String? = null,
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
            requestGeneration = requestGeneration,
            submissionId = submissionId,
        )

    // ---- feature 060 strict wire models ----

    private data class ScopeDecode(
        val valid: Boolean,
        val scope: TransientFrameScope?,
    )

    private data class ExplicitNullable<out T>(val value: T?)

    private val snakeCase = Regex("^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
    private val lowerSha256 = Regex("^[0-9a-f]{64}$")
    private val strictSemVer =
        Regex(
            "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)" +
                "(?:-[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?" +
                "(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?$",
        )
    private val operationFlags =
        mapOf(
            "accepted" to (false to false),
            "validating" to (false to false),
            "persisting" to (false to false),
            "running" to (false to false),
            "completed" to (true to false),
            "failed" to (true to false),
            "cancelled" to (true to false),
            "retryable" to (true to true),
        )
    private val operationErrorCodes =
        setOf(
            "invalid_input",
            "validation_failed",
            "provider_unavailable",
            "network_unavailable",
            "deadline_exceeded",
            "capacity_exceeded",
            "queue_wait_expired",
            "registration_timeout",
            "disconnected",
            "cancelled_by_user",
            "operation_failed",
            "conflict",
            "incompatible_runtime",
            "agent_offline",
            "stale_generation",
        )
    private val admissionRefusalCodes =
        setOf(
            "capacity_exceeded",
            "registration_required",
            "registration_timeout",
            "idempotency_conflict",
            "connection_closing",
            "service_draining",
            "invalid_input",
            "registration_queue_full",
            "operation_failed",
        )
    private val agentLifecycleReasonCodes =
        setOf(
            "invalid_host_registration",
            "runtime_contract_unsupported",
            "runtime_lock_mismatch",
            "bundle_digest_mismatch",
            "bundle_install_failed",
            "child_start_failed",
            "child_registration_timeout",
            "child_exited",
            "child_hung",
            "host_lost",
            "agent_offline",
            "agent_deleted",
            "stale_runtime_generation",
            "revision_promotion_failed",
            "inventory_required",
            "process_cleanup_timeout",
        )

    private fun uiRenderFromJson(
        root: JsonObject,
        type: String,
    ): Inbound {
        val decodedScope = root.transientScope()
        if (!decodedScope.valid) return Inbound.Unknown(type)
        return Inbound.UiRender(
            target = root.str("target") ?: "canvas",
            components = Component.listFromJson(root.arr("components")),
            scope = decodedScope.scope,
        )
    }

    private fun uiUpsertFromJson(
        root: JsonObject,
        type: String,
    ): Inbound {
        val decodedScope = root.transientScope()
        if (!decodedScope.valid) return Inbound.Unknown(type)
        return Inbound.UiUpsert(
            chatId = root.str("chat_id"),
            ops = opsFromJson(root.arr("ops")),
            scope = decodedScope.scope,
        )
    }

    private fun uiStreamDataFromJson(
        root: JsonObject,
        type: String,
    ): Inbound {
        val decodedScope = root.transientScope()
        if (!decodedScope.valid) return Inbound.Unknown(type)
        return Inbound.UiStreamData(
            streamId = root.str("stream_id"),
            sessionId = root.str("session_id"),
            seq = root.int("seq"),
            components = Component.listFromJson(root.arr("components")),
            terminal = root.bool("terminal") ?: false,
            error = errorFromJson(root.obj("error")),
            toolName = root.str("tool_name"),
            componentId = root.str("component_id"),
            scope = decodedScope.scope,
        )
    }

    private fun JsonObject.transientScope(): ScopeDecode {
        val fenceFields =
            listOf(
                "connection_generation",
                "request_generation",
                "base_render_revision",
                "frame_sequence",
            )
        if (fenceFields.none(::containsKey)) return ScopeDecode(valid = true, scope = null)
        val chatId = canonicalUuid4(strictString("chat_id")) ?: return ScopeDecode(false, null)
        val connection =
            canonicalUuid4(strictString("connection_generation")) ?: return ScopeDecode(false, null)
        val request = canonicalUuid4(strictString("request_generation")) ?: return ScopeDecode(false, null)
        val baseRevision = strictULong("base_render_revision") ?: return ScopeDecode(false, null)
        val sequence = strictULong("frame_sequence") ?: return ScopeDecode(false, null)
        return ScopeDecode(
            valid = true,
            scope =
                TransientFrameScope(
                    chatId = chatId,
                    connectionGeneration = connection,
                    requestGeneration = request,
                    baseRenderRevision = baseRevision,
                    frameSequence = sequence,
                ),
        )
    }

    private fun conversationSnapshotFromJson(root: JsonObject): Inbound.ConversationSnapshot? {
        if (
            !root.hasExactKeys(
                "type",
                "schema_version",
                "snapshot_id",
                "chat_id",
                "connection_generation",
                "request_generation",
                "snapshot_purpose",
                "render_revision",
                "committed_at",
                "transcript",
                "canvas",
            )
        ) {
            return null
        }
        if (root.strictString("type") != "conversation_snapshot" || root.strictULong("schema_version") != 1UL) {
            return null
        }
        val snapshotId = canonicalUuid4(root.strictString("snapshot_id")) ?: return null
        val chatId = canonicalUuid4(root.strictString("chat_id")) ?: return null
        val connection = canonicalUuid4(root.strictString("connection_generation")) ?: return null
        val request = canonicalUuid4(root.strictString("request_generation")) ?: return null
        val purpose = root.strictString("snapshot_purpose")?.takeIf { it == "hydration" || it == "commit" } ?: return null
        val renderRevision = root.strictULong("render_revision") ?: return null
        val committedAt = root.strictString("committed_at")?.takeIf(::isRfc3339Utc) ?: return null
        val transcript = root.arr("transcript")?.let(::canonicalTranscript) ?: return null
        val canvasObject = root.obj("canvas") ?: return null
        if (!canvasObject.hasExactKeys("target", "components") || canvasObject.strictString("target") != "canvas") {
            return null
        }
        val componentArray = canvasObject.arr("components") ?: return null
        if (!canonicalNativeComponents(componentArray)) return null
        return Inbound.ConversationSnapshot(
            schemaVersion = 1,
            snapshotId = snapshotId,
            chatId = chatId,
            connectionGeneration = connection,
            requestGeneration = request,
            snapshotPurpose = purpose,
            renderRevision = renderRevision,
            committedAt = committedAt,
            transcript = transcript,
            canvas = SnapshotCanvas(target = "canvas", components = Component.listFromJson(componentArray)),
        )
    }

    private fun conversationCommitReadyFromJson(root: JsonObject): Inbound.ConversationCommitReady? {
        if (
            !root.hasExactKeys(
                "type",
                "schema_version",
                "chat_id",
                "connection_generation",
                "request_generation",
                "render_revision",
            ) ||
            root.strictString("type") != "conversation_commit_ready" ||
            root.strictULong("schema_version") != 1UL
        ) {
            return null
        }
        val chatId = canonicalUuid4(root.strictString("chat_id")) ?: return null
        val connection = canonicalUuid4(root.strictString("connection_generation")) ?: return null
        val request = canonicalUuid4(root.strictString("request_generation")) ?: return null
        val revision = root.strictULong("render_revision") ?: return null
        return Inbound.ConversationCommitReady(
            schemaVersion = 1,
            chatId = chatId,
            connectionGeneration = connection,
            requestGeneration = request,
            renderRevision = revision,
        )
    }

    private fun canonicalTranscript(array: JsonArray): List<JsonObject>? {
        val messages = mutableListOf<JsonObject>()
        for (element in array) {
            val message = element as? JsonObject ?: return null
            if (!canonicalTranscriptMessage(message)) return null
            messages += message
        }
        return messages
    }

    private fun canonicalTranscriptMessage(message: JsonObject): Boolean {
        if (!message.hasExactKeys("message_id", "role", "created_at", "parts", "attachments")) return false
        if (message.strictString("message_id").isNullOrEmpty()) return false
        if (message.strictString("role") !in setOf("user", "assistant", "system", "tool")) return false
        if (message.strictString("created_at")?.let(::isRfc3339Utc) != true) return false
        val attachments = message.arr("attachments") ?: return false
        if (attachments.any { it !is JsonObject }) return false
        val parts = message.arr("parts")?.takeIf { it.isNotEmpty() } ?: return false
        return parts.all { part -> (part as? JsonObject)?.let(::canonicalTranscriptPart) == true }
    }

    private fun canonicalTranscriptPart(part: JsonObject): Boolean =
        when (part.strictString("type")) {
            "text" -> part.hasExactKeys("type", "text") && part.strictString("text") != null
            "components" -> {
                val components = part.arr("components")
                part.hasExactKeys("type", "components") &&
                    components != null &&
                    canonicalNativeComponents(components)
            }
            "structured" ->
                part.hasExactKeys("type", "value", "plain_text") && part.strictString("plain_text") != null
            "recovery" ->
                part.hasExactKeys("type", "code", "message") &&
                    !part.strictString("code").isNullOrEmpty() &&
                    !part.strictString("message").isNullOrEmpty()
            else -> false
        }

    /** Native semantic snapshots never accept web-only presentation authority. */
    private fun canonicalNativeComponents(components: JsonArray): Boolean =
        components.all { element ->
            val component = element as? JsonObject ?: return@all false
            val type = component.strictString("type")
            if (type.isNullOrBlank() || "_presentation" in component) return@all false
            val children = component["children"]
            if (children is JsonArray && !canonicalNativeComponents(children)) return@all false
            if (children is JsonObject && !canonicalNativeComponents(JsonArray(listOf(children)))) return@all false
            val content = component["content"]
            when {
                content is JsonObject && content.strictString("type") != null ->
                    canonicalNativeComponents(JsonArray(listOf(content)))
                content is JsonArray &&
                    content.isNotEmpty() &&
                    content.all { (it as? JsonObject)?.strictString("type") != null } ->
                    canonicalNativeComponents(content)
                else -> true
            }
        }

    private fun operationStatusFromJson(root: JsonObject): Inbound.OperationStatus? {
        if (
            !root.hasExactKeys(
                "type",
                "operation_id",
                "action",
                "surface",
                "chat_id",
                "connection_generation",
                "request_generation",
                "sequence",
                "state",
                "phase",
                "label",
                "terminal",
                "retryable",
                "error",
                "retry_after_ms",
                "updated_at",
            ) || root.strictString("type") != "operation_status"
        ) {
            return null
        }
        val operationId = canonicalUuid4(root.strictString("operation_id")) ?: return null
        val action = root.strictString("action")?.takeIf(::isSnakeCase) ?: return null
        val surface = root.strictString("surface")?.takeIf(::isSnakeCase) ?: return null
        val chatId = root.explicitNullableUuid("chat_id") ?: return null
        val connection = canonicalUuid4(root.strictString("connection_generation")) ?: return null
        val request = canonicalUuid4(root.strictString("request_generation")) ?: return null
        val sequence = root.strictULong("sequence") ?: return null
        val state = root.strictString("state") ?: return null
        val phase = root.strictString("phase")?.takeIf(::isSnakeCase) ?: return null
        val label = root.strictString("label")?.takeIf { it.isNotBlank() } ?: return null
        val terminal = root.strictBoolean("terminal") ?: return null
        val retryable = root.strictBoolean("retryable") ?: return null
        if (operationFlags[state] != (terminal to retryable)) return null

        val errorElement = root["error"] ?: return null
        val requiresError = state == "failed" || state == "cancelled" || state == "retryable"
        val error =
            if (requiresError) {
                val value = errorElement as? JsonObject ?: return null
                if (!value.hasExactKeys("code", "message")) return null
                val code = value.strictString("code")?.takeIf(operationErrorCodes::contains) ?: return null
                val message = value.strictString("message")?.takeIf { it.isNotBlank() } ?: return null
                OperationStatusError(code = code, message = message)
            } else {
                if (errorElement !is JsonNull) return null
                null
            }

        val retryAfterElement = root["retry_after_ms"] ?: return null
        val retryAfter =
            if (retryAfterElement is JsonNull) {
                null
            } else {
                if (state != "retryable") return null
                root.strictULong("retry_after_ms") ?: return null
            }
        val updatedAt = root.strictString("updated_at")?.takeIf(::isRfc3339Utc) ?: return null
        return Inbound.OperationStatus(
            operationId = operationId,
            action = action,
            surface = surface,
            chatId = chatId.value,
            connectionGeneration = connection,
            requestGeneration = request,
            sequence = sequence,
            state = state,
            phase = phase,
            label = label,
            terminal = terminal,
            retryable = retryable,
            error = error,
            retryAfterMs = retryAfter,
            updatedAt = updatedAt,
        )
    }

    private fun admissionRefusalFromJson(root: JsonObject): Inbound.AdmissionRefusal? {
        if (
            !root.hasExactKeys(
                "type",
                "submission_id",
                "accepted",
                "code",
                "message",
                "retryable",
                "retry_after_ms",
            ) || root.strictString("type") != "error" || root.strictBoolean("accepted") != false
        ) {
            return null
        }
        val submissionId = canonicalUuid4(root.strictString("submission_id")) ?: return null
        val code = root.strictString("code")?.takeIf(admissionRefusalCodes::contains) ?: return null
        val message = root.strictString("message")?.takeIf { it.isNotBlank() } ?: return null
        val retryable = root.strictBoolean("retryable") ?: return null
        val retryAfterElement = root["retry_after_ms"] ?: return null
        val retryAfter =
            if (retryAfterElement is JsonNull) {
                null
            } else {
                if (!retryable) return null
                root.strictULong("retry_after_ms") ?: return null
            }
        return Inbound.AdmissionRefusal(
            submissionId = submissionId,
            code = code,
            message = message,
            retryable = retryable,
            retryAfterMs = retryAfter,
        )
    }

    private fun agentLifecycleFromJson(root: JsonObject): Inbound.AgentLifecycle? {
        if (
            !root.hasExactKeys(
                "type",
                "agent_id",
                "revision_id",
                "runtime_instance_id",
                "lifecycle_generation",
                "state_revision",
                "state",
                "reason_code",
                "label",
                "updated_at",
            ) || root.strictString("type") != "agent_lifecycle"
        ) {
            return null
        }
        val agentId = root.strictString("agent_id")?.takeIf { it.isNotBlank() } ?: return null
        val revisionId = root.explicitNullableUuid("revision_id") ?: return null
        val runtimeId = root.explicitNullableUuid("runtime_instance_id") ?: return null
        val lifecycleGeneration = root.strictULong("lifecycle_generation") ?: return null
        val stateRevision = root.strictULong("state_revision") ?: return null
        val state =
            root.strictString("state")
                ?.takeIf { it in setOf("starting", "online", "updating", "failed", "offline") }
                ?: return null
        if (state in setOf("starting", "online", "updating") && (revisionId.value == null || runtimeId.value == null)) {
            return null
        }
        val reasonCode = root.explicitNullableString("reason_code") ?: return null
        if (reasonCode.value != null && reasonCode.value !in agentLifecycleReasonCodes) return null
        val label = root.strictString("label")?.takeIf { it.isNotBlank() } ?: return null
        val updatedAt = root.strictString("updated_at")?.takeIf(::isRfc3339Utc) ?: return null
        return Inbound.AgentLifecycle(
            agentId = agentId,
            revisionId = revisionId.value,
            runtimeInstanceId = runtimeId.value,
            lifecycleGeneration = lifecycleGeneration,
            stateRevision = stateRevision,
            state = state,
            reasonCode = reasonCode.value,
            label = label,
            updatedAt = updatedAt,
        )
    }

    private fun agentHostRegistrationFromJson(root: JsonObject): AgentHostRegistration? {
        if (
            !root.hasExactKeys(
                "host_id",
                "supported_runtime_contract_versions",
                "runtime_lock_sha256",
                "platform",
                "client_version",
            )
        ) {
            return null
        }
        val hostId = canonicalUuid4(root.strictString("host_id")) ?: return null
        val versions =
            root.positiveSortedVersions("supported_runtime_contract_versions")?.takeIf { it.isNotEmpty() }
                ?: return null
        val digest = root.strictString("runtime_lock_sha256")?.takeIf(lowerSha256::matches) ?: return null
        val platform = root.strictString("platform")?.takeIf { it == "windows" || it == "macos" } ?: return null
        val clientVersion = root.strictString("client_version")?.takeIf(strictSemVer::matches) ?: return null
        return AgentHostRegistration(hostId, versions, digest, platform, clientVersion)
    }

    private fun agentHostRegisteredFromJson(root: JsonObject): AgentHostRegistered? {
        if (
            !root.hasExactKeys("type", "host_id", "host_session_id", "inventory_required", "accepted_at") ||
            root.strictString("type") != "agent_host_registered"
        ) {
            return null
        }
        val hostId = canonicalUuid4(root.strictString("host_id")) ?: return null
        val hostSessionId = canonicalUuid4(root.strictString("host_session_id")) ?: return null
        val inventoryRequired = root.strictBoolean("inventory_required") ?: return null
        val acceptedAt = root.strictString("accepted_at")?.takeIf(::isRfc3339Utc) ?: return null
        return AgentHostRegistered(hostId, hostSessionId, inventoryRequired, acceptedAt)
    }

    private fun candidateCapabilityMapFromJson(root: JsonObject): CandidateCapabilityMap? {
        if (!root.hasExactKeys("capabilities")) return null
        val capabilities = root.obj("capabilities")?.takeIf { it.hasExactKeys("personal_agent_host") } ?: return null
        val hosts = capabilities.obj("personal_agent_host")?.takeIf { it.hasExactKeys("macos") } ?: return null
        val macos = hosts.obj("macos") ?: return null
        if (!macos.hasExactKeys("supported", "runtime_contract_versions", "source_feature")) return null
        val supported = macos.strictBoolean("supported") ?: return null
        val versions = macos.positiveSortedVersions("runtime_contract_versions") ?: return null
        val source = macos.explicitNullableString("source_feature") ?: return null
        if (supported) {
            if (2 !in versions || source.value != "059") return null
        } else if (versions.isNotEmpty() || source.value != null) {
            return null
        }
        return CandidateCapabilityMap(
            macosPersonalAgentHost =
                PersonalAgentHostCapability(
                    supported = supported,
                    runtimeContractVersions = versions,
                    sourceFeature = source.value,
                ),
        )
    }

    private fun parseObject(raw: String): JsonObject? = runCatching { json.parseToJsonElement(raw) as? JsonObject }.getOrNull()

    private fun JsonObject.hasExactKeys(vararg keys: String): Boolean = this.keys == keys.toSet()

    private fun JsonObject.strictString(key: String): String? = (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

    private fun JsonObject.strictBoolean(key: String): Boolean? = (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonObject.strictULong(key: String): ULong? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.content?.toULongOrNull()

    private fun JsonObject.explicitNullableString(key: String): ExplicitNullable<String>? {
        val element = this[key] ?: return null
        if (element is JsonNull) return ExplicitNullable(null)
        return strictString(key)?.let(::ExplicitNullable)
    }

    private fun JsonObject.explicitNullableUuid(key: String): ExplicitNullable<String>? {
        val element = this[key] ?: return null
        if (element is JsonNull) return ExplicitNullable(null)
        return canonicalUuid4(strictString(key))?.let(::ExplicitNullable)
    }

    private fun JsonObject.positiveSortedVersions(key: String): List<Int>? {
        val values = arr(key) ?: return null
        val versions =
            values.map { element ->
                val primitive = (element as? JsonPrimitive)?.takeIf { !it.isString } ?: return null
                val value = primitive.content.toULongOrNull() ?: return null
                if (value == 0UL || value > Int.MAX_VALUE.toULong()) return null
                value.toInt()
            }
        return versions.takeIf { it == it.distinct().sorted() }
    }

    private fun canonicalUuid4(value: String?): String? {
        if (value == null) return null
        val parsed = runCatching { UUID.fromString(value) }.getOrNull() ?: return null
        return value.takeIf { parsed.version() == 4 && parsed.toString() == value }
    }

    private fun isRfc3339Utc(value: String): Boolean = value.endsWith("Z") && runCatching { Instant.parse(value) }.isSuccess

    private fun isSnakeCase(value: String): Boolean = snakeCase.matches(value)

    // ---- legacy-compatible helpers ----

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

    // components_combined/condensed results are saved-row shapes ({id,
    // component_data, …}); the primitive dict rides in `component_data` and may
    // not carry a workspace identity yet (the reconcile ui_render that follows
    // stamps it), so identity falls back to the fresh row id.
    private fun replacementsFromJson(arr: JsonArray?): List<Component> =
        arr?.mapIndexedNotNull { i, el ->
            val row = el as? JsonObject ?: return@mapIndexedNotNull null
            val data = row.obj("component_data") ?: return@mapIndexedNotNull null
            val comp = Component.fromJson(data)
            if (comp.id != null) comp else comp.copy(id = row.str("id") ?: "combined-$i")
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
