package com.personalailabs.astraldeep.app.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import com.personalailabs.astraldeep.app.R
import com.personalailabs.astraldeep.app.render.Renderer
import com.personalailabs.astraldeep.app.ui.theme.AstralColors
import com.personalailabs.astraldeep.core.chrome.ChromeMenuModel
import com.personalailabs.astraldeep.core.chrome.MenuItem
import kotlinx.serialization.json.JsonObject

/**
 * The app root. The top bar is deliberately minimal and identical across clients
 * (feature 042): the small brand logo · a New-chat button · a Recent-chats
 * button · a Settings gear whose dropdown holds ALL settings, built from the
 * single server-owned menu model the orchestrator pushes over `chrome_menu`
 * (Constitution XII — one definition, every client renders it). There is no
 * separate Settings *screen* anymore (it used to duplicate Agents/Audit). Chat
 * is the adaptive SDUI shell; the others are native Compose surfaces.
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
                model = state.chromeMenu,
                onNewChat = {
                    vm.newChat()
                    vm.goTo(Screen.Chat)
                },
                onRecentChats = { vm.goTo(Screen.History) },
                onOpenItem = vm::openMenuItem,
                onOpenSurface = { surface, params -> vm.openSurface(surface, params) },
                onSignOut = onSignOut,
            )
        },
    ) { padding ->
        // Edge-to-edge (targetSdk 35): pad for the system bars the Scaffold
        // reports, mark them consumed, then let the input rise above the IME.
        Column(modifier = Modifier.fillMaxSize().padding(padding).consumeWindowInsets(padding).imePadding()) {
            // Connection + banner strips (feature 044): a degraded connection and
            // server errors/notifications are visible, never silent.
            connectionStripLabel(state.connection, state.everConnected)?.let { ConnectionStrip(it) }
            state.banner?.let {
                BannerBar(text = it, isError = state.bannerKind == "error", onDismiss = vm::dismissBanner)
            }
            Box(modifier = Modifier.fillMaxWidth().weight(1f)) {
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
                    Screen.Surface ->
                        SurfaceScreen(
                            surface = state.pendingSurface,
                            surfaceKey = state.pendingSurfaceKey,
                            renderer = renderer,
                            onRetry = vm::retryPendingSurface,
                        )
                }
            }
        }
    }
}

/** The slim "Reconnecting…" strip shown while a previously-live session is degraded. */
@Composable
private fun ConnectionStrip(label: String) {
    Surface(color = MaterialTheme.colorScheme.surfaceVariant, modifier = Modifier.fillMaxWidth()) {
        Text(
            label,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 12.sp,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 5.dp),
        )
    }
}

/** A dismissible one-line banner for server errors, offline drops, and notifications. */
@Composable
private fun BannerBar(
    text: String,
    isError: Boolean,
    onDismiss: () -> Unit,
) {
    val bg = if (isError) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.surfaceVariant
    val fg = if (isError) MaterialTheme.colorScheme.onErrorContainer else MaterialTheme.colorScheme.onSurface
    Surface(color = bg, modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 14.dp, end = 8.dp, top = 8.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(text, color = fg, fontSize = 13.sp, modifier = Modifier.weight(1f))
            Text(
                "✕",
                color = fg,
                fontSize = 14.sp,
                modifier =
                    Modifier
                        .clip(RoundedCornerShape(10.dp))
                        .clickable(onClick = onDismiss)
                        .padding(horizontal = 8.dp, vertical = 2.dp),
            )
        }
    }
}

@Composable
private fun AstralTopBar(
    model: ChromeMenuModel?,
    onNewChat: () -> Unit,
    onRecentChats: () -> Unit,
    onOpenItem: (MenuItem) -> Unit,
    onOpenSurface: (String, JsonObject) -> Unit,
    onSignOut: () -> Unit,
) {
    Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 2.dp) {
        Row(
            modifier =
                Modifier
                    .fillMaxWidth()
                    .statusBarsPadding()
                    .padding(start = 12.dp, end = 12.dp, top = 8.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            // Small brand logo only — no wordmark, no status text.
            Image(
                painter = painterResource(R.drawable.app_icon),
                contentDescription = "AstralBody",
                modifier = Modifier.size(30.dp).clip(RoundedCornerShape(8.dp)),
            )
            Box(modifier = Modifier.weight(1f))
            // Chat navigation first (form-factor affordances — New/Recent are
            // Android-specific and not part of the server chrome model). Recent
            // chats uses a speech-bubble glyph, NOT the clock — the clock belongs
            // to the server "Workspace timeline" control below, and two clocks
            // side by side read as a duplicate (feature 044 top-bar polish).
            NewChatButton(onClick = onNewChat)
            IconButton(onClick = onRecentChats) {
                Icon(
                    painter = painterResource(R.drawable.ic_chat),
                    contentDescription = "Recent chats",
                    tint = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.size(22.dp),
                )
            }
            // Server-owned chrome cluster on the right (pulse / timeline, feature
            // 042/044 T037): rendered from the model so they're actually reachable
            // — no client hard-coding. Each opens its surface via chrome_open.
            model?.topbarActions?.forEach { control ->
                topBarActionView(control)?.let { view ->
                    IconButton(onClick = { onOpenSurface(view.surface, view.params) }) {
                        Icon(
                            painter = painterResource(topBarActionIcon(view.icon)),
                            contentDescription = view.label,
                            tint = MaterialTheme.colorScheme.onSurface,
                            modifier = Modifier.size(22.dp),
                        )
                    }
                }
            }
            // Settings gear → dropdown with ALL settings (from the server model).
            SettingsMenu(model = model, onOpenItem = onOpenItem, onSignOut = onSignOut)
        }
    }
}

/** Map a resolved top-bar action glyph to a drawable (T037). */
private fun topBarActionIcon(icon: TopBarIcon): Int =
    when (icon) {
        TopBarIcon.SPARKLE -> R.drawable.ic_sparkle
        TopBarIcon.HISTORY -> R.drawable.ic_history
        TopBarIcon.GENERIC -> R.drawable.ic_menu
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
