package com.kyopenscience.astral.app.render.renderers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import com.kyopenscience.astral.app.render.Download
import com.kyopenscience.astral.app.render.Emit
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.core.sdui.Component
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject

/** Register the input/code/file primitives (US2). */
fun Renderer.registerInputRenderers(): Renderer =
    apply {
        register("input") { c -> InputPrimitive(c, emit) }
        register("param_picker") { c -> ParamPickerPrimitive(c, emit) }
        register("color_picker") { c -> ColorPickerPrimitive(c) }
        register("theme_apply") { } // feature 043: side-effect only, no visible UI
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
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (actions.isNotEmpty()) {
                    actions.forEach { a ->
                        val action = (a["action"] as? JsonPrimitive)?.contentOrNull ?: return@forEach
                        val alabel = (a["label"] as? JsonPrimitive)?.contentOrNull ?: "Submit"
                        val extra = (a["payload"] as? JsonObject) ?: JsonObject(emptyMap())
                        Button(onClick = { emit.event(action, collect(extra)) }) { Text(alabel) }
                    }
                } else {
                    c.str("submit_action")?.let { sa ->
                        val extra = (c.attributes["submit_payload"] as? JsonObject) ?: JsonObject(emptyMap())
                        Button(onClick = { emit.event(sa, collect(extra)) }) {
                            Text(c.str("submit_label") ?: "Save")
                        }
                    }
                }
            }
        }
    }
}

/** Feature 043 — a theme channel readout (label + hex) for the Theme surface. */
@Composable
private fun ColorPickerPrimitive(c: Component) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(c.str("label") ?: c.str("color_key").orEmpty(), style = MaterialTheme.typography.bodyMedium)
        Text(
            c.str("value") ?: "",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(start = 8.dp),
        )
    }
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
