package com.personalailabs.astraldeep.app.render.renderers

import com.personalailabs.astraldeep.app.render.Renderer

/**
 * Register the full SDUI primitive vocabulary the client renders natively. Charts
 * include `plotly_chart` — we extract its traces and draw them natively so ROTE
 * doesn't degrade agent-emitted Plotly figures into value cards on this client.
 * The remaining web-only / not-yet-implemented types (`audio`, `color_picker`,
 * `theme_apply`, `generative`) are intentionally NOT registered — ROTE substitutes
 * them upstream (the client advertises only `supportedTypes`), and any that still
 * arrive hit the labeled placeholder (FR-005).
 */
fun Renderer.registerAllRenderers(): Renderer =
    registerBasicRenderers()
        .registerLayoutRenderers()
        .registerDataRenderers()
        .registerInputRenderers()
        .registerChartRenderers()
        .registerMediaRenderers()
