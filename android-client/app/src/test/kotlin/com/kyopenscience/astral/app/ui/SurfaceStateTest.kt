package com.kyopenscience.astral.app.ui

import kotlin.test.Test
import kotlin.test.assertEquals

/** Feature 044 T039 — the SDUI surface's bounded loading state (loaded/loading/timed-out). */
class SurfaceStateTest {
    @Test
    fun a_delivered_surface_is_loaded_regardless_of_the_timer() {
        assertEquals(SurfaceViewState.Loaded, surfaceViewState(hasSurface = true, timedOut = false))
        assertEquals(SurfaceViewState.Loaded, surfaceViewState(hasSurface = true, timedOut = true))
    }

    @Test
    fun waiting_is_loading_until_the_timeout_fires() {
        assertEquals(SurfaceViewState.Loading, surfaceViewState(hasSurface = false, timedOut = false))
    }

    @Test
    fun a_timeout_without_a_surface_offers_retry() {
        assertEquals(SurfaceViewState.TimedOut, surfaceViewState(hasSurface = false, timedOut = true))
    }
}
