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
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.kyopenscience.astral.app.R
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.app.ui.theme.AstralColors

/**
 * The app root. A compact top bar (app-icon brand + New chat + a hamburger menu)
 * frees the whole bottom of the phone for the chat input, so the SDUI canvas can
 * own 80–90% of the Chat surface. The hamburger holds navigation (Home / Agents /
 * History / Audit), Settings, and Sign out — mirroring the web settings menu. Chat
 * is the adaptive SDUI shell; the others are native Compose surfaces.
 */
@Composable
fun RootScaffold(vm: AppViewModel, renderer: Renderer, onSignOut: () -> Unit) {
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
                onSignOut = onSignOut,
            )
        },
    ) { padding ->
        // Edge-to-edge (targetSdk 35): pad for the system bars the Scaffold
        // reports, mark them consumed, then let the input rise above the IME.
        Box(modifier = Modifier.fillMaxSize().padding(padding).consumeWindowInsets(padding).imePadding()) {
            when (state.screen) {
                Screen.Chat -> AdaptiveShell(vm, renderer)
                Screen.Agents ->
                    AgentsScreen(
                        state.agents,
                        state.agentsLoading,
                        vm::setAgentEnabled,
                        vm::setToolEnabled,
                        vm::enableRecommended,
                    )
                Screen.History -> HistoryScreen(state.history, state.historyLoading, vm::openChat)
                Screen.Audit -> AuditScreen(state.audit, state.auditLoading)
                Screen.Settings ->
                    SettingsScreen(
                        connection = state.connection,
                        onOpenAgents = { vm.goTo(Screen.Agents) },
                        onOpenAudit = { vm.goTo(Screen.Audit) },
                    )
            }
        }
    }
}

@Composable
private fun AstralTopBar(
    current: Screen,
    onNavigate: (Screen) -> Unit,
    onNewChat: () -> Unit,
    onSignOut: () -> Unit,
) {
    Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 2.dp) {
        Row(
            modifier =
                Modifier
                    .fillMaxWidth()
                    .statusBarsPadding()
                    .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Image(
                painter = painterResource(R.drawable.app_icon),
                contentDescription = "AstralBody",
                modifier = Modifier.size(28.dp).clip(RoundedCornerShape(8.dp)),
            )
            Text(
                "AstralBody",
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 16.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Box(modifier = Modifier.weight(1f))
            NewChatButton(onClick = onNewChat)
            HamburgerMenu(current = current, onNavigate = onNavigate, onSignOut = onSignOut)
        }
    }
}

@Composable
private fun HamburgerMenu(current: Screen, onNavigate: (Screen) -> Unit, onSignOut: () -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        IconButton(onClick = { open = true }) {
            Icon(
                painter = painterResource(R.drawable.ic_menu),
                contentDescription = "Menu",
                tint = MaterialTheme.colorScheme.onSurface,
                modifier = Modifier.size(22.dp),
            )
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            MenuItem("Home", R.drawable.ic_chat, current == Screen.Chat) { open = false; onNavigate(Screen.Chat) }
            MenuItem("Agents", R.drawable.ic_agents, current == Screen.Agents) { open = false; onNavigate(Screen.Agents) }
            MenuItem("History", R.drawable.ic_history, current == Screen.History) { open = false; onNavigate(Screen.History) }
            MenuItem("Audit", R.drawable.ic_audit, current == Screen.Audit) { open = false; onNavigate(Screen.Audit) }
            HorizontalDivider(color = MaterialTheme.colorScheme.outline)
            MenuItem("Settings", R.drawable.ic_settings, current == Screen.Settings) { open = false; onNavigate(Screen.Settings) }
            DropdownMenuItem(
                text = { Text("Sign out", color = MaterialTheme.colorScheme.error) },
                leadingIcon = {
                    Icon(
                        painter = painterResource(R.drawable.ic_signout),
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.error,
                        modifier = Modifier.size(20.dp),
                    )
                },
                onClick = {
                    open = false
                    onSignOut()
                },
            )
        }
    }
}

@Composable
private fun MenuItem(label: String, iconRes: Int, selected: Boolean, onClick: () -> Unit) {
    val accent = AstralColors.Indigo
    DropdownMenuItem(
        text = {
            Text(
                label,
                color = if (selected) accent else MaterialTheme.colorScheme.onSurface,
                fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
            )
        },
        leadingIcon = {
            Icon(
                painter = painterResource(iconRes),
                contentDescription = null,
                tint = if (selected) accent else MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(20.dp),
            )
        },
        onClick = onClick,
    )
}

@Composable
private fun NewChatButton(onClick: () -> Unit) {
    Row(
        modifier =
            Modifier
                .clip(RoundedCornerShape(14.dp))
                .background(AstralColors.AccentBrush)
                .clickable(onClick = onClick)
                .padding(horizontal = 11.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Icon(
            painter = painterResource(R.drawable.ic_plus),
            contentDescription = null,
            tint = Color.White,
            modifier = Modifier.size(14.dp),
        )
        Text("New", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
    }
}
