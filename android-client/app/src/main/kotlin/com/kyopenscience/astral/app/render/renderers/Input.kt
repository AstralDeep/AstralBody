package com.kyopenscience.astral.app.render.renderers

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.kyopenscience.astral.app.render.Emit
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.core.sdui.Component
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Register the input/code/file primitives (US2). */
fun Renderer.registerInputRenderers(): Renderer =
    apply {
        register("input") { c -> InputPrimitive(c, emit) }
        register("param_picker") { c -> ParamPickerPrimitive(c, emit) }
        register("code") { c -> CodePrimitive(c) }
        register("file_upload") { c -> FileActionButton(c, emit, c.str("label") ?: "Upload") }
        register("file_download") { c -> FileActionButton(c, emit, c.str("label") ?: "Download") }
        register("download_card") { c -> FileActionButton(c, emit, c.str("label") ?: "Download") }
    }

@Composable
private fun InputPrimitive(c: Component, emit: Emit) {
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

@Composable
private fun ParamPickerPrimitive(c: Component, emit: Emit) {
    val action = c.str("action")
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(14.dp)) {
            Text(c.str("title") ?: "Parameters", style = MaterialTheme.typography.titleSmall)
            Button(
                onClick = { if (action != null) emit.event(action, c.payload()) },
                enabled = action != null,
            ) { Text(c.str("submit_label") ?: "Run") }
        }
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
private fun FileActionButton(c: Component, emit: Emit, label: String) {
    val action = c.str("action")
    Button(
        onClick = { if (action != null) emit.event(action, c.payload()) },
        enabled = action != null,
    ) { Text(label) }
}
