package com.kyopenscience.astral.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.kyopenscience.astral.app.render.Renderer

private fun glyph(screen: Screen): String =
    when (screen) {
        Screen.Chat -> "💬"
        Screen.Agents -> "🧩"
        Screen.History -> "🕘"
        Screen.Audit -> "🛡"
    }

/**
 * The app root: a bottom NavigationBar over the four v1 surfaces. Chat is the
 * adaptive SDUI shell; Agents/History/Audit are native Compose surfaces driven by
 * the existing data actions / REST (never the web `chrome_render`, which the
 * client acknowledges but cannot embed).
 */
@Composable
fun RootScaffold(vm: AppViewModel, renderer: Renderer) {
    val state by vm.state.collectAsStateWithLifecycle()
    Scaffold(
        bottomBar = {
            NavigationBar {
                Screen.entries.forEach { sc ->
                    NavigationBarItem(
                        selected = state.screen == sc,
                        onClick = { vm.goTo(sc) },
                        icon = { Text(glyph(sc)) },
                        label = { Text(sc.name) },
                    )
                }
            }
        },
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            when (state.screen) {
                Screen.Chat -> AdaptiveShell(vm, renderer)
                Screen.Agents -> AgentsScreen(state.agents, vm::setToolEnabled, vm::enableRecommended)
                Screen.History -> HistoryScreen(state.history, vm::openChat)
                Screen.Audit -> AuditScreen(state.audit)
            }
        }
    }
}
