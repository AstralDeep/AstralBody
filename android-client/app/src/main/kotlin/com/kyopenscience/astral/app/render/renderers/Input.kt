package com.kyopenscience.astral.app.render.renderers

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import com.kyopenscience.astral.app.render.Download
import com.kyopenscience.astral.app.render.Emit
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.app.render.ThemeSink
import com.kyopenscience.astral.app.ui.theme.channelSwatchOptions
import com.kyopenscience.astral.app.ui.theme.hexToColor
import com.kyopenscience.astral.core.sdui.Component
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject

/** How long a ParamPicker shows "Saving…" before restoring its buttons when no
 *  surface re-render arrives (the server normally replies well within this). */
private const val SUBMIT_FAILSAFE_MS = 12_000L

/** Register the input/code/file primitives (US2). */
fun Renderer.registerInputRenderers(): Renderer =
    apply {
        register("input") { c -> InputPrimitive(c, emit) }
        register("param_picker") { c -> ParamPickerPrimitive(c, emit) }
        register("color_picker") { c -> ColorPickerPrimitive(c, emit, theme) }
        register("theme_apply") { c -> ThemeApplyPrimitive(c, theme) } // US5: apply the emitted palette live
        register("code") { c -> CodePrimitive(c) }
        register("file_upload") { c -> FileActionButton(c, emit, c.str("label") ?: "Upload") }
        register("file_download") { c -> FileDownloadPrimitive(c, download) }
        register("download_card") { c -> FileDownloadPrimitive(c, download) }
    }

@Composable
private fun InputPrimitive(
    c: Component,
    emit: Emit,
) {
    var value by remember { mutableStateOf(c.str("value").orEmpty()) }
    val action = c.str("action")
    OutlinedTextField(
        value = value,
        onValueChange = { value = it },
        modifier = Modifier.fillMaxWidth(),
        label = c.str("label")?.let { { Text(it) } },
        singleLine = true,
        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
        keyboardActions =
            KeyboardActions(
                onDone = { if (action != null) emit.event(action, buildJsonObject { put("value", value) }) },
            ),
    )
}

/**
 * Feature 043 — a settings form. Renders each field (text / password / textarea /
 * boolean / select→text) with collected state and one or more action buttons that
 * post the SAME `{fields: {...}}` payload to a `chrome_*` handler (action-submit),
 * or the single `submit_action`. Falls back to the legacy single-action button.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ParamPickerPrimitive(
    c: Component,
    emit: Emit,
) {
    val fields = c.arr("fields")?.mapNotNull { it as? JsonObject } ?: emptyList()
    val texts =
        remember(c) {
            mutableStateMapOf<String, String>().apply {
                fields.forEach { f ->
                    val name = (f["name"] as? JsonPrimitive)?.contentOrNull ?: return@forEach
                    if ((f["kind"] as? JsonPrimitive)?.contentOrNull != "boolean") {
                        put(name, (f["default"] as? JsonPrimitive)?.contentOrNull ?: "")
                    }
                }
            }
        }
    val bools =
        remember(c) {
            mutableStateMapOf<String, Boolean>().apply {
                fields.forEach { f ->
                    val name = (f["name"] as? JsonPrimitive)?.contentOrNull ?: return@forEach
                    if ((f["kind"] as? JsonPrimitive)?.contentOrNull == "boolean") {
                        put(name, (f["default"] as? JsonPrimitive)?.booleanOrNull ?: false)
                    }
                }
            }
        }

    fun collect(extra: JsonObject) =
        buildJsonObject {
            putJsonObject("fields") {
                fields.forEach { f ->
                    val name = (f["name"] as? JsonPrimitive)?.contentOrNull ?: return@forEach
                    if ((f["kind"] as? JsonPrimitive)?.contentOrNull == "boolean") {
                        put(name, bools[name] ?: false)
                    } else {
                        put(name, texts[name] ?: "")
                    }
                }
            }
            extra.forEach { (k, v) -> put(k, v) }
        }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            c.str("title")?.takeIf { it.isNotBlank() }?.let {
                Text(it, style = MaterialTheme.typography.titleSmall)
            }
            fields.forEach { f ->
                val name = (f["name"] as? JsonPrimitive)?.contentOrNull ?: return@forEach
                val label = (f["label"] as? JsonPrimitive)?.contentOrNull ?: name
                val kind = (f["kind"] as? JsonPrimitive)?.contentOrNull ?: "text"
                if (kind == "boolean") {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Switch(checked = bools[name] ?: false, onCheckedChange = { bools[name] = it })
                        Text(label, modifier = Modifier.padding(start = 8.dp))
                    }
                } else {
                    OutlinedTextField(
                        value = texts[name] ?: "",
                        onValueChange = { texts[name] = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text(label) },
                        singleLine = kind != "textarea",
                        visualTransformation =
                            if (kind == "password") PasswordVisualTransformation() else VisualTransformation.None,
                    )
                }
                (f["help"] as? JsonPrimitive)?.contentOrNull?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            val actions = c.arr("actions")?.mapNotNull { it as? JsonObject } ?: emptyList()
            // The submit is fire-and-forget (the server re-pushes the surface on
            // success, replacing this component). Until then show a transient
            // "Saving…" so a tap is never silent (T039); a new surface resets it
            // (SurfaceContent keys items per delivery), and a lost/failed
            // re-render restores the buttons after a bounded wait — the form
            // must never be stuck spinner-only with no way to resubmit.
            var submitting by remember(c) { mutableStateOf(false) }
            if (submitting) {
                LaunchedEffect(Unit) {
                    kotlinx.coroutines.delay(SUBMIT_FAILSAFE_MS)
                    submitting = false
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                    Text("Saving…", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            } else {
                // Wrap, never overflow: three action buttons (LLM's Load / Test /
                // Save) must not squeeze the last one into a vertical letter
                // stack on a phone width — extra buttons flow to the next line.
                FlowRow(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    if (actions.isNotEmpty()) {
                        actions.forEach { a ->
                            val action = (a["action"] as? JsonPrimitive)?.contentOrNull ?: return@forEach
                            val alabel = (a["label"] as? JsonPrimitive)?.contentOrNull ?: "Submit"
                            val extra = (a["payload"] as? JsonObject) ?: JsonObject(emptyMap())
                            Button(onClick = {
                                submitting = true
                                emit.event(action, collect(extra))
                            }) { Text(alabel) }
                        }
                    } else {
                        c.str("submit_action")?.let { sa ->
                            val extra = (c.attributes["submit_payload"] as? JsonObject) ?: JsonObject(emptyMap())
                            Button(onClick = {
                                submitting = true
                                emit.event(sa, collect(extra))
                            }) {
                                Text(c.str("submit_label") ?: "Save")
                            }
                        }
                    }
                }
            }
        }
    }
}

/**
 * Feature 044 US5 — an INTERACTIVE theme channel picker. Shows the channel's
 * swatch + hex; tapping opens a menu of on-brand choices (the presets' values for
 * this channel). Picking one restyles the app instantly ([ThemeSink]) AND persists
 * it (`save_theme {theme:{color_key, color_value}}`), matching the web round-trip.
 */
