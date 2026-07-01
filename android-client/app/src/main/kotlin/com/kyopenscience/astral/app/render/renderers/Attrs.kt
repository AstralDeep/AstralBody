package com.kyopenscience.astral.app.render.renderers

import com.kyopenscience.astral.core.sdui.Component
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
