package com.personalailabs.astraldeep.app.ui

import androidx.window.core.layout.WindowWidthSizeClass
import kotlin.test.Test
import kotlin.test.assertEquals

class LayoutModeTest {
    @Test
    fun compact_width_stacks() {
        assertEquals(LayoutMode.Stacked, layoutModeFor(WindowWidthSizeClass.COMPACT))
    }

    @Test
    fun medium_width_splits() {
        assertEquals(LayoutMode.Split, layoutModeFor(WindowWidthSizeClass.MEDIUM))
    }

    @Test
    fun expanded_width_splits() {
        assertEquals(LayoutMode.Split, layoutModeFor(WindowWidthSizeClass.EXPANDED))
    }
}
