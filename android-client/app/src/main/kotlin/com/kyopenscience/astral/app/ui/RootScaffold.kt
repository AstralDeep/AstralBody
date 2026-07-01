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
import com.kyopenscience.astral.core.chrome.ChromeMenuModel
import com.kyopenscience.astral.core.chrome.MenuItem
import com.kyopenscience.astral.core.chrome.TopBarControl

/**
 * The app root. The top bar mirrors the web chrome (feature 042): brand · status ·
 * [Pulse, flag-gated] · Workspace-timeline · Settings gear — the gear opens the
 * grouped Settings dropdown (ACCOUNT / HELP / ADMIN TOOLS + a red Sign out) built
 * from the single server-owned menu model the orchestrator pushes over
 * `chrome_menu` (Constitution XII — one definition, every client renders it). A
 * compact New-chat button is kept as a mobile chat affordance. There is no longer
 * a separate Settings *screen* (which used to duplicate Agents/Audit) — Settings
 * is only this dropdown. Chat is the adaptive SDUI shell; the others are native
 * Compose surfaces.
 */
@Composable
fun RootScaffold(
    vm: AppViewModel,
    renderer: Renderer,
    onSignOut: () -> Unit,
) {
    val state by vm.state.collectAsStateWithLifecycle()
    Scaffold(
        topBar = {
            AstralTopBar(
                state = state,
                onNewChat = {
                    vm.newChat()
                    vm.goTo(Screen.Chat)
                },
                onTopBarAction = vm::openTopBarAction,
                onOpenItem = vm::openMenuItem,
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
                Screen.SurfacePlaceholder -> SurfacePlaceholderScreen(state.pendingSurfaceLabel)
            }
        }
    }
}

@Composable
private fun AstralTopBar(
    state: UiState,
    onNewChat: () -> Unit,
    onTopBarAction: (TopBarControl) -> Unit,
    onOpenItem: (MenuItem) -> Unit,
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
            horizontalArrangement = Arrangement.spacedBy(6.dp),
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
            // Status text — mirrors the web's status span (usually quiet).
            Text(
                connectionLabel(state.connection),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 11.sp,
                maxLines = 1,
            )
            Box(modifier = Modifier.weight(1f))
            // Model-driven top-bar action controls, in order: Pulse (only present
            // when the server enables FF_PULSE_DIGEST) then Workspace timeline.
            state.chromeMenu?.topbarActions?.forEach { control ->
                TopBarActionButton(control = control, onClick = { onTopBarAction(control) })
            }
            NewChatButton(onClick = onNewChat)
            SettingsMenu(model = state.chromeMenu, onOpenItem = onOpenItem, onSignOut = onSignOut)
        }
    }
}

/** An icon button for a model top-bar action control (Pulse / Workspace timeline). */
@Composable
private fun TopBarActionButton(
    control: TopBarControl,
    onClick: () -> Unit,
) {
    IconButton(onClick = onClick) {
        Icon(
            painter = painterResource(iconResFor(control.icon)),
            contentDescription = control.label,
            tint = MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.size(20.dp),
        )
    }
}

/**
 * The Settings gear + its dropdown, rendered from the server-owned model.
 * `internal` so the instrumented UI test can drive it without real auth.
 */
@Composable
internal fun SettingsMenu(
    model: ChromeMenuModel?,
    onOpenItem: (MenuItem) -> Unit,
    onSignOut: () -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    Box {
        IconButton(onClick = { open = true }) {
            Icon(
                painter = painterResource(R.drawable.ic_settings),
                contentDescription = "Settings",
                tint = MaterialTheme.colorScheme.onSurface,
                modifier = Modifier.size(22.dp),
            )
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            model?.menu?.forEach { group ->
                SectionHeader(group.label)
                group.items.forEach { item ->
                    DropdownMenuItem(
                        text = { Text(item.label, color = MaterialTheme.colorScheme.onSurface) },
                        onClick = {
                            open = false
                            onOpenItem(item)
                        },
                    )
                }
            }
            HorizontalDivider(color = MaterialTheme.colorScheme.outline)
            DropdownMenuItem(
                text = { Text(model?.signout?.label ?: "Sign out", color = MaterialTheme.colorScheme.error) },
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
private fun SectionHeader(label: String) {
    Text(
        label.uppercase(),
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
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

/** Map a model icon id (gear/history/sparkle) to a client drawable. */
private fun iconResFor(iconId: String?): Int =
    when (iconId) {
        "history" -> R.drawable.ic_history
        "gear" -> R.drawable.ic_settings
        // "sparkle" (Pulse) has no dedicated asset yet; the history glyph reads as
        // "what happened" and Pulse is flag-gated off by default anyway.
        else -> R.drawable.ic_history
    }
