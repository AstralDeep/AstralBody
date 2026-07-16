package com.personalailabs.astraldeep.app.transport

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import okhttp3.Request
import okhttp3.WebSocket
import okio.ByteString
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

    @Test
    fun open_socket_rejection_retains_exact_frame_for_reconnect_replay() {
        val client = OrchestratorClient("ws://localhost:9/ws")
        client.installOpenSocketForTest(RejectingWebSocket())

        val local = client.sendEvent("raced_send", null)

        assertEquals(listOf("raced_send"), client.pendingActions())
        val sent = mutableListOf<String>()
        val replayed = mutableListOf<LocalSubmission>()
        client.replayPendingForTest(
            connectionGeneration = "22222222-2222-4222-8222-222222222222",
            onGeneration = {},
            onQueuedSubmission = replayed::add,
            send = { frame -> sent.add(frame) },
        )
        assertEquals(listOf(local), replayed)
        assertEquals(client.pendingActions(), emptyList())
        assertTrue(sent.single().contains(local.submissionId))
    }

    private class RejectingWebSocket : WebSocket {
        override fun request(): Request = Request.Builder().url("ws://localhost:9/ws").build()

        override fun queueSize(): Long = 0L

        override fun send(text: String): Boolean = false

        override fun send(bytes: ByteString): Boolean = false

        override fun close(
            code: Int,
            reason: String?,
        ): Boolean = true

        override fun cancel() = Unit
    }
}
