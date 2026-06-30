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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.kyopenscience.astral.app.rest.AuditEvent
import com.kyopenscience.astral.core.protocol.Agent
import com.kyopenscience.astral.core.protocol.ChatSummary

@Composable
fun AgentsScreen(agents: List<Agent>, onToggle: (Agent, Boolean) -> Unit, onEnableRecommended: () -> Unit) {
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
        items(agents, key = { it.id }) { agent ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(agent.name, style = MaterialTheme.typography.titleMedium)
                        if (agent.description.isNotBlank()) {
                            Text(
                                agent.description,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    Switch(checked = agent.scopes.values.any { it }, onCheckedChange = { onToggle(agent, it) })
                }
            }
        }
        if (agents.isEmpty()) {
            item { Text("No agents loaded yet.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}

@Composable
fun HistoryScreen(chats: List<ChatSummary>, onOpen: (String) -> Unit) {
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
fun AuditScreen(events: List<AuditEvent>) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(events) { event ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text(
                        text = listOfNotNull(event.eventClass, event.action).joinToString(" · ").ifBlank { "event" },
                        style = MaterialTheme.typography.titleSmall,
                    )
                    Text(
                        text = listOfNotNull(event.outcome, event.recordedAt).joinToString("  "),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        if (events.isEmpty()) {
            item { Text("No audit events.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}
