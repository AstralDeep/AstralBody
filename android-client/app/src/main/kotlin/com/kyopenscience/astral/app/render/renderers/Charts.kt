package com.kyopenscience.astral.app.render.renderers

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.kyopenscience.astral.app.render.Renderer
import com.kyopenscience.astral.core.sdui.Component
import kotlin.math.max
import kotlin.math.min

private val pieColors =
    listOf(
        Color(0xFF6366F1), Color(0xFF8B5CF6), Color(0xFF06B6D4), Color(0xFF22C55E),
        Color(0xFFEAB308), Color(0xFFEF4444), Color(0xFFEC4899), Color(0xFF14B8A6),
    )

private fun Component.values(): List<Double> = numList("values").ifEmpty { numList("data") }

/** Register the chart primitives (US2), drawn with Compose Canvas (no extra dep). */
fun Renderer.registerChartRenderers(): Renderer =
    apply {
        register("bar_chart") { c -> BarChart(c) }
        register("line_chart") { c -> LineChart(c) }
        register("pie_chart") { c -> PieChart(c) }
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
