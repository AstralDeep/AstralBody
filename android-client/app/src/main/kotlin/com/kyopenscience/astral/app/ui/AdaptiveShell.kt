package com.kyopenscience.astral.app.ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.window.core.layout.WindowWidthSizeClass
import com.kyopenscience.astral.app.R
import com.kyopenscience.astral.app.render.CanvasHost
import com.kyopenscience.astral.app.render.MarkdownText
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.app.ui.theme.AstralColors
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

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
fun AdaptiveShell(
    vm: AppViewModel,
    renderer: Renderer,
) {
    val state by vm.state.collectAsStateWithLifecycle()
    val width = currentWindowAdaptiveInfo().windowSizeClass.windowWidthSizeClass
    when (layoutModeFor(width)) {
        LayoutMode.Stacked -> StackedShell(state, renderer, vm)
        LayoutMode.Split -> SplitShell(state, renderer, vm)
    }
}

/**
 * Phone layout, top→bottom: the SDUI canvas (the dominant ~85% area), a
 * collapsible "Messages" panel stickied above the input, and the input bar
 * (mic + paperclip). The canvas persists across turns and is only replaced when
 * a new final SDUI commits (see [AppViewModel]).
 */
@Composable
private fun StackedShell(
    state: UiState,
    renderer: Renderer,
    vm: AppViewModel,
) {
    Column(modifier = Modifier.fillMaxSize()) {
        CanvasArea(
            state = state,
            renderer = renderer,
            onSelectSnapshot = vm::viewCanvasSnapshot,
            onBackToLive = vm::backToLiveCanvas,
            modifier = Modifier.fillMaxWidth().weight(1f),
        )
        if (state.turnActive) StepTrail(state.stepTrail)
        MessagesPanel(turns = state.turns, statusText = state.statusText)
        InputBar(
            staged = state.staged,
            readOnly = state.mutationsLocked,
            onSend = vm::sendChat,
            onStageFile = vm::stageAttachment,
            onRemoveAttachment = vm::removeAttachment,
            onOpenAttachments = { vm.openSurface("attachments") },
        )
    }
}

/**
 * Tablet / foldable / landscape layout: a persistent conversation rail beside the
 * canvas. Same input + timeline affordances, reflowed to the wider window.
 */
@Composable
private fun SplitShell(
    state: UiState,
    renderer: Renderer,
    vm: AppViewModel,
) {
    Row(modifier = Modifier.fillMaxSize()) {
        Column(modifier = Modifier.width(360.dp).fillMaxHeight()) {
            PanelHeader("Conversation")
            ChatList(state.turns, Modifier.fillMaxWidth().weight(1f))
            if (state.turnActive) StepTrail(state.stepTrail)
            InputBar(
                staged = state.staged,
                readOnly = state.mutationsLocked,
                onSend = vm::sendChat,
                onStageFile = vm::stageAttachment,
                onRemoveAttachment = vm::removeAttachment,
                onOpenAttachments = { vm.openSurface("attachments") },
            )
        }
        VerticalDivider()
        CanvasArea(
            state = state,
            renderer = renderer,
            onSelectSnapshot = vm::viewCanvasSnapshot,
            onBackToLive = vm::backToLiveCanvas,
            modifier = Modifier.weight(1f).fillMaxHeight(),
        )
    }
}

// ---------------------------------------------------------------------------
// Canvas area: skeleton / empty-state / live canvas + working + timeline chrome
// ---------------------------------------------------------------------------

@Composable
private fun CanvasArea(
    state: UiState,
    renderer: Renderer,
    onSelectSnapshot: (Int) -> Unit,
    onBackToLive: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var showTimeline by remember { mutableStateOf(false) }
    Column(modifier = modifier.background(MaterialTheme.colorScheme.background)) {
        // A read-only banner (history), else a thin progress line for in-place
        // (non-skeleton) turns. During a replacing query the skeleton IS the
        // loading state, and the status text lives only in the Messages bar.
        if (state.isViewingHistory) {
            ReadOnlyBanner(
                label = state.canvasHistory.getOrNull(state.viewingIndex ?: -1)?.label,
                onBackToLive = onBackToLive,
            )
        } else if (state.turnActive && !state.showSkeleton) {
            WorkingBar()
        }

        Box(modifier = Modifier.fillMaxWidth().weight(1f)) {
            when {
                state.showSkeleton -> SkeletonCanvas(Modifier.fillMaxSize())
                state.visibleCanvas.isEmpty() -> EmptyCanvasHint(Modifier.fillMaxSize())
                else -> CanvasHost(components = state.visibleCanvas, renderer = renderer, modifier = Modifier.fillMaxSize())
            }

            // Timeline entry point — only when previous canvases exist and we're live.
            if (state.canvasHistory.isNotEmpty() && !state.isViewingHistory) {
                TimelinePill(
                    count = state.canvasHistory.size,
                    onClick = { showTimeline = true },
                    modifier = Modifier.align(Alignment.TopEnd).padding(12.dp),
                )
            }

            if (showTimeline) {
                CanvasTimelineOverlay(
                    history = state.canvasHistory,
                    onSelect = { idx ->
                        onSelectSnapshot(idx)
                        showTimeline = false
                    },
                    onDismiss = { showTimeline = false },
                )
            }
        }
    }
}

