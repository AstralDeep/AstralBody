package com.personalailabs.astraldeep.app.transport

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class BackoffTest {
    @Test
    fun first_attempt_is_base() {
        assertEquals(1_000L, backoffDelayMs(1))
        assertEquals(1_000L, backoffDelayMs(0))
    }

    @Test
    fun doubles_each_attempt() {
        assertEquals(2_000L, backoffDelayMs(2))
        assertEquals(4_000L, backoffDelayMs(3))
        assertEquals(8_000L, backoffDelayMs(4))
    }

    @Test
    fun caps_at_max_and_never_overflows() {
        assertEquals(30_000L, backoffDelayMs(10))
        assertEquals(30_000L, backoffDelayMs(100))
        assertTrue(backoffDelayMs(64) in 1L..30_000L)
    }
}
