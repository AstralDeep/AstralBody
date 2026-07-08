package com.personalailabs.astraldeep.app.render.renderers

import com.personalailabs.astraldeep.core.sdui.Component
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull

// Small tolerant readers over a component's raw attribute object, shared by the
// renderer modules.
internal fun Component.str(key: String): String? = (attributes[key] as? JsonPrimitive)?.contentOrNull

internal fun Component.obj(key: String): JsonObject? = attributes[key] as? JsonObject

internal fun Component.int(key: String): Int? = (attributes[key] as? JsonPrimitive)?.intOrNull

internal fun Component.dbl(key: String): Double? = (attributes[key] as? JsonPrimitive)?.doubleOrNull

internal fun Component.bool(key: String): Boolean? = (attributes[key] as? JsonPrimitive)?.booleanOrNull

internal fun Component.arr(key: String): JsonArray? = attributes[key] as? JsonArray

internal fun Component.payload(): JsonObject = (attributes["payload"] as? JsonObject) ?: JsonObject(emptyMap())

internal fun Component.strList(key: String): List<String> = arr(key)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull } ?: emptyList()

internal fun Component.numList(key: String): List<Double> = arr(key)?.mapNotNull { (it as? JsonPrimitive)?.doubleOrNull } ?: emptyList()

/** Rows for `table` / generic 2-D arrays: a JSON array of arrays of cells. */
internal fun Component.rows(key: String): List<List<String>> =
    arr(key)?.mapNotNull { row ->
        (row as? JsonArray)?.map { (it as? JsonPrimitive)?.contentOrNull ?: "" }
    } ?: emptyList()

// --- minimal native `css` support (settings-surface parity) -----------------
// The web renderer applies the astralprims `css` styling field as inline CSS;
// the native clients honor the tiny subset the settings surfaces actually use
// (the Theme preset swatch strips): background, height ("22px"), flex ("1").
// Mirrored by the Windows twin (renderer.py _r_container).

internal fun Component.cssBackground(): String? =
    (obj("css")?.get("background") as? JsonPrimitive)?.contentOrNull?.takeIf {
        it.isNotBlank()
    }

internal fun Component.cssHeightPx(default: Int): Int =
    (obj("css")?.get("height") as? JsonPrimitive)?.contentOrNull
        ?.filter { it.isDigit() || it == '.' }
        ?.toDoubleOrNull()?.toInt()?.takeIf { it > 0 } ?: default

internal fun Component.cssFlex(default: Float): Float =
    (obj("css")?.get("flex") as? JsonPrimitive)?.contentOrNull?.toFloatOrNull()?.takeIf {
        it > 0f
    } ?: default

/** How a `container` renders natively (pure — JVM unit-tested). */
internal enum class ContainerMode { SwatchBox, SwatchRow, WrapRow, Column }

/** A childless css-styled container is a colored box (e.g. a Theme swatch cell). */
internal fun Component.isSwatchLeaf(): Boolean = children.isEmpty() && cssBackground() != null

/**
 * Container layout rule: a css-styled leaf renders as a colored box; a
 * `direction:"row"` whose children are ALL styled leaves is a proportional
 * swatch strip; any other row wraps its children (buttons/tab bars never
 * overflow a phone width); everything else stays the default column.
 */
internal fun containerMode(c: Component): ContainerMode =
    when {
        c.isSwatchLeaf() -> ContainerMode.SwatchBox
        c.str("direction") == "row" ->
            if (c.children.isNotEmpty() && c.children.all { it.isSwatchLeaf() }) {
                ContainerMode.SwatchRow
            } else {
                ContainerMode.WrapRow
            }
        else -> ContainerMode.Column
    }

// --- table pagination (T027) -----------------------------------------------

/** A `table` carries paginator metadata when it has both `total_rows` and `page_size`. */
internal fun shouldPaginate(
    total: Int?,
    size: Int?,
): Boolean = total != null && size != null && total > 0 && size > 0

/** The derived pager affordance state: prev/next enablement + a "rows X–Y of Z" label. */
internal data class PagerState(
    val prevEnabled: Boolean,
    val nextEnabled: Boolean,
    val label: String,
)

/**
 * Pure pager math for a paginated `table` (T027): with [total] rows shown [size] at
 * a time from [offset], Prev is enabled off the first page and Next until the last.
 * The label is 1-based and inclusive ("rows 1–25 of 100").
 */
internal fun pagerState(
    total: Int,
    size: Int,
    offset: Int,
): PagerState {
    val off = offset.coerceAtLeast(0)
    val start = if (total <= 0) 0 else off + 1
    val end = minOf(off + size, total)
    return PagerState(
        prevEnabled = off > 0,
        nextEnabled = off + size < total,
        label = "rows $start–$end of $total",
    )
}
