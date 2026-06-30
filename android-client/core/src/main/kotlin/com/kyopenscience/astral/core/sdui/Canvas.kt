package com.kyopenscience.astral.core.sdui

/** A single in-place canvas mutation, from `ui_upsert.ops` or the streaming consumer. */
data class CanvasOp(
    val op: String,
    val componentId: String,
    val component: Component? = null,
)

/**
 * Pure canvas reducer — the model behind the Compose canvas. Components are kept
 * in an ordered list keyed by their identity; `upsert` replaces in place
 * (preserving position) or appends, and `remove` drops by id. Returns a NEW list
 * (no input mutation) so it is trivially unit-testable and drives Compose state.
 *
 * Mirrors the Windows client's `Canvas.apply_ops`.
 */
object Canvas {
    fun apply(current: List<Component>, ops: List<CanvasOp>): List<Component> {
        val order = ArrayList<String>(current.size)
        val byId = LinkedHashMap<String, Component>(current.size)
        current.forEachIndexed { index, c ->
            val key = c.id ?: "anon-$index"
            if (byId.put(key, c) == null) order.add(key)
        }
        for (op in ops) {
            when (op.op) {
                "remove" -> if (byId.remove(op.componentId) != null) order.remove(op.componentId)
                else -> {
                    val comp = op.component ?: continue
                    if (byId.put(op.componentId, comp) == null) order.add(op.componentId)
                }
            }
        }
        return order.map { byId.getValue(it) }
    }
}
