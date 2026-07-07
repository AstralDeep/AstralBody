package com.personalailabs.astraldeep.app.transport

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Feature 044 T014 — the bounded offline queue's drop-oldest is never silent. */
@OptIn(ExperimentalCoroutinesApi::class)
class QueueOverflowTest {
    @Test
    fun overflow_surfaces_each_dropped_frames_action() =
        runTest {
            val client = OrchestratorClient("ws://localhost:9/ws")
            val drops = mutableListOf<String>()
            val job = launch(UnconfinedTestDispatcher(testScheduler)) { client.dropped.collect { drops.add(it) } }
            // 66 frames while disconnected: the 64-deep queue drops the two oldest.
            repeat(66) { i -> client.sendEvent("action_$i", null) }
            testScheduler.advanceUntilIdle()
            assertEquals(listOf("action_0", "action_1"), drops)
            job.cancel()
        }

    @Test
    fun no_drop_signal_below_the_cap() =
        runTest {
            val client = OrchestratorClient("ws://localhost:9/ws")
            val drops = mutableListOf<String>()
            val job = launch(UnconfinedTestDispatcher(testScheduler)) { client.dropped.collect { drops.add(it) } }
            repeat(64) { i -> client.sendEvent("action_$i", null) }
            testScheduler.advanceUntilIdle()
            assertTrue(drops.isEmpty())
            job.cancel()
        }
}
