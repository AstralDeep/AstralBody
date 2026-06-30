package com.kyopenscience.astral.core.streaming

import com.kyopenscience.astral.core.protocol.Inbound
import com.kyopenscience.astral.core.protocol.StreamError
import com.kyopenscience.astral.core.sdui.CanvasOp
import com.kyopenscience.astral.core.sdui.Component
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Client-side consumption of the orchestrator's push-streaming protocol — a
 * direct port of the verified Windows `streaming.py`. Pure: translate a stream
 * frame into canvas ops that the existing `Canvas` reducer applies in place,
 * keyed by a synthetic `stream-<stream_id>` node. Renders the structured
 * `components` (ignoring any web `html`), with per-stream monotonic seq dedupe,
 * session filtering, terminal final-and-forget, and error→alert.
 */
const val STREAM_NODE_PREFIX = "stream-"

fun streamNodeId(streamId: String): String = "$STREAM_NODE_PREFIX$streamId"

/** (canvasComponentId, dedupeKey) for a frame — push keys on stream_id, legacy poll on tool_name. */
private fun nodeKey(streamId: String?, toolName: String?): Pair<String, String>? =
    when {
        streamId != null -> streamNodeId(streamId) to streamId
        toolName != null -> "${STREAM_NODE_PREFIX}tool-$toolName" to "tool:$toolName"
        else -> null
    }

private fun errorComponent(node: String, err: StreamError): Component {
    val retryable = err.retryable
    val text = err.message ?: err.code ?: "stream error"
    val attrs =
        buildJsonObject {
            put("type", "alert")
            put("variant", if (retryable) "warning" else "error")
            put("title", if (retryable) "Live update interrupted" else "Live update failed")
            put("message", text)
        }
    return Component(type = "alert", id = node, attributes = attrs, children = emptyList())
}

private fun containerOf(node: String, comps: List<Component>): Component =
    Component(
        type = "container",
        id = node,
        attributes = buildJsonObject { put("type", "container") },
        children = comps,
    )

/**
 * Translate a `ui_stream_data` / legacy `stream_data` frame into canvas ops.
 * Returns `[]` when dropped (unaddressable, another chat, or stale) or with
 * nothing renderable. [seqState] (stream-key -> last seq) is mutated in place.
 */
fun streamFrameToOps(
    frame: Inbound.UiStreamData,
    activeChat: String?,
    seqState: MutableMap<String, Int>,
): List<CanvasOp> {
    val (node, key) = nodeKey(frame.streamId, frame.toolName) ?: return emptyList()

    val session = frame.sessionId
    if (session != null && activeChat != null && session != activeChat) return emptyList()

    val seq = frame.seq
    if (seq != null) {
        val last = seqState[key]
        if (last != null && seq <= last) return emptyList()
        seqState[key] = seq
    }
    if (frame.terminal) seqState.remove(key)

    frame.error?.let { return listOf(CanvasOp("upsert", node, errorComponent(node, it))) }

    val comps = frame.components
    if (comps.isEmpty()) return emptyList()
    val body = if (comps.size == 1) comps[0].copy(id = node) else containerOf(node, comps)
    return listOf(CanvasOp("upsert", node, body))
}

/** A lightweight placeholder shown on `stream_subscribed`, replaced by the first frame. */
fun subscribeAckOps(msg: Inbound.StreamSubscribed): List<CanvasOp> {
    val (node, _) = nodeKey(msg.streamId, msg.toolName) ?: return emptyList()
    val tool = msg.toolName ?: "tool"
    val attrs =
        buildJsonObject {
            put("type", "text")
            put("content", "Streaming $tool…")
        }
    return listOf(CanvasOp("upsert", node, Component("text", node, attrs, emptyList())))
}

/** A standalone `stream_error` control message → an alert at the stream node (or `[]`). */
fun streamErrorOps(msg: Inbound.StreamErrorMsg): List<CanvasOp> {
    val (node, _) = nodeKey(msg.streamId, msg.toolName) ?: return emptyList()
    val text = msg.error.message ?: msg.error.code ?: "stream error"
    val attrs =
        buildJsonObject {
            put("type", "alert")
            put("variant", "error")
            put("title", "Stream error")
            put("message", text)
        }
    return listOf(CanvasOp("upsert", node, Component("alert", node, attrs, emptyList())))
}
