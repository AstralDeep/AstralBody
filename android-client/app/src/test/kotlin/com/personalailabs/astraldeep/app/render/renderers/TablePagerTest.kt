package com.personalailabs.astraldeep.app.render.renderers

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Feature 044 T027 — the pure table-pager math (prev/next enablement + label). */
class TablePagerTest {
    @Test
    fun should_paginate_only_with_positive_total_and_size() {
        assertTrue(shouldPaginate(100, 25))
        assertFalse(shouldPaginate(null, 25))
        assertFalse(shouldPaginate(100, null))
        assertFalse(shouldPaginate(0, 25))
        assertFalse(shouldPaginate(100, 0))
    }

    @Test
    fun first_page_disables_prev_enables_next() {
        val ps = pagerState(total = 100, size = 25, offset = 0)
        assertFalse(ps.prevEnabled)
        assertTrue(ps.nextEnabled)
        assertEquals("rows 1–25 of 100", ps.label)
    }

    @Test
    fun middle_page_enables_both() {
        val ps = pagerState(total = 100, size = 25, offset = 25)
        assertTrue(ps.prevEnabled)
        assertTrue(ps.nextEnabled)
        assertEquals("rows 26–50 of 100", ps.label)
    }

    @Test
    fun last_page_disables_next_and_clamps_end_to_total() {
        val ps = pagerState(total = 90, size = 25, offset = 75)
        assertTrue(ps.prevEnabled)
        assertFalse(ps.nextEnabled)
        assertEquals("rows 76–90 of 90", ps.label)
    }

    @Test
    fun negative_offset_is_clamped_to_the_first_page() {
        val ps = pagerState(total = 50, size = 10, offset = -5)
        assertFalse(ps.prevEnabled)
        assertEquals("rows 1–10 of 50", ps.label)
    }
}
