package com.kyopenscience.astral.app.rest

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/** One row of `GET /api/audit` (the per-user, hash-chained audit log). */
data class AuditEvent(
    val id: String?,
    val eventClass: String?,
    val action: String?,
    val outcome: String?,
    val recordedAt: String?,
    val outcomeDetail: String? = null,
    /** Compact inputs/outputs metadata for the expanded detail view. */
    val detail: String? = null,
)

private val auditJson =
    Json {
        ignoreUnknownKeys = true
        isLenient = true
    }

/**
 * Tolerant shaping of the `/api/audit` body — accepts a top-level array or an
 * object wrapping the rows under `events`/`items`/`data`, and reads each row's
 * fields under a few likely key spellings. Pure → unit-tested.
 */
fun parseAudit(raw: String): List<AuditEvent> {
    val root = runCatching { auditJson.parseToJsonElement(raw) }.getOrNull() ?: return emptyList()
    val arr: JsonArray =
        when (root) {
            is JsonArray -> root
            is JsonObject -> (root["events"] ?: root["items"] ?: root["data"]) as? JsonArray ?: JsonArray(emptyList())
            else -> JsonArray(emptyList())
        }
    return arr.mapNotNull { it as? JsonObject }.map { o ->
        fun pick(vararg keys: String): String? = keys.firstNotNullOfOrNull { (o[it] as? JsonPrimitive)?.contentOrNull }
        AuditEvent(
            id = pick("id", "event_id"),
            eventClass = pick("event_class", "class"),
            action = pick("action_type", "action"),
            outcome = pick("outcome", "result"),
            recordedAt = pick("recorded_at", "created_at", "timestamp"),
            outcomeDetail = pick("outcome_detail"),
            detail = metaSummary(o),
        )
    }
}

private fun metaSummary(o: JsonObject): String? {
    val parts = mutableListOf<String>()
    (o["inputs_meta"] as? JsonObject)?.let { if (it.isNotEmpty()) parts.add("inputs: $it") }
    (o["outputs_meta"] as? JsonObject)?.let { if (it.isNotEmpty()) parts.add("outputs: $it") }
    return parts.joinToString("\n").ifBlank { null }
}

/** Metadata returned by `POST /api/upload` for a staged attachment (feature 031). */
data class AttachmentUpload(
    val attachmentId: String,
    val filename: String,
    val category: String,
    /** covered | preparing | pending_admin_approval | unavailable */
    val parserStatus: String?,
)

/** Thin REST client for the read-only surfaces the SDUI wire does not carry. */
class AstralRest(
    private val baseUrl: String,
    private val client: OkHttpClient = OkHttpClient(),
) {
    /**
     * Upload a single file to `POST /api/upload` (multipart `file` field, Bearer
     * auth) — the exact contract the web client uses. Returns the new
     * attachment's metadata (id/category/parser_status) or null on any failure.
     */
    suspend fun uploadAttachment(
        token: String,
        filename: String,
        mimeType: String?,
        bytes: ByteArray,
    ): AttachmentUpload? =
        withContext(Dispatchers.IO) {
            val media = (mimeType ?: "application/octet-stream").toMediaTypeOrNull()
            val body =
                MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart("file", filename, bytes.toRequestBody(media))
                    .build()
            val request =
                Request.Builder()
                    .url("${baseUrl.trimEnd('/')}/api/upload")
                    .header("Authorization", "Bearer $token")
                    .post(body)
                    .build()
            runCatching {
                client.newCall(request).execute().use { resp ->
                    val raw = resp.body?.string().orEmpty()
                    if (!resp.isSuccessful) return@use null
                    val o = auditJson.parseToJsonElement(raw) as? JsonObject ?: return@use null
                    val id = (o["attachment_id"] as? JsonPrimitive)?.contentOrNull ?: return@use null
                    AttachmentUpload(
                        attachmentId = id,
                        filename = (o["filename"] as? JsonPrimitive)?.contentOrNull ?: filename,
                        category = (o["category"] as? JsonPrimitive)?.contentOrNull ?: "file",
                        parserStatus = (o["parser_status"] as? JsonPrimitive)?.contentOrNull,
                    )
                }
            }.getOrNull()
        }

    suspend fun audit(token: String): List<AuditEvent> =
        withContext(Dispatchers.IO) {
            val request =
                Request.Builder()
                    .url("${baseUrl.trimEnd('/')}/api/audit")
                    .header("Authorization", "Bearer $token")
                    .build()
            client.newCall(request).execute().use { resp ->
                if (!resp.isSuccessful) emptyList() else parseAudit(resp.body?.string().orEmpty())
            }
        }

    /**
     * Toggle one tool's permission for the current user (feature-013 per-(tool,
     * kind) shape): PUT /api/agents/{id}/permissions
     * `{per_tool_permissions: {tool: {kind: enabled}}}`. Granular — does not touch
     * the agent's other tools. Returns true on a 2xx.
     */
    suspend fun setToolPermission(
        token: String,
        agentId: String,
        tool: String,
        kind: String,
        enabled: Boolean,
    ): Boolean =
        withContext(Dispatchers.IO) {
            val body =
                buildJsonObject {
                    putJsonObject("per_tool_permissions") {
                        putJsonObject(tool) { put(kind, enabled) }
                    }
                }.toString()
            val request =
                Request.Builder()
                    .url("${baseUrl.trimEnd('/')}/api/agents/$agentId/permissions")
                    .header("Authorization", "Bearer $token")
                    .put(body.toRequestBody("application/json".toMediaType()))
                    .build()
            client.newCall(request).execute().use { it.isSuccessful }
        }
}
