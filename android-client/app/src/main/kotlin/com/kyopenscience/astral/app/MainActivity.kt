package com.kyopenscience.astral.app

import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kyopenscience.astral.app.auth.OidcAuth
import com.kyopenscience.astral.app.auth.TokenStore
import com.kyopenscience.astral.app.render.Emit
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.app.render.renderers.registerAllRenderers
import com.kyopenscience.astral.app.rest.AstralRest
import com.kyopenscience.astral.app.transport.ConnectionState
import com.kyopenscience.astral.app.transport.OrchestratorClient
import com.kyopenscience.astral.app.transport.deviceCapabilities
import com.kyopenscience.astral.app.ui.AppViewModel
import com.kyopenscience.astral.app.ui.RootScaffold
import com.kyopenscience.astral.app.ui.theme.AstralColors
import com.kyopenscience.astral.app.ui.theme.AstralTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private val client by lazy { OrchestratorClient(AppConfig.WS_URL) }
    private val rest by lazy { AstralRest(AppConfig.API_BASE) }
    private val oidc by lazy { OidcAuth(this) }
    private val store by lazy { TokenStore(this) }
    private val authToken = MutableStateFlow<String?>(null)
    private val signInError = MutableStateFlow<String?>(null)

    private val authLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            val data = result.data ?: return@registerForActivityResult
            lifecycleScope.launch(Dispatchers.IO) {
                runCatching {
                    val state = oidc.exchange(data)
                    val token = oidc.freshToken(state)
                    store.save(state) // persist AFTER the first refresh (captures rotation)
                    token
                }.onSuccess {
                    authToken.value = it
                    signInError.value = null
                }.onFailure {
                    Log.w("MainActivity", "sign-in exchange failed: ${it.message}")
                    signInError.value = it.message ?: "sign-in failed"
                }
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Resume a cached session. Per the sign-in-once-a-year policy: if credentials
        // are found on the device, go straight to the home screen — show it right away
        // with the cached access token, then refresh silently and PERSIST the (rotated)
        // refresh token so the session survives future cold starts. Only a missing or
        // fully-dead session falls back to the sign-in screen.
        lifecycleScope.launch(Dispatchers.IO) {
            val st = store.load() ?: return@launch
            st.accessToken?.takeIf { it.isNotBlank() }?.let { authToken.value = it }
            runCatching { oidc.freshToken(st) }
                .onSuccess {
                    store.save(st)
                    authToken.value = it
                }
                .onFailure { Log.w("MainActivity", "silent token refresh failed: ${it.message}") }
        }
        setContent {
            AstralTheme {
                val vm: AppViewModel = viewModel(factory = AppViewModel.factory(client, rest))
                val renderer = remember(vm) { Renderer(Emit { a, p -> vm.sendEvent(a, p) }).registerAllRenderers() }
                val token by authToken.collectAsStateWithLifecycle()
                val error by signInError.collectAsStateWithLifecycle()

                if (token == null) {
                    SignInScreen(error = error, onSignIn = ::startSignIn)
                } else {
                    val uiState by vm.state.collectAsStateWithLifecycle()
                    LaunchedEffect(token) {
                        val dm = resources.displayMetrics
                        vm.start(
                            token = token!!,
                            device =
                                deviceCapabilities(
                                    widthPx = dm.widthPixels,
                                    heightPx = dm.heightPixels,
                                    pixelRatio = dm.density.toDouble(),
                                    supportedTypes = renderer.supportedTypes.toList(),
                                ),
                        )
                    }
                    // Mid-session token expiry: silently refresh and reconnect; if the
                    // refresh fails, drop to the sign-in screen (FR-012).
                    LaunchedEffect(uiState.connection) {
                        if (uiState.connection == ConnectionState.AuthRequired) {
                            authToken.value =
                                withContext(Dispatchers.IO) {
                                    store.load()?.let { st ->
                                        runCatching { oidc.freshToken(st).also { store.save(st) } }.getOrNull()
                                    }
                                }
                        }
                    }
                    RootScaffold(vm, renderer, onSignOut = ::signOut)
                }
            }
        }
    }

    private fun startSignIn() {
        runCatching { authLauncher.launch(oidc.authorizeIntent()) }
            .onFailure { signInError.value = it.message ?: "could not start sign-in" }
    }

    /** Sign out: drop the cached session and return to the sign-in screen. */
    private fun signOut() {
        store.clear()
        signInError.value = null
        authToken.value = null
    }

    override fun onDestroy() {
        oidc.dispose()
        super.onDestroy()
    }
}

/**
 * The sign-in landing. Painted on its own [Surface] so content color resolves to
 * the theme's on-background (the earlier bare Column rendered text in the default
 * black, which was invisible on the dark backdrop). The AstralDeep wordmark is the
 * hero; a single gradient "Sign in" launches the Keycloak PKCE flow.
 */
@Composable
private fun SignInScreen(error: String?, onSignIn: () -> Unit) {
    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Box(
            modifier = Modifier.fillMaxSize().background(AstralColors.BackdropBrush).padding(28.dp),
            contentAlignment = Alignment.Center,
        ) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
                modifier = Modifier.widthIn(max = 420.dp).fillMaxWidth(),
            ) {
                Image(
                    painter = painterResource(R.drawable.astral_logo),
                    contentDescription = "AstralDeep",
                    contentScale = ContentScale.Fit,
                    modifier = Modifier.fillMaxWidth(0.78f).height(96.dp),
                )
                Spacer(Modifier.height(14.dp))
                Text(
                    text = "Your adaptive AI workspace",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 15.sp,
                    textAlign = TextAlign.Center,
                )
                Spacer(Modifier.height(40.dp))
                GradientButton(text = "Sign in", onClick = onSignIn)
                error?.let {
                    Spacer(Modifier.height(18.dp))
                    Text(
                        text = it,
                        color = MaterialTheme.colorScheme.error,
                        fontSize = 13.sp,
                        textAlign = TextAlign.Center,
                    )
                }
                Spacer(Modifier.height(28.dp))
                Text(
                    text = "Secured by Keycloak",
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                    fontSize = 12.sp,
                )
            }
        }
    }
}

/** The signature indigo→purple pill button used for the primary sign-in action. */
@Composable
private fun GradientButton(text: String, onClick: () -> Unit) {
    Box(
        modifier =
            Modifier
                .widthIn(min = 220.dp)
                .clip(RoundedCornerShape(26.dp))
                .background(AstralColors.AccentBrush)
                .clickable(onClick = onClick)
                .padding(vertical = 15.dp, horizontal = 32.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text = text, color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
    }
}
