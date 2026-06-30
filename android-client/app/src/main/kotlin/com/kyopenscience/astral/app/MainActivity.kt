package com.kyopenscience.astral.app

import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kyopenscience.astral.app.auth.DevAuth
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
                    store.save(state)
                    oidc.freshToken(state)
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
        // Resume an existing session (silent refresh) if one is stored.
        lifecycleScope.launch(Dispatchers.IO) {
            store.load()?.let { st ->
                runCatching { oidc.freshToken(st) }.onSuccess { authToken.value = it }
            }
        }
        setContent {
            AstralTheme {
                val vm: AppViewModel = viewModel(factory = AppViewModel.factory(client, rest))
                val renderer = remember(vm) { Renderer(Emit { a, p -> vm.sendEvent(a, p) }).registerAllRenderers() }
                val token by authToken.collectAsStateWithLifecycle()
                val error by signInError.collectAsStateWithLifecycle()

                if (token == null) {
                    SignInScreen(
                        error = error,
                        devAvailable = DevAuth.devToken != null,
                        onSignIn = ::startSignIn,
                        onDevSignIn = ::devSignIn,
                    )
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
                                    runCatching { store.load()?.let { oidc.freshToken(it) } }.getOrNull()
                                }
                        }
                    }
                    RootScaffold(vm, renderer)
                }
            }
        }
    }

    private fun startSignIn() {
        runCatching { authLauncher.launch(oidc.authorizeIntent()) }
            .onFailure { signInError.value = it.message ?: "could not start sign-in" }
    }

    private fun devSignIn() {
        DevAuth.devToken?.let { authToken.value = it }
    }

    override fun onDestroy() {
        oidc.dispose()
        super.onDestroy()
    }
}

@Composable
private fun SignInScreen(
    error: String?,
    devAvailable: Boolean,
    onSignIn: () -> Unit,
    onDevSignIn: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("AstralBody", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(24.dp))
        Button(onClick = onSignIn) { Text("Sign in") }
        if (devAvailable) {
            TextButton(onClick = onDevSignIn) { Text("Dev sign-in (debug)") }
        }
        error?.let {
            Spacer(Modifier.height(12.dp))
            Text(text = it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        }
    }
}