/** A slim, text-free activity line for in-place turns (component actions). */
@Composable
private fun WorkingBar() {
    LinearProgressIndicator(
        modifier = Modifier.fillMaxWidth(),
        color = AstralColors.Purple,
        trackColor = AstralColors.SurfaceVariant,
    )
}

@Composable
private fun ReadOnlyBanner(
    label: String?,
    onBackToLive: () -> Unit,
) {
    Surface(color = AstralColors.Indigo.copy(alpha = 0.16f), modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Icon(
                painter = painterResource(R.drawable.ic_history),
                contentDescription = null,
                tint = AstralColors.Indigo,
                modifier = Modifier.size(16.dp),
            )
            Column(Modifier.weight(1f)) {
                Text(
                    "Viewing a previous canvas",
                    color = MaterialTheme.colorScheme.onSurface,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                if (!label.isNullOrBlank()) {
                    Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp, maxLines = 1)
                }
            }
            Surface(
                color = AstralColors.Indigo,
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier.clickable(onClick = onBackToLive),
            ) {
                Text(
                    "Back to live",
                    color = Color.White,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                )
            }
        }
    }
}

@Composable
private fun TimelinePill(
    count: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.92f),
        shape = RoundedCornerShape(18.dp),
        tonalElevation = 4.dp,
        modifier = modifier.clickable(onClick = onClick),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
        ) {
            Icon(
                painter = painterResource(R.drawable.ic_history),
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurface,
                modifier = Modifier.size(14.dp),
            )
            Text(
                "History ($count)",
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 12.sp,
                fontWeight = FontWeight.Medium,
            )
        }
    }
}

