package com.kyopenscience.astral.app.render.renderers

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.core.sdui.Component
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlin.math.max
import kotlin.math.min

private val pieColors =
    listOf(
        Color(0xFF6366F1),
        Color(0xFF8B5CF6),
        Color(0xFF06B6D4),
        Color(0xFF22C55E),
        Color(0xFFEAB308),
        Color(0xFFEF4444),
        Color(0xFFEC4899),
        Color(0xFF14B8A6),
    )

private fun Component.values(): List<Double> = numList("values").ifEmpty { numList("data") }

/** Register the chart primitives (US2), drawn with Compose Canvas (no extra dep). */
fun Renderer.registerChartRenderers(): Renderer =
    apply {
        register("bar_chart") { c -> BarChart(c) }
        register("line_chart") { c -> LineChart(c) }
        register("pie_chart") { c -> PieChart(c) }
        // Native draw of Plotly figures too: advertising this type keeps ROTE
        // from degrading server-side charts (many agents emit plotly_chart) into
        // value cards on this client — we extract the traces and draw them.
        register("plotly_chart") { c -> PlotlyChart(c) }
    }

@Composable
private fun EmptyChart(c: Component) {
    Text(
        text = c.str("title") ?: "(chart)",
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
private fun BarChart(c: Component) {
    val vals = c.values()
    if (vals.isEmpty()) {
        EmptyChart(c)
        return
    }
    val color = MaterialTheme.colorScheme.primary
    Canvas(modifier = Modifier.fillMaxWidth().height(160.dp)) {
        val maxV = max(vals.max(), 1.0)
        val n = vals.size
        val gap = size.width * 0.02f
        val barW = (size.width - gap * (n + 1)) / n
        vals.forEachIndexed { i, v ->
            val h = (v / maxV).toFloat() * size.height
            drawRect(color = color, topLeft = Offset(gap + i * (barW + gap), size.height - h), size = Size(barW, h))
        }
    }
}

@Composable
private fun LineChart(c: Component) {
    val vals = c.values()
    if (vals.size < 2) {
        EmptyChart(c)
        return
    }
    val color = MaterialTheme.colorScheme.primary
    Canvas(modifier = Modifier.fillMaxWidth().height(160.dp)) {
        val maxV = vals.max()
        val minV = min(vals.min(), 0.0)
        val range = max(maxV - minV, 1.0)
        val stepX = size.width / (vals.size - 1)
        for (i in 0 until vals.size - 1) {
            val y1 = size.height - ((vals[i] - minV) / range).toFloat() * size.height
            val y2 = size.height - ((vals[i + 1] - minV) / range).toFloat() * size.height
            drawLine(color = color, start = Offset(i * stepX, y1), end = Offset((i + 1) * stepX, y2), strokeWidth = 4f)
        }
    }
}

@Composable
private fun PieChart(c: Component) {
    val vals = c.values()
    if (vals.isEmpty()) {
        EmptyChart(c)
        return
    }
    val total = max(vals.sum(), 1e-9)
    Canvas(modifier = Modifier.fillMaxWidth().height(160.dp)) {
        val d = min(size.width, size.height)
        val topLeft = Offset((size.width - d) / 2f, (size.height - d) / 2f)
        var start = -90f
        vals.forEachIndexed { i, v ->
            val sweep = (v / total).toFloat() * 360f
            drawArc(
                color = pieColors[i % pieColors.size],
                startAngle = start,
                sweepAngle = sweep,
                useCenter = true,
                topLeft = topLeft,
                size = Size(d, d),
            )
            start += sweep
        }
    }
}

/** One Plotly trace we can draw: its numeric y-series plus type/name. */
private class Trace(val y: List<Double>, val type: String, val name: String?)

private fun Component.traces(): List<Trace> =
    (arr("data") ?: JsonArray(emptyList())).mapNotNull { el ->
        val o = el as? JsonObject ?: return@mapNotNull null
        val y = (o["y"] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.doubleOrNull }.orEmpty()
        if (y.isEmpty()) {
            null
        } else {
            Trace(
                y = y,
                type = (o["type"] as? JsonPrimitive)?.contentOrNull ?: "scatter",
                name = (o["name"] as? JsonPrimitive)?.contentOrNull,
            )
        }
    }

/**
 * A native draw of a Plotly figure: a single bar trace becomes a bar chart; one
 * or more scatter/line traces become overlaid polylines with a legend. Values are
 * co-normalized across traces so multi-series (e.g. high vs low) share a scale.
 */
@Composable
private fun PlotlyChart(c: Component) {
    val traces = c.traces()
    if (traces.isEmpty()) {
        EmptyChart(c)
        return
    }
    val allY = traces.flatMap { it.y }
    val asBars = traces.size == 1 && traces[0].type.equals("bar", ignoreCase = true)
    val dataMin = allY.min()
    val dataMax = allY.max()
    // Bars baseline at 0; lines use the data's own range (with a little headroom)
    // so a narrow band — e.g. 67–74°F — actually shows its variation.
    val pad = (dataMax - dataMin) * 0.12
    val minV = if (asBars) min(dataMin, 0.0) else dataMin - pad
    val maxV = if (asBars) dataMax else dataMax + pad
    val range = max(maxV - minV, 1e-9)
    Column(modifier = Modifier.fillMaxWidth()) {
        c.str("title")?.takeIf { it.isNotBlank() }?.let {
            Text(
                text = it,
                style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.onSurface,
                modifier = Modifier.padding(bottom = 6.dp),
            )
        }
        Canvas(modifier = Modifier.fillMaxWidth().height(180.dp)) {
            fun yPix(v: Double): Float = size.height - ((v - minV) / range).toFloat() * size.height
            if (asBars) {
                val vals = traces[0].y
                val n = vals.size
                val gap = size.width * 0.02f
                val barW = (size.width - gap * (n + 1)) / n
                vals.forEachIndexed { i, v ->
                    val top = yPix(v)
                    drawRect(
                        color = pieColors[0],
                        topLeft = Offset(gap + i * (barW + gap), top),
                        size = Size(barW, size.height - top),
                    )
                }
            } else {
                traces.forEachIndexed { ti, tr ->
                    val color = pieColors[ti % pieColors.size]
                    val ys = tr.y
                    if (ys.size < 2) {
                        drawCircle(color = color, radius = 6f, center = Offset(size.width / 2f, yPix(ys[0])))
                    } else {
                        val stepX = size.width / (ys.size - 1)
                        for (i in 0 until ys.size - 1) {
                            drawLine(
                                color = color,
                                start = Offset(i * stepX, yPix(ys[i])),
                                end = Offset((i + 1) * stepX, yPix(ys[i + 1])),
                                strokeWidth = 4f,
                            )
                        }
                    }
                }
            }
        }
        if (traces.any { !it.name.isNullOrBlank() }) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                traces.forEachIndexed { ti, tr ->
                    val nm = tr.name?.takeIf { it.isNotBlank() } ?: return@forEachIndexed
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        Box(
                            modifier =
                                Modifier
                                    .size(10.dp)
                                    .clip(RoundedCornerShape(2.dp))
                                    .background(pieColors[ti % pieColors.size]),
                        )
                        Text(
                            text = nm,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }
}
