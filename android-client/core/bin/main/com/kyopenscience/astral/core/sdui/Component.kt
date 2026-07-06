package com.kyopenscience.astral.core.sdui

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * One SDUI component: a typed node with dynamic [attributes] and optional
 * [children], decoded tolerantly from the orchestrator's structured wire.
 *
 * The renderer looks up [type] in its registry and falls back to a labeled
 * placeholder for unknown types (FR-005). [id] is the in-place-update identity
 * (`component_id`, else `id`, else null). [attributes] keeps the raw component
 * object so each renderer can read the per-primitive fields it needs (mirrors the
 * Windows client's "the component dict is the attributes" model).
 */
data class Component(
    val type: String,
    val id: String?,
    val attributes: JsonObject,
    val children: List<Component>,
) {
    companion object {
        fun fromJson(obj: JsonObject): Component {
            val type = (obj["type"] as? JsonPrimitive)?.contentOrNull.orEmpty()
            val id =
                (obj["component_id"] as? JsonPrimitive)?.contentOrNull
                    ?: (obj["id"] as? JsonPrimitive)?.contentOrNull
            return Component(type = type, id = id, attributes = obj, children = childrenOf(obj))
        }

        /** Decode a JSON array of component objects (nulls / non-objects dropped). */
        fun listFromJson(arr: JsonArray?): List<Component> = arr?.mapNotNull { (it as? JsonObject)?.let(::fromJson) } ?: emptyList()

        private fun childrenOf(obj: JsonObject): List<Component> =
            when (val raw = obj["content"] ?: obj["children"]) {
                is JsonArray -> raw.mapNotNull { (it as? JsonObject)?.let(::fromJson) }
                is JsonObject -> listOf(fromJson(raw))
                else -> emptyList()
            }
    }
}
