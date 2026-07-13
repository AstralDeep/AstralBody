package com.personalailabs.astraldeep.app.render.renderers

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.personalailabs.astraldeep.app.R
import com.personalailabs.astraldeep.app.render.Download
import com.personalailabs.astraldeep.app.render.Emit
import com.personalailabs.astraldeep.core.sdui.Component
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.net.URLEncoder

/**
 * Feature 055 — the shared per-component chrome rendered under every top-level
 * canvas component (the Android twin of the web component footer): a compact
 * provenance badge (T036, wire-contract §6) and an overflow menu carrying the
 * Refine affordance (T040, `component_refine`) and the export entries (T045).
 */

/** The three server-stamped trust marks (wire-contract §6). */
enum class Provenance(
    val label: String,
    val glyph: String,
) {
    Grounded("tool data", "✓"),
    Estimated("estimated", "≈"),
    Generated("AI-generated", "✦"),
}

// Decorative/structural types assert no facts — never badged, never refined
// (mirrors the web footer's skip set, webrender/renderer.py _PROV_SKIP_TYPES).
private val PROVENANCE_SKIP_TYPES = setOf("divider", "skeleton")

// The web footer's tolerant normalization sets — the server stamps the three
// canonical values, but agent-authored synonyms still read as the right mark.
private val PROVENANCE_GROUNDED = setOf("grounded", "verified", "tool", "search", "source")
private val PROVENANCE_ESTIMATED = setOf("estimated", "uncertain", "approx", "low_confidence")
private val PROVENANCE_GENERATED = setOf("generated", "model", "ai")

/**
 * The badge kind for a component's server-stamped `provenance` field. Absent,
 * blank, or unknown values render NOTHING — the client never derives trust
 * locally (the stamp is server-owned and overwrites agent-supplied values).
 */
internal fun provenanceOf(c: Component): Provenance? {
    if (c.type.trim().lowercase() in PROVENANCE_SKIP_TYPES) return null
    val kind = c.str("provenance")?.trim()?.lowercase()?.takeIf { it.isNotBlank() } ?: return null
    return when {
        kind in PROVENANCE_GROUNDED -> Provenance.Grounded
        kind in PROVENANCE_ESTIMATED -> Provenance.Estimated
        kind in PROVENANCE_GENERATED -> Provenance.Generated
        else -> null
    }
}

/** One export entry: an authed backend URL fetched via the existing download path. */
@Immutable
data class ExportEntry(
    val label: String,
    val url: String,
    val filename: String,
)

/** The derived overflow-menu model for one canvas component (pure → JVM-tested). */
@Immutable
data class ArtifactMenu(
    /** Target of the Refine… entry; null hides it (no identity / read-only view). */
    val refineComponentId: String? = null,
    val exports: List<ExportEntry> = emptyList(),
) {
    val isEmpty: Boolean get() = refineComponentId == null && exports.isEmpty()
}

/**
 * Menu derivation rules (contracts/rest-endpoints.md): CSV export exists only
 * for a `table` with an identity (the endpoint 422s other types); the canvas
 * HTML export needs only the chat; Refine needs an identity and a live,
 * mutable view (the read-only timeline pauses it, same rule as the composer).
 */
internal fun artifactMenu(
    c: Component,
    chatId: String?,
    mutationsLocked: Boolean,
): ArtifactMenu {
    val id = c.id?.takeIf { it.isNotBlank() }
    val chat = chatId?.takeIf { it.isNotBlank() }
    val exports =
        buildList {
            if (chat != null && id != null && c.type.equals("table", ignoreCase = true)) {
                add(
                    ExportEntry(
                        label = "Export table (CSV)",
                        url = "/api/export/component/${encodeUrl(id)}.csv?chat_id=${encodeUrl(chat)}",
                        filename = exportFilename(c.str("title") ?: id, "csv"),
                    ),
                )
            }
            if (chat != null) {
                add(
                    ExportEntry(
                        label = "Export canvas (HTML)",
                        url = "/api/export/canvas/${encodeUrl(chat)}.html",
                        filename = exportFilename("canvas-$chat", "html"),
                    ),
                )
            }
        }
    val refinable = id != null && !mutationsLocked && c.type.trim().lowercase() !in PROVENANCE_SKIP_TYPES
    return ArtifactMenu(refineComponentId = if (refinable) id else null, exports = exports)
}

