package com.kyopenscience.astral.app.auth

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import net.openid.appauth.AuthState

/**
 * Encrypted persistence for the AppAuth [AuthState] (access + refresh tokens),
 * backed by AndroidX Security `EncryptedSharedPreferences`. Only the refresh
 * token needs to survive process death; the access token is short-lived.
 */
class TokenStore(context: Context) {
    private val prefs =
        EncryptedSharedPreferences.create(
            context,
            FILE,
            MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )

    fun load(): AuthState? =
        prefs.getString(KEY, null)?.let { runCatching { AuthState.jsonDeserialize(it) }.getOrNull() }

    fun save(state: AuthState) {
        prefs.edit().putString(KEY, state.jsonSerializeString()).apply()
    }

    fun clear() {
        prefs.edit().remove(KEY).apply()
    }

    private companion object {
        const val FILE = "astral_auth"
        const val KEY = "auth_state"
    }
}
