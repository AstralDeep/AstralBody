package com.kyopenscience.astral.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kyopenscience.astral.app.render.CanvasHost
import com.kyopenscience.astral.app.render.Emit
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.app.transport.OrchestratorClient
import com.kyopenscience.astral.app.ui.AppViewModel
import com.kyopenscience.astral.app.ui.theme.AstralTheme

class MainActivity : ComponentActivity() {
    private val client by lazy { OrchestratorClient(AppConfig.WS_URL) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            AstralTheme {
                val vm: AppViewModel = viewModel(factory = AppViewModel.factory(client))
                AppShell(vm)
                // US1 (T019–T024) wires OIDC auth + config, then calls
                // vm.start(token, deviceCapabilities(...)) to connect. Until then the
                // shell renders empty (no token); the plumbing below is complete.
            }
        }
    }
}

@Composable
private fun AppShell(vm: AppViewModel) {
    val state by vm.state.collectAsStateWithLifecycle()
    val renderer = remember(vm) { Renderer(Emit { action, payload -> vm.sendEvent(action, payload) }) }
    var input by remember { mutableStateOf("") }

    Scaffold(
        bottomBar = {
            Row(
                modifier = Modifier.fillMaxWidth().padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = input,
                    onValueChange = { input = it },
                    modifier = Modifier.weight(1f),
                    placeholder = { Text("Message AstralBody…") },
                    singleLine = true,
                )
                Button(onClick = {
                    vm.sendChat(input)
                    input = ""
                }, enabled = input.isNotBlank()) {
                    Text("Send")
                }
            }
        },
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding)) {
            state.statusText?.let {
                Text(
                    text = it,
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )
            }
            if (state.turns.isNotEmpty()) {
                LazyColumn(modifier = Modifier.fillMaxWidth().weight(0.4f).padding(horizontal = 16.dp)) {
                    items(state.turns) { turn ->
                        Text(
                            text = (if (turn.role == "user") "You: " else "Assistant: ") + turn.text,
                            modifier = Modifier.padding(vertical = 4.dp),
                        )
                    }
                }
                HorizontalDivider()
            }
            CanvasHost(components = state.canvas, renderer = renderer, modifier = Modifier.weight(1f))
        }
    }
}
