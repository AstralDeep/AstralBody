package com.personalailabs.astraldeep.app.auth

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import java.security.MessageDigest
import java.time.Instant
import java.util.Base64
import java.util.UUID

/**
 * Durable, non-secret active-conversation locator for Android.
 *
 * Account identity appears only as a SHA-256 storage-key suffix. Values contain
 * exactly the versioned chat UUID and update time; credentials, transcript,
 * canvas, endpoint, and display identity are never persisted here. Android's
 * synchronous [SharedPreferences.Editor.commit] is used so a selection is
 * durable before registration or `load_chat` is sent.
 */
class ConversationResumeStore internal constructor(
    private val storage: Storage,
    private val clock: () -> Instant = { Instant.now() },
) {
    /** Production adapter over one private Android preferences file. */
    constructor(context: Context) : this(
        SharedPreferencesStorage(
            context.applicationContext.getSharedPreferences(FILE_NAME, Context.MODE_PRIVATE),
        ),
    )

    /** Stable authenticated account identity used only to derive an opaque key. */
    data class AccountIdentity(val issuer: String, val subject: String) {
        init {
            require(issuer.isNotBlank()) { "issuer must not be blank" }
            require(subject.isNotBlank()) { "subject must not be blank" }
        }
    }

    /** Version-one locator value. */
    data class Locator(val chatId: String, val updatedAt: Instant, val schemaVersion: Int = SCHEMA_VERSION)

    /** The complete allowlist of state transitions authorized to remove a locator. */
    enum class ClearReason {
        EXPLICIT_NEW_CHAT,
        DEFINITIVE_SIGN_OUT,
        ACCOUNT_SWITCH_OR_REMOVAL,
        CONFIRMED_DELETION,
    }

    /** Minimal storage contract keeps locator parsing and persistence JVM-testable. */
    internal interface Storage {
        fun get(key: String): String?

        fun put(
            key: String,
            value: String,
        ): Boolean

        fun remove(key: String): Boolean
    }

    /**
     * Read the current v1 locator. Unknown versions and malformed values remain
     * untouched and are not interpreted, preserving a future migration path.
     */
    fun load(account: AccountIdentity): Locator? {
        val raw = storage.get(storageKey(account)) ?: return null
        val value =
            runCatching { JSON.parseToJsonElement(raw).jsonObject }
                .onFailure { Log.w(TAG, "Ignoring unreadable conversation locator") }
                .getOrNull() ?: return null
        val version = value.strictInt("schema_version") ?: return null
        if (version != SCHEMA_VERSION) {
            Log.i(TAG, "Retaining unsupported conversation locator schema=$version")
            return null
        }
        if (value.keys != VALUE_FIELDS) return null
        val chatId = canonicalUuid4(value.strictString("chat_id")) ?: return null
        val updatedAt = value.strictString("updated_at")?.let(::parseUtcInstant) ?: return null
        return Locator(chatId = chatId, updatedAt = updatedAt)
    }

    /** Persist [chatId] atomically before it becomes the intentionally active chat. */
    fun save(
        account: AccountIdentity,
        chatId: String,
    ): Boolean {
        val canonical = canonicalUuid4(chatId) ?: return false
        val value =
            buildJsonObject {
                put("schema_version", SCHEMA_VERSION)
                put("chat_id", canonical)
                put("updated_at", clock().toString())
            }.toString()
        return storage.put(storageKey(account), value).also { saved ->
            if (!saved) Log.w(TAG, "Conversation locator commit failed")
        }
    }

    /** Remove only this account's locator for one explicit allowlisted transition. */
    fun clear(
        account: AccountIdentity,
        reason: ClearReason,
    ): Boolean =
        storage.remove(storageKey(account)).also { removed ->
            if (removed) {
                Log.i(TAG, "Conversation locator cleared reason=${reason.name.lowercase()}")
            } else {
                Log.w(TAG, "Conversation locator clear failed reason=${reason.name.lowercase()}")
            }
        }

    private fun JsonObject.strictString(key: String): String? = (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.strictInt(key: String): Int? = (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull

    private class SharedPreferencesStorage(private val preferences: SharedPreferences) : Storage {
        override fun get(key: String): String? = preferences.getString(key, null)

        override fun put(
            key: String,
            value: String,
        ): Boolean = preferences.edit().putString(key, value).commit()

        override fun remove(key: String): Boolean = preferences.edit().remove(key).commit()
    }

    companion object {
        private const val TAG = "ConversationResume"
        private const val FILE_NAME = "astraldeep_conversation_resume"
        private const val SCHEMA_VERSION = 1
        private val VALUE_FIELDS = setOf("schema_version", "chat_id", "updated_at")
        private val JSON = Json { isLenient = false }

        /** Contract key: SHA-256(UTF8(issuer) || NUL || UTF8(subject)). */
        fun storageKey(account: AccountIdentity): String {
            val digest = MessageDigest.getInstance("SHA-256")
            digest.update(account.issuer.encodeToByteArray())
            digest.update(0)
            digest.update(account.subject.encodeToByteArray())
            return "astraldeep.active_chat.v1.${digest.digest().toHex()}"
        }

        /**
         * Extract Keycloak's issuer/subject claims from an already-authenticated
         * access token. This does not authenticate the token; AppAuth and the
         * server own authentication. It only derives the non-secret storage key.
         */
        fun accountFromAccessToken(token: String): AccountIdentity? {
            val segments = token.split('.')
            if (segments.size != 3) return null
            val payload =
                runCatching { Base64.getUrlDecoder().decode(segments[1]).decodeToString() }
                    .getOrNull() ?: return null
            val claims =
                runCatching { JSON.parseToJsonElement(payload).jsonObject }
                    .getOrNull() ?: return null
            val issuer = (claims["iss"] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
            val subject = (claims["sub"] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
            if (issuer.isNullOrBlank() || subject.isNullOrBlank()) return null
            return AccountIdentity(issuer, subject)
        }

        private fun canonicalUuid4(value: String?): String? {
            if (value == null) return null
            val parsed = runCatching { UUID.fromString(value) }.getOrNull() ?: return null
            return value.takeIf { parsed.version() == 4 && parsed.toString() == value }
        }

        private fun parseUtcInstant(value: String): Instant? =
            value.takeIf { it.endsWith('Z') }?.let { runCatching { Instant.parse(it) }.getOrNull() }

        private fun ByteArray.toHex(): String = joinToString(separator = "") { byte -> "%02x".format(byte) }
    }
}
