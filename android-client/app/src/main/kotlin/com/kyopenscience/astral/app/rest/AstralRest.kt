package com.kyopenscience.astral.app.rest

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import okhttp3.OkHttpClient
import okhttp3.Request

/** One row of `GET /api/audit` (the per-user, hash-chained audit log). */
data class AuditEvent(
    val id: String?,
    val eventClass: String?,
    val action: String?,
    val outcome: String?,
    val recordedAt: String?,
)

private val auditJson = Json {
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
        fun pick(vararg keys: String): String? =
            keys.firstNotNullOfOrNull { (o[it] as? JsonPrimitive)?.contentOrNull }
        AuditEvent(
            id = pick("id", "event_id"),
            eventClass = pick("event_class", "class"),
            action = pick("action"),
            outcome = pick("outcome", "result"),
            recordedAt = pick("recorded_at", "created_at", "timestamp"),
        )
    }
}

/** Thin REST client for the read-only surfaces the SDUI wire does not carry. */
class AstralRest(
    private val baseUrl: String,
    private val client: OkHttpClient = OkHttpClient(),
) {
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
}
