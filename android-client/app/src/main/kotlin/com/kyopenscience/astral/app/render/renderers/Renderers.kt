package com.kyopenscience.astral.app.render.renderers

import com.kyopenscience.astral.app.render.Renderer

/**
 * Register the full SDUI primitive vocabulary the client renders natively. The
 * excluded web-only / not-yet-implemented types (`plotly_chart`, `audio`,
 * `color_picker`, `theme_apply`, `generative`) are intentionally NOT registered —
 * ROTE substitutes them upstream (the client advertises only `supportedTypes`),
 * and any that still arrive hit the labeled placeholder (FR-005).
 */
fun Renderer.registerAllRenderers(): Renderer =
    registerBasicRenderers()
        .registerLayoutRenderers()
        .registerDataRenderers()
        .registerInputRenderers()
        .registerChartRenderers()
        .registerMediaRenderers()