/** A scrim + card listing prior turns' canvases; tapping opens one read-only. */
@Composable
private fun CanvasTimelineOverlay(
    history: List<CanvasSnapshot>,
    onSelect: (Int) -> Unit,
    onDismiss: () -> Unit,
) {
    Box(
        modifier =
            Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.5f)).clickable(onClick = onDismiss),
        contentAlignment = Alignment.BottomCenter,
    ) {
        Surface(
            color = MaterialTheme.colorScheme.surface,
            shape = RoundedCornerShape(topStart = 18.dp, topEnd = 18.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    "Previous canvases",
                    color = MaterialTheme.colorScheme.onSurface,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    "Read-only snapshots from earlier turns in this chat.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                )
                Spacer(Modifier.height(10.dp))
                LazyColumn(
                    modifier = Modifier.fillMaxWidth().heightIn(max = 340.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    // Most-recent first.
                    val indexed = history.indices.reversed().toList()
                    items(indexed) { idx ->
                        val snap = history[idx]
                        Surface(
                            color = MaterialTheme.colorScheme.surfaceVariant,
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.fillMaxWidth().clickable { onSelect(idx) },
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth().padding(14.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(10.dp),
                            ) {
                                Column(Modifier.weight(1f)) {
                                    Text(
                                        snap.label.ifBlank { "Canvas ${idx + 1}" },
                                        color = MaterialTheme.colorScheme.onSurface,
                                        fontSize = 14.sp,
                                        maxLines = 1,
                                    )
                                    Text(
                                        "${snap.components.size} component${if (snap.components.size == 1) "" else "s"}",
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        fontSize = 12.sp,
                                    )
                                }
                                Text("›", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 20.sp)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun EmptyCanvasHint(modifier: Modifier = Modifier) {
    Box(modifier = modifier.padding(32.dp), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("✨", fontSize = 40.sp)
            Spacer(Modifier.height(12.dp))
            Text(
                "Your generated interface appears here",
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 16.sp,
                fontWeight = FontWeight.SemiBold,
                textAlign = TextAlign.Center,
            )
            Spacer(Modifier.height(6.dp))
            Text(
                "Ask something below and AstralDeep will build a live interface for it.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 13.sp,
                textAlign = TextAlign.Center,
            )
        }
    }
}

// ---------------------------------------------------------------------------
// Messages panel (stacked): collapsible bar stickied above the input
// ---------------------------------------------------------------------------

/**
 * The text-only conversation, collapsed by default to a single "Messages" bar
 * that sits right on top of the input bar. It appears as soon as the chat has
 * any content; tapping the bar expands the transcript up over the canvas.
 */
@Composable
private fun MessagesPanel(
    turns: List<ChatTurn>,
    statusText: String?,
) {
    val visible = turns.filter { it.text.isNotBlank() }
    if (visible.isEmpty()) return
    // Appears expanded when the chat first has content; the user can collapse it
    // "down to just a bar" to give the canvas the full screen.
    var expanded by rememberSaveable { mutableStateOf(true) }
    Column(Modifier.fillMaxWidth()) {
        if (expanded) {
            HorizontalDivider(color = MaterialTheme.colorScheme.outline)
            ChatList(
                turns,
                Modifier
                    .fillMaxWidth()
                    .heightIn(max = 320.dp)
                    .background(MaterialTheme.colorScheme.background),
            )
        }
        Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 3.dp) {
            Row(
                modifier =
                    Modifier
                        .fillMaxWidth()
                        .clickable { expanded = !expanded }
                        .padding(horizontal = 16.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(if (expanded) "▼" else "▲", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                Text(
                    "Messages",
                    color = MaterialTheme.colorScheme.onSurface,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                )
                Text("(${visible.size})", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                Spacer(Modifier.weight(1f))
                if (!expanded && !statusText.isNullOrBlank()) {
                    Text(
                        statusText,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 12.sp,
                        maxLines = 1,
                    )
                }
            }
        }
    }
}

/**
 * The running turn's execution trail (chat_step/tool_progress) — a few small
 * muted lines by the status indicator while the orchestrator works (T021).
 */
@Composable
private fun StepTrail(lines: List<String>) {
    if (lines.isEmpty()) return
    Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp)) {
        lines.takeLast(4).forEach { line ->
            Text(
                line,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 11.sp,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun PanelHeader(title: String) {
    Surface(color = MaterialTheme.colorScheme.surface) {
        Text(
            text = title.uppercase(),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp),
        )
    }
}

@Composable
private fun ChatList(
    turns: List<ChatTurn>,
    modifier: Modifier,
) {
    val visible = turns.filter { it.text.isNotBlank() }
    LazyColumn(
        modifier = modifier.padding(horizontal = 12.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        reverseLayout = true,
    ) {
        items(visible.reversed()) { turn -> ChatBubble(turn) }
    }
}

@Composable
private fun ChatBubble(turn: ChatTurn) {
    if (turn.role == "reasoning") {
        ReasoningSnippet(turn.text)
        return
    }
    val isUser = turn.role == "user"
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
    ) {
        // User bubbles follow the shared tinted convention (web `.msg-user`,
        // Apple clients): a translucent primary fill + hairline primary border.
        Surface(
            color =
                if (isUser) {
                    MaterialTheme.colorScheme.primary.copy(alpha = 0.20f)
                } else {
                    MaterialTheme.colorScheme.surfaceVariant
                },
            contentColor = MaterialTheme.colorScheme.onSurface,
            shape = RoundedCornerShape(if (isUser) 10.dp else 16.dp),
            border =
                if (isUser) {
                    BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.30f))
                } else {
                    null
                },
            modifier = if (isUser) Modifier.widthIn(max = 300.dp) else Modifier.fillMaxWidth(0.96f),
        ) {
            Box(modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp)) {
                if (isUser) {
                    Text(turn.text, fontSize = 14.sp)
                } else {
                    MarkdownText(turn.text)
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Input bar: mic (STT) + attachment chips + text field + paperclip + send
// ---------------------------------------------------------------------------

/** Model reasoning shown in the chat window as a collapsed, expandable snippet. */
@Composable
private fun ReasoningSnippet(text: String) {
    var expanded by remember { mutableStateOf(false) }
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth().clickable { expanded = !expanded },
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text(if (expanded) "▼" else "▶", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                Text(
                    "Reasoning",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                )
            }
            if (expanded) {
                Spacer(Modifier.height(6.dp))
                MarkdownText(text)
            }
        }
    }
}

@Composable
private fun InputBar(
    staged: List<StagedAttachment>,
    readOnly: Boolean,
    onSend: (String) -> Unit,
    onStageFile: (String, String?, ByteArray) -> Unit,
    onRemoveAttachment: (Long) -> Unit,
    onOpenAttachments: () -> Unit,
) {
    var input by rememberSaveable { mutableStateOf("") }
    var attachMenuOpen by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val micLauncher =
        rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            val spoken = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()
            if (!spoken.isNullOrBlank()) {
                input = if (input.isBlank()) spoken else "$input $spoken"
            }
        }
    val filePicker =
        rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
            if (uri != null) {
                scope.launch(Dispatchers.IO) {
                    val picked = readPickedFile(context, uri) ?: return@launch
                    val mime = context.contentResolver.getType(uri)
                    withContext(Dispatchers.Main) { onStageFile(picked.first, mime, picked.second) }
                }
            }
        }

    fun launchMic() {
        val intent =
            Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_PROMPT, "Speak your message")
            }
        runCatching { micLauncher.launch(intent) }
    }

    fun doSend() {
        if (input.isBlank() && staged.none { it.state == "ready" }) return
        onSend(input)
        input = ""
    }

    Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 2.dp) {
        Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 8.dp)) {
            // Viewing the read-only timeline pauses composing (T041).
            if (readOnly) {
                Text(
                    "Viewing history — messaging is paused. Return to the live view to continue.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 4.dp),
                )
            }
            if (staged.isNotEmpty()) {
                AttachmentChips(staged, onRemoveAttachment)
                Spacer(Modifier.height(6.dp))
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                GlyphButton(iconRes = R.drawable.ic_mic, contentDescription = "Voice input", enabled = !readOnly, onClick = ::launchMic)
                OutlinedTextField(
                    value = input,
                    onValueChange = { input = it },
                    modifier = Modifier.weight(1f),
                    enabled = !readOnly,
                    placeholder = { Text("Message AstralBody…") },
                    maxLines = 4,
                    shape = RoundedCornerShape(22.dp),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Default),
                )
                // Paperclip → a menu mirroring the web: Upload a file, or Choose
                // from your files (opens the attachments surface, T047).
                Box {
                    GlyphButton(iconRes = R.drawable.ic_paperclip, contentDescription = "Attach a file", enabled = !readOnly) {
                        attachMenuOpen = true
                    }
                    DropdownMenu(expanded = attachMenuOpen, onDismissRequest = { attachMenuOpen = false }) {
                        DropdownMenuItem(
                            text = { Text("Upload a file") },
                            onClick = {
                                attachMenuOpen = false
                                filePicker.launch("*/*")
                            },
                        )
                        DropdownMenuItem(
                            text = { Text("Choose from your files") },
                            onClick = {
                                attachMenuOpen = false
                                onOpenAttachments()
                            },
                        )
                    }
                }
                SendButton(enabled = !readOnly && (input.isNotBlank() || staged.any { it.state == "ready" }), onClick = ::doSend)
            }
        }
    }
}

@Composable
private fun GlyphButton(
    iconRes: Int,
    contentDescription: String,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    val base = MaterialTheme.colorScheme.onSurfaceVariant
    IconButton(onClick = onClick, enabled = enabled) {
        Icon(
            painter = painterResource(iconRes),
            contentDescription = contentDescription,
            tint = if (enabled) base else base.copy(alpha = 0.4f),
            modifier = Modifier.size(22.dp),
        )
    }
}

@Composable
private fun SendButton(
    enabled: Boolean,
    onClick: () -> Unit,
) {
    val bg = if (enabled) AstralColors.Indigo else AstralColors.SurfaceVariant
    Box(
        modifier =
            Modifier
                .size(44.dp)
                .clip(RoundedCornerShape(22.dp))
                .background(bg)
                .clickable(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            painter = painterResource(R.drawable.ic_send),
            contentDescription = "Send",
            tint = if (enabled) Color.White else MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(20.dp),
        )
    }
}

@Composable
private fun AttachmentChips(
    staged: List<StagedAttachment>,
    onRemove: (Long) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        staged.forEach { att ->
            Surface(
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = RoundedCornerShape(14.dp),
            ) {
                Row(
                    modifier = Modifier.padding(start = 10.dp, end = 6.dp, top = 5.dp, bottom = 5.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    val marker =
                        when (att.state) {
                            "uploading" -> "…"
                            "failed" -> "⚠"
                            else -> "📄"
                        }
                    Text(marker, fontSize = 12.sp)
                    Column {
                        Text(
                            att.filename,
                            color = MaterialTheme.colorScheme.onSurface,
                            fontSize = 12.sp,
                            maxLines = 1,
                            modifier = Modifier.widthIn(max = 160.dp),
                        )
                        if (!att.note.isNullOrBlank()) {
                            Text(att.note, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp, maxLines = 1)
                        }
                    }
                    Text(
                        "×",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 16.sp,
                        modifier = Modifier.clickable { onRemove(att.uid) }.padding(horizontal = 4.dp),
                    )
                }
            }
        }
    }
}

/** Read a picked file's display name + bytes off the ContentResolver (IO thread). */
private fun readPickedFile(
    context: Context,
    uri: Uri,
): Pair<String, ByteArray>? =
    runCatching {
        val name =
            context.contentResolver.query(uri, null, null, null, null)?.use { c ->
                val idx = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (idx >= 0 && c.moveToFirst()) c.getString(idx) else null
            } ?: uri.lastPathSegment ?: "file"
        val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: return@runCatching null
        name to bytes
    }.getOrNull()