/** `component_refine` payload (wire-contract §3): the identity + the instruction. */
internal fun refinePayload(
    componentId: String,
    instruction: String,
): JsonObject =
    buildJsonObject {
        put("component_id", componentId)
        put("instruction", instruction.trim())
    }

private fun encodeUrl(v: String): String = URLEncoder.encode(v, "UTF-8")

/** DownloadManager rejects path separators/exotic chars in destination names. */
internal fun exportFilename(
    base: String,
    ext: String,
): String {
    val safe =
        base
            .map { if (it.isLetterOrDigit() || it in "-_ .") it else '_' }
            .joinToString("")
            .trim()
            .ifBlank { "export" }
    return "${safe.take(60)}.$ext"
}

/**
 * The chrome row under one top-level canvas component. Renders nothing when
 * there is neither a badge nor a menu entry, so pre-055 canvases (no stamped
 * provenance, no chat context) are byte-identical to today.
 */
@Composable
fun ArtifactFooter(
    c: Component,
    emit: Emit,
    download: Download,
    chatId: String?,
    mutationsLocked: Boolean,
) {
    val provenance = provenanceOf(c)
    val menu = artifactMenu(c, chatId, mutationsLocked)
    if (provenance == null && menu.isEmpty) return
    var menuOpen by remember { mutableStateOf(false) }
    var refineOpen by remember { mutableStateOf(false) }
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.End),
    ) {
        provenance?.let { ProvenanceBadge(it) }
        if (!menu.isEmpty) {
            Box {
                IconButton(onClick = { menuOpen = true }, modifier = Modifier.size(26.dp)) {
                    Icon(
                        painter = painterResource(R.drawable.ic_more),
                        contentDescription = "Component actions",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.size(15.dp),
                    )
                }
                DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                    menu.refineComponentId?.let {
                        DropdownMenuItem(
                            text = { Text("Refine…") },
                            onClick = {
                                menuOpen = false
                                refineOpen = true
                            },
                        )
                    }
                    menu.exports.forEach { entry ->
                        DropdownMenuItem(
                            text = { Text(entry.label) },
                            onClick = {
                                menuOpen = false
                                download.file(entry.url, entry.filename)
                            },
                        )
                    }
                }
            }
        }
    }
    val refineId = menu.refineComponentId
    if (refineOpen && refineId != null) {
        RefineDialog(
            onDismiss = { refineOpen = false },
            onSubmit = { instruction ->
                refineOpen = false
                emit.event("component_refine", refinePayload(refineId, instruction))
            },
        )
    }
}

/**
 * Compact trust pill — ✓ tool data (green) / ≈ estimated (amber) / ✦
 * AI-generated (muted) — matching the web footer's icons, labels, and tones so
 * provenance reads the same on every target (SC-006).
 */
@Composable
private fun ProvenanceBadge(p: Provenance) {
    val tone =
        when (p) {
            Provenance.Grounded -> Color(0xFF22C55E)
            Provenance.Estimated -> Color(0xFFEAB308)
            Provenance.Generated -> MaterialTheme.colorScheme.onSurfaceVariant
        }
    Surface(color = tone.copy(alpha = 0.12f), shape = RoundedCornerShape(9.dp)) {
        Text(
            text = "${p.glyph} ${p.label}",
            color = tone,
            fontSize = 10.sp,
            fontWeight = FontWeight.Medium,
            modifier = Modifier.padding(horizontal = 7.dp, vertical = 2.dp),
        )
    }
}

/**
 * The refine instruction prompt (T040): a plain-language instruction sent as
 * `component_refine` — the server runs the full gate stack and answers with a
 * `ui_upsert` onto the same identity, or an honest per-action error frame.
 */
@Composable
private fun RefineDialog(
    onDismiss: () -> Unit,
    onSubmit: (String) -> Unit,
) {
    var instruction by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Refine this component") },
        text = {
            OutlinedTextField(
                value = instruction,
                onValueChange = { instruction = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("What should change?") },
                minLines = 2,
            )
        },
        confirmButton = {
            TextButton(enabled = instruction.isNotBlank(), onClick = { onSubmit(instruction) }) { Text("Refine") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
