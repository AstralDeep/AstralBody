package com.kyopenscience.astral.app

import com.kyopenscience.astral.core.sdui.Component
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject

internal fun attrs(json: String): JsonObject = Json.parseToJsonElement(json).jsonObject

internal fun textComponent(
    text: String,
    id: String = "t-$text",
): Component = Component("text", id, attrs("""{"type":"text","content":"$text"}"""), emptyList())
