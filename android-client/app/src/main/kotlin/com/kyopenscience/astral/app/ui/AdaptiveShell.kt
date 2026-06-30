package com.kyopenscience.astral.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.VerticalDivider
import androidx.compose.material3.adaptive.currentWindowAdaptiveInfo
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.window.core.layout.WindowWidthSizeClass
import com.kyopenscience.astral.app.render.CanvasHost
import com.kyopenscience.astral.app.render.MarkdownText
import com.kyopenscience.astral.app.render.Renderer

/** How the chat + canvas are arranged for the current window width. */
enum class LayoutMode { Stacked, Split }

/**
 * The single adaptive rule (pure → unit-tested): a compact width (phone portrait)
 * stacks chat over canvas; medium/expanded (tablet, foldable open, landscape)
 * splits into a chat rail + canvas. One UI, reflowing by width.
 */
fun layoutModeFor(width: WindowWidthSizeClass): LayoutMode =
    if (width == WindowWidthSizeClass.COMPACT) LayoutMode.Stacked else LayoutMode.Split

@Composable
fun AdaptiveShell(vm: AppViewModel, renderer: Renderer) {
    val state by vm.state.collectAsStateWithLifecycle()
    val width = currentWindowAdaptiveInfo().windowSizeClass.windowWidthSizeClass
    when (layoutModeFor(width)) {
        LayoutMode.Stacked -> StackedShell(state, renderer, vm::sendChat)
        LayoutMode.Split -> SplitShell(state, renderer, vm::sendChat)
    }
}

@Composable
private fun StackedShell(state: UiState, renderer: Renderer, onSend: (String) -> Unit) {
    Column(modifier = Modifier.fillMaxSize()) {
        StatusLine(state.statusText)
        if (state.turns.isNotEmpty()) {
            ChatList(state.turns, Modifier.fillMaxWidth().weight(0.4f))
            HorizontalDivider()
        }
        CanvasHost(components = state.canvas, renderer = renderer, modifier = Modifier.weight(1f))
        InputBar(onSend)
    }
}

@Composable
private fun SplitShell(state: UiState, renderer: Renderer, onSend: (String) -> Unit) {
    Row(modifier = Modifier.fillMaxSize()) {
        Column(modifier = Modifier.width(360.dp).fillMaxHeight()) {
            StatusLine(state.statusText)
            ChatList(state.turns, Modifier.fillMaxWidth().weight(1f))
            InputBar(onSend)
        }
        VerticalDivider()
        CanvasHost(components = state.canvas, renderer = renderer, modifier = Modifier.weight(1f).fillMaxHeight())
    }
}

@Composable
private fun StatusLine(text: String?) {
    text?.let {
        Text(
            text = it,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
        )
    }
}

@Composable
private fun ChatList(turns: List<ChatTurn>, modifier: Modifier) {
    val visible = turns.filter { it.text.isNotBlank() }
    LazyColumn(
        modifier = modifier.padding(horizontal = 12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(visible) { turn -> ChatBubble(turn) }
    }
}

@Composable
private fun ChatBubble(turn: ChatTurn) {
    val isUser = turn.role == "user"
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
    ) {
        Surface(
            color = if (isUser) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
            contentColor = if (isUser) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
            shape = RoundedCornerShape(16.dp),
            modifier = if (isUser) Modifier.widthIn(max = 300.dp) else Modifier.fillMaxWidth(0.96f),
        ) {
            Box(modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp)) {
                if (isUser) {
                    Text(turn.text, style = MaterialTheme.typography.bodyMedium)
                } else {
                    MarkdownText(turn.text)
                }
            }
        }
    }
}

@Composable
private fun InputBar(onSend: (String) -> Unit) {
    var input by remember { mutableStateOf("") }
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
            onSend(input)
            input = ""
        }, enabled = input.isNotBlank()) {
            Text("Send")
        }
    }
}
