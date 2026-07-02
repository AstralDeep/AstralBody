package com.kyopenscience.astral.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.app.rest.AuditEvent
import com.kyopenscience.astral.app.transport.ConnectionState
import com.kyopenscience.astral.core.protocol.Agent
import com.kyopenscience.astral.core.protocol.ChatSummary
import com.kyopenscience.astral.core.protocol.Inbound
import kotlinx.coroutines.delay
import java.util.concurrent.atomic.AtomicInteger

@Composable
fun AgentsScreen(
    agents: List<Agent>,
    loading: Boolean,
    onToggleAgent: (Agent, Boolean) -> Unit,
    onToggleTool: (Agent, String, Boolean) -> Unit,
    onEnableRecommended: () -> Unit,
) {
    if (loading && agents.isEmpty()) {
        SkeletonList()
        return
    }
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("Agents", style = MaterialTheme.typography.titleLarge)
                Button(onClick = onEnableRecommended) { Text("Enable recommended") }
            }
        }
        items(agents, key = { it.id }) { agent -> AgentCard(agent, onToggleAgent, onToggleTool) }
        if (agents.isEmpty()) {
            item { Text("No agents loaded yet.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}

@Composable
private fun AgentCard(
    agent: Agent,
    onToggleAgent: (Agent, Boolean) -> Unit,
    onToggleTool: (Agent, String, Boolean) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Column(modifier = Modifier.weight(1f).clickable { expanded = !expanded }) {
                    Text(
                        (if (expanded) "▼ " else "▶ ") + agent.name,
                        style = MaterialTheme.typography.titleMedium,
                    )
                    if (agent.description.isNotBlank()) {
                        Text(
                            agent.description,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    val enabled = agent.permissions.values.count { it }
                    Text(
                        "$enabled / ${agent.tools.size} tools enabled",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Switch(
                    checked = agent.permissions.values.any { it },
                    onCheckedChange = { onToggleAgent(agent, it) },
                )
            }
            if (expanded) {
                if (agent.tools.isEmpty()) {
                    Text(
                        "This agent exposes no tools.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                agent.tools.forEach { tool ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(tool, style = MaterialTheme.typography.bodyMedium)
                            agent.toolDescriptions[tool]?.takeIf { it.isNotBlank() }?.let {
                                Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                        Switch(
                            checked = agent.permissions[tool] ?: false,
                            onCheckedChange = { onToggleTool(agent, tool, it) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun HistoryScreen(
    chats: List<ChatSummary>,
    loading: Boolean,
    onOpen: (String) -> Unit,
) {
    if (loading && chats.isEmpty()) {
        SkeletonList()
        return
    }
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(chats, key = { it.id }) { chat ->
            Card(modifier = Modifier.fillMaxWidth().clickable { onOpen(chat.id) }) {
                Text(
                    text = chat.title.ifBlank { "Untitled conversation" },
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.padding(14.dp),
                )
            }
        }
        if (chats.isEmpty()) {
            item { Text("No conversations yet.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}

@Composable
fun AuditScreen(
    events: List<AuditEvent>,
    loading: Boolean,
) {
    if (loading && events.isEmpty()) {
        SkeletonList()
        return
    }
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(events) { event -> AuditCard(event) }
        if (events.isEmpty()) {
            item { Text("No audit events.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}

@Composable
private fun AuditCard(event: AuditEvent) {
    var expanded by remember { mutableStateOf(false) }
    Card(modifier = Modifier.fillMaxWidth().clickable { expanded = !expanded }) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                text = listOfNotNull(event.eventClass, event.action).joinToString(" · ").ifBlank { "event" },
                style = MaterialTheme.typography.titleSmall,
            )
            Text(
                text = listOfNotNull(event.outcome, event.recordedAt).joinToString("  "),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (expanded) {
                event.outcomeDetail?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                event.detail?.let {
                    Text(it, style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace)
                }
                event.id?.let {
                    Text("id: $it", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (event.outcomeDetail == null && event.detail == null) {
                    Text(
                        "No additional detail recorded.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

/** The three states of an SDUI settings surface while/after it is requested (T039). */
enum class SurfaceViewState { Loaded, Loading, TimedOut }

/** Pure state rule: a delivered surface wins; else loading until the timeout fires. */
fun surfaceViewState(
    hasSurface: Boolean,
    timedOut: Boolean,
): SurfaceViewState =
    when {
        hasSurface -> SurfaceViewState.Loaded
        timedOut -> SurfaceViewState.TimedOut
        else -> SurfaceViewState.Loading
    }

/** How long to wait for a `chrome_surface` before offering Retry (T039). */
private const val SURFACE_TIMEOUT_MS = 10_000L

/**
 * Feature 043/044 — a settings surface delivered as SDUI (chrome_surface),
 * rendered natively with the SAME component renderer used for the chat canvas.
 * While waiting, a skeleton shows; if no surface arrives within
 * [SURFACE_TIMEOUT_MS] the screen offers a Retry that re-requests it (T039), so a
 * dropped/blocked surface never leaves an INFINITE skeleton.
 */
@Composable
fun SurfaceScreen(
    surface: Inbound.ChromeSurface?,
    surfaceKey: String,
    renderer: Renderer,
    onRetry: () -> Unit,
) {
    var attempt by remember(surfaceKey) { mutableStateOf(0) }
    var timedOut by remember(surfaceKey) { mutableStateOf(false) }
    val hasSurface = surface != null
    LaunchedEffect(surfaceKey, attempt, hasSurface) {
        if (!hasSurface) {
            timedOut = false
            delay(SURFACE_TIMEOUT_MS)
            timedOut = true
        }
    }
    when (surfaceViewState(hasSurface, timedOut)) {
        SurfaceViewState.Loaded -> SurfaceContent(surface!!, renderer)
        SurfaceViewState.Loading -> SkeletonList()
        SurfaceViewState.TimedOut ->
            SurfaceTimeout(
                onRetry = {
                    attempt += 1 // re-arm the loading timer
                    onRetry()
                },
            )
    }
}

/** Monotonic id per delivered `chrome_surface` frame (drives item-state reset). */
private val surfaceRevision = AtomicInteger()

@Composable
private fun SurfaceContent(
    surface: Inbound.ChromeSurface,
    renderer: Renderer,
) {
    // Each server push is a NEW delivery: scroll back to the top (so a
    // re-render's leading notice — e.g. a failed LLM save — or a guide
    // section's fresh content is actually SEEN) and key every item by the
    // delivery revision so per-item composable state resets. Without the
    // reset, a re-delivered component that compares EQUAL to its predecessor
    // kept its old state — the LLM form stayed stuck on "Saving…" with its
    // buttons gone after an error re-render.
    val revision = remember(surface) { surfaceRevision.incrementAndGet() }
    val listState = rememberLazyListState()
    LaunchedEffect(revision) { listState.scrollToItem(0) }
    LazyColumn(
        state = listState,
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "$revision-title") {
            Text(
                surface.title.ifBlank { "Settings" },
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onSurface,
            )
        }
        itemsIndexed(surface.components, key = { i, _ -> "$revision-$i" }) { _, comp ->
            renderer.render(comp)
        }
    }
}

@Composable
private fun SurfaceTimeout(onRetry: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            "Couldn't load this settings screen",
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurface,
            textAlign = TextAlign.Center,
        )
        Text(
            "The server didn't send it in time. Check your connection and try again.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 8.dp, bottom = 16.dp),
        )
        Button(onClick = onRetry) { Text("Retry") }
    }
}

/** Human-readable connection status shown in the top bar. */
fun connectionLabel(c: ConnectionState): String =
    when (c) {
        ConnectionState.Connected -> "Connected"
        ConnectionState.Connecting -> "Connecting…"
        ConnectionState.Disconnected -> "Disconnected"
        ConnectionState.AuthRequired -> "Re-authenticating…"
    }

/**
 * The slim connection strip's label; null = hidden. Shows only once a session
 * has been live and then degrades — a visible reconnect, never a silent stall
 * (feature 044 T014). Pure → unit-tested.
 */
fun connectionStripLabel(
    c: ConnectionState,
    everConnected: Boolean,
): String? =
    when {
        !everConnected || c == ConnectionState.Connected -> null
        c == ConnectionState.AuthRequired -> connectionLabel(c)
        else -> "Reconnecting…"
    }
