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

internal fun Component.strList(key: String): List<String> =
    arr(key)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull } ?: emptyList()

internal fun Component.numList(key: String): List<Double> =
    arr(key)?.mapNotNull { (it as? JsonPrimitive)?.doubleOrNull } ?: emptyList()

/** Rows for `table` / generic 2-D arrays: a JSON array of arrays of cells. */
internal fun Component.rows(key: String): List<List<String>> =
    arr(key)?.mapNotNull { row ->
        (row as? JsonArray)?.map { (it as? JsonPrimitive)?.contentOrNull ?: "" }
    } ?: emptyList()
