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
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.kyopenscience.astral.app.rest.AuditEvent
import com.kyopenscience.astral.app.transport.ConnectionState
import com.kyopenscience.astral.core.protocol.Agent
import com.kyopenscience.astral.core.protocol.ChatSummary

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

/**
 * Placeholder for a settings surface not yet rendered natively on Android. The
 * menu item is present (matching the web exactly, feature 042); its SDUI surface
 * arrives in P2. FR-013 graceful degradation — a labeled placeholder, never a
 * blank or broken screen.
 */
@Composable
fun SurfacePlaceholderScreen(label: String) {
    Column(
        modifier = Modifier.fillMaxSize().padding(28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            label.ifBlank { "Settings" },
            style = MaterialTheme.typography.titleLarge,
            color = MaterialTheme.colorScheme.onSurface,
        )
        Text(
            "This settings screen is coming to the Android app soon.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 10.dp),
        )
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
