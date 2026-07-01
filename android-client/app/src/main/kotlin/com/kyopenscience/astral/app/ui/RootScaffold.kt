package com.kyopenscience.astral.app.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.kyopenscience.astral.app.R
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.app.ui.theme.AstralColors

private fun glyph(screen: Screen): String =
    when (screen) {
        Screen.Chat -> "💬"
        Screen.Agents -> "🧩"
        Screen.History -> "🕘"
        Screen.Audit -> "🛡"
    }

/**
 * The app root. A compact top bar (brand + surface switcher + New chat) frees the
 * whole bottom of the phone for the chat input, so the SDUI canvas can own 80–90%
 * of the Chat surface. Chat is the adaptive SDUI shell; Agents/History/Audit are
 * native Compose surfaces driven by the existing data actions / REST.
 */
@Composable
fun RootScaffold(vm: AppViewModel, renderer: Renderer) {
    val state by vm.state.collectAsStateWithLifecycle()
    Scaffold(
        topBar = {
            AstralTopBar(
                current = state.screen,
                onNavigate = vm::goTo,
                onNewChat = {
                    vm.newChat()
                    vm.goTo(Screen.Chat)
                },
            )
        },
    ) { padding ->
        // Edge-to-edge (targetSdk 35): pad for the system bars the Scaffold
        // reports, mark them consumed, then let the input rise above the IME.
        Box(modifier = Modifier.fillMaxSize().padding(padding).consumeWindowInsets(padding).imePadding()) {
            when (state.screen) {
                Screen.Chat -> AdaptiveShell(vm, renderer)
                Screen.Agents -> AgentsScreen(state.agents, vm::setAgentEnabled, vm::setToolEnabled, vm::enableRecommended)
                Screen.History -> HistoryScreen(state.history, vm::openChat)
                Screen.Audit -> AuditScreen(state.audit)
            }
        }
    }
}

@Composable
private fun AstralTopBar(current: Screen, onNavigate: (Screen) -> Unit, onNewChat: () -> Unit) {
    Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 2.dp) {
        Row(
            modifier =
                Modifier
                    .fillMaxWidth()
                    .statusBarsPadding()
                    .padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Image(
                painter = painterResource(R.drawable.astral_logo),
                contentDescription = "AstralBody",
                contentScale = ContentScale.Fit,
                modifier = Modifier.height(22.dp).padding(end = 4.dp),
            )
            Box(modifier = Modifier.weight(1f))
            Screen.entries.forEach { sc ->
                NavGlyph(glyph = glyph(sc), selected = current == sc, onClick = { onNavigate(sc) })
            }
            NewChatButton(onClick = onNewChat)
        }
    }
}

@Composable
private fun NavGlyph(glyph: String, selected: Boolean, onClick: () -> Unit) {
    val bg = if (selected) AstralColors.Indigo.copy(alpha = 0.22f) else Color.Transparent
    Box(
        modifier =
            Modifier
                .clip(RoundedCornerShape(10.dp))
                .background(bg)
                .clickable(onClick = onClick)
                .padding(horizontal = 9.dp, vertical = 6.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(glyph, fontSize = 16.sp)
    }
}

@Composable
private fun NewChatButton(onClick: () -> Unit) {
    Box(
        modifier =
            Modifier
                .clip(RoundedCornerShape(14.dp))
                .background(AstralColors.AccentBrush)
                .clickable(onClick = onClick)
                .padding(horizontal = 10.dp, vertical = 6.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text("＋ New", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
    }
}