@Composable
private fun ColorPickerPrimitive(
    c: Component,
    emit: Emit,
    theme: ThemeSink,
) {
    val key = c.str("color_key").orEmpty()
    val label = c.str("label") ?: key
    var current by remember(c) { mutableStateOf(c.str("value") ?: "") }
    var open by remember { mutableStateOf(false) }
    Box {
        Row(
            modifier =
                Modifier
                    .fillMaxWidth()
                    .clickable(enabled = key.isNotBlank()) { open = true }
                    .padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            ColorSwatch(current)
            Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
            Text(
                current,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            channelSwatchOptions(key, current).forEach { hex ->
                DropdownMenuItem(
                    text = {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            ColorSwatch(hex)
                            Text(hex, color = MaterialTheme.colorScheme.onSurface)
                        }
                    },
                    onClick = {
                        open = false
                        current = hex
                        val spec =
                            buildJsonObject {
                                put("color_key", key)
                                put("color_value", hex)
                            }
                        theme.apply(spec) // restyle live
                        emit.event("save_theme", buildJsonObject { put("theme", spec) }) // persist
                    },
                )
            }
        }
    }
}

/** A small rounded color chip; falls back to the surface tint for a bad hex. */
@Composable
private fun ColorSwatch(hex: String) {
    val color = hexToColor(hex) ?: MaterialTheme.colorScheme.surfaceVariant
    Box(
        modifier =
            Modifier
                .size(18.dp)
                .clip(RoundedCornerShape(4.dp))
                .background(color)
                .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(4.dp)),
    )
}

/**
 * Feature 044 US5 — `theme_apply` is a side-effect component: when it appears it
 * pushes its palette spec (preset|colors|color_key+value) to the [ThemeSink] so the
 * app restyles live. It renders no visible UI.
 */
@Composable
private fun ThemeApplyPrimitive(
    c: Component,
    theme: ThemeSink,
) {
    LaunchedEffect(c) { theme.apply(c.attributes) }
}

@Composable
private fun CodePrimitive(c: Component) {
    Surface(color = MaterialTheme.colorScheme.surfaceVariant, modifier = Modifier.fillMaxWidth()) {
        Text(
            text = c.str("content") ?: c.str("code").orEmpty(),
            fontFamily = FontFamily.Monospace,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(12.dp),
        )
    }
}

@Composable
private fun FileActionButton(
    c: Component,
    emit: Emit,
    label: String,
) {
    val action = c.str("action")
    Button(
        onClick = { if (action != null) emit.event(action, c.payload()) },
        enabled = action != null,
    ) { Text(label) }
}

/** Feature — a download button that fetches an authed backend file to the device. */
@Composable
private fun FileDownloadPrimitive(
    c: Component,
    download: Download,
) {
    val url = c.str("url") ?: c.str("download_url")
    val filename = c.str("filename") ?: c.str("title") ?: "download"
    val label = c.str("label") ?: "Download $filename"
    Button(
        onClick = { if (url != null) download.file(url, filename) },
        enabled = url != null,
    ) { Text(label) }
}
