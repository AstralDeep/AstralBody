package com.personalailabs.astraldeep.app

import com.personalailabs.astraldeep.app.rest.AstralRest
import com.personalailabs.astraldeep.app.transport.ConnectionState
import com.personalailabs.astraldeep.app.transport.LocalSubmission
import com.personalailabs.astraldeep.app.transport.OrchestratorClient
import com.personalailabs.astraldeep.app.ui.AppViewModel
import com.personalailabs.astraldeep.app.ui.UiState
import com.personalailabs.astraldeep.core.protocol.Inbound
import com.personalailabs.astraldeep.core.protocol.OperationStatusError
import com.personalailabs.astraldeep.core.protocol.Wire
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Feature 060 canonical operation/lifecycle reducer coverage for Android. */
class StatusLifecycleTest {
    private val vm =
        AppViewModel(
            OrchestratorClient("ws://localhost:9/ws"),
            AstralRest("http://localhost:9"),
        )

    private fun operation(
        state: String,
        sequence: ULong,
        connection: String = CONNECTION,
        request: String = REQUEST,
        chat: String? = CHAT,
        action: String = "curated_example",
    ): Inbound.OperationStatus {
        val terminal = state in setOf("completed", "failed", "cancelled", "retryable")
        val error =
            if (state in setOf("failed", "cancelled", "retryable")) {
                OperationStatusError("operation_failed", "Safe terminal message")
            } else {
                null
            }
        return Inbound.OperationStatus(
            operationId = OPERATION,
            action = action,
            surface = "chat",
            chatId = chat,
            connectionGeneration = connection,
            requestGeneration = request,
            sequence = sequence,
            state = state,
            phase = state,
            label = state.replaceFirstChar(Char::uppercase),
            terminal = terminal,
            retryable = state == "retryable",
            error = error,
            retryAfterMs = if (state == "retryable") 500UL else null,
            updatedAt = "2026-07-16T12:00:00Z",
        )
    }

    private fun localSubmission(
        action: String = "curated_example",
        request: String = REQUEST,
        submission: String = SUBMISSION,
        chat: String? = null,
    ) =
        LocalSubmission(
            action = action,
            chatId = chat,
            submissionId = submission,
            requestGeneration = request,
        )

    private fun lifecycle(
        generation: ULong,
        revision: ULong,
        state: String,
    ): Inbound.AgentLifecycle =
        Inbound.AgentLifecycle(
            agentId = AGENT,
            revisionId = REVISION,
            runtimeInstanceId = if (state in setOf("failed", "offline")) null else RUNTIME,
            lifecycleGeneration = generation,
            stateRevision = revision,
            state = state,
            reasonCode = if (state == "offline") "host_lost" else null,
            label = state.replaceFirstChar(Char::uppercase),
            updatedAt = "2026-07-16T12:00:00Z",
        )

    @Test
    fun operation_status_retains_highest_sequence_and_first_terminal() {
        var ui =
            UiState(
                activeChatId = CHAT,
                connectionGeneration = CONNECTION,
                requestGeneration = REQUEST,
            )
        ui = vm.reduce(ui, operation("accepted", 0UL))
        assertEquals("Accepted", ui.statusText)
        ui = vm.reduce(ui, operation("running", 1UL))
        assertEquals("Running", ui.statusText)
        assertEquals(1UL, ui.operationStatuses.getValue(OPERATION).sequence)

        val terminal = vm.reduce(ui, operation("failed", 2UL))
        assertEquals("Safe terminal message", terminal.statusText)
        assertEquals("failed", terminal.operationStatuses.getValue(OPERATION).state)

        assertEquals(terminal, vm.reduce(terminal, operation("completed", 3UL)))
        assertEquals(terminal, vm.reduce(terminal, operation("running", 1UL)))
    }

    @Test
    fun operation_status_rejects_stale_chat_scope() {
        val base =
            UiState(
                activeChatId = CHAT,
                connectionGeneration = CONNECTION,
                requestGeneration = REQUEST,
            )
        assertEquals(base, vm.reduce(base, operation("accepted", 0UL, connection = OTHER)))
        assertEquals(base, vm.reduce(base, operation("accepted", 0UL, request = OTHER)))
        assertEquals(base, vm.reduce(base, operation("accepted", 0UL, chat = OTHER)))
    }

    @Test
    fun surface_send_before_any_chat_projects_submitting_then_accepts_known_generation() {
        val uuids = ArrayDeque(listOf(SUBMISSION, REQUEST))
        val client = OrchestratorClient("ws://localhost:9/ws", uuidFactory = { uuids.removeFirst() })
        val model = AppViewModel(client, AstralRest("http://localhost:9"))

        model.sendEvent("curated_example")

        val submitting = model.state.value
        val local = submitting.pendingSubmissions.getValue(REQUEST)
        assertNull(submitting.activeChatId)
        assertEquals("Submitting…", submitting.statusText)
        assertEquals(SUBMISSION, local.submissionId)
        val frame = Json.parseToJsonElement(client.pendingFrames().single()).jsonObject
        assertEquals(SUBMISSION, frame.getValue("submission_id").jsonPrimitive.content)
        assertEquals(REQUEST, frame.getValue("request_generation").jsonPrimitive.content)
        assertEquals(SUBMISSION, frame.getValue("payload").jsonObject.getValue("submission_id").jsonPrimitive.content)
        assertEquals(
            REQUEST,
            frame.getValue("payload").jsonObject.getValue("request_generation").jsonPrimitive.content,
        )

        val surface =
            model.reduce(
                submitting.copy(connectionGeneration = CONNECTION),
                operation("accepted", 0UL, chat = null),
            )
        assertEquals("Accepted", surface.statusText)
        assertEquals(OPERATION, surface.operationStatuses.keys.single())
    }

    @Test
    fun surface_status_requires_a_known_pending_generation_and_exact_connection_and_action() {
        val base = UiState(connectionGeneration = CONNECTION)
        val pending = vm.projectLocalSubmission(base, localSubmission())

        assertEquals(base, vm.reduce(base, operation("accepted", 0UL, chat = null)))
        assertEquals(pending, vm.reduce(pending, operation("accepted", 0UL, request = OTHER, chat = null)))
        assertEquals(pending, vm.reduce(pending, operation("accepted", 0UL, connection = OTHER, chat = null)))
        assertEquals(
            pending,
            vm.reduce(pending, operation("accepted", 0UL, chat = null, action = "different_action")),
        )
    }

    @Test
    fun completed_terminal_keeps_its_visible_canonical_label() {
        val base =
            UiState(
                activeChatId = CHAT,
                connectionGeneration = CONNECTION,
                requestGeneration = REQUEST,
            )
        val completed = vm.reduce(base, operation("completed", 1UL))
        assertEquals("Completed", completed.statusText)
        assertNull(completed.operationStatuses.getValue(OPERATION).error)
    }

    @Test
    fun terminal_status_and_disconnect_clear_client_only_pending_submissions() {
        val pending =
            vm.projectLocalSubmission(
                UiState(connectionGeneration = CONNECTION),
                localSubmission(),
            )
        val completed = vm.reduce(pending, operation("completed", 1UL, chat = null))
        assertTrue(completed.pendingSubmissions.isEmpty())
        assertEquals("Completed", completed.statusText)

        val disconnected = vm.reduceConnectionState(pending, ConnectionState.Disconnected)
        assertTrue(disconnected.pendingSubmissions.isEmpty())
        assertNull(disconnected.statusText)
    }

    @Test
    fun correlated_admission_refusal_terminalizes_only_the_named_local_submission() {
        val refusal =
            assertIs<Inbound.AdmissionRefusal>(
                Wire.decode(
                    """{"type":"error","submission_id":"$SUBMISSION","accepted":false,"code":"capacity_exceeded","message":"Try again shortly.","retryable":true,"retry_after_ms":1000}""",
                ),
            )
        assertEquals(SUBMISSION, refusal.submissionId)
        val firstPending = vm.projectLocalSubmission(UiState(), localSubmission())
        val pending =
            vm.projectLocalSubmission(
                firstPending,
                localSubmission(request = OTHER, submission = OTHER),
            )

        val settled = vm.reduce(pending, refusal)

        assertEquals(setOf(OTHER), settled.pendingSubmissions.keys)
        assertEquals("Try again shortly.", settled.statusText)
        assertEquals("Try again shortly. (capacity_exceeded)", settled.banner)
        assertEquals(pending, vm.reduce(pending, refusal.copy(submissionId = FOREIGN)))
        assertTrue(vm.reduce(settled, refusal.copy(submissionId = OTHER)).pendingSubmissions.isEmpty())
    }

    @Test
    fun malformed_admission_refusals_remain_generic_and_cannot_settle_pending() {
        val pending = vm.projectLocalSubmission(UiState(), localSubmission())
        val malformed =
            listOf(
                """{"type":"error","submission_id":null,"accepted":false,"code":"capacity_exceeded","message":"Try again shortly.","retryable":true,"retry_after_ms":1000}""",
                """{"type":"error","submission_id":"$SUBMISSION","accepted":false,"code":"capacity_exceeded","message":"Try again shortly.","retryable":true,"retry_after_ms":1000,"unexpected":true}""",
                """{"type":"error","submission_id":"$SUBMISSION","accepted":false,"code":"raw_internal_trace","message":"Try again shortly.","retryable":true,"retry_after_ms":1000}""",
                """{"type":"error","submission_id":"$SUBMISSION","accepted":false,"code":"capacity_exceeded","message":"Try again shortly.","retryable":false,"retry_after_ms":1}""",
            )

        malformed.forEach { raw ->
            val generic = assertIs<Inbound.ErrorFrame>(Wire.decode(raw))
            val reduced = vm.reduce(pending, generic)
            assertEquals(pending.pendingSubmissions, reduced.pendingSubmissions)
            assertEquals("error", reduced.bannerKind)
        }
    }

    @Test
    fun all_five_lifecycle_states_render_and_twenty_sequences_converge() {
        val states = listOf("starting", "online", "updating", "failed", "offline")
        var ui = UiState()
        for (generation in 1UL..20UL) {
            val frames = states.mapIndexed { index, state -> lifecycle(generation, index.toULong(), state) }
            for (frame in frames) {
                ui = vm.reduce(ui, frame)
                assertEquals(frame.state, ui.agentLifecycles.getValue(AGENT).state)
                assertEquals("$AGENT: ${frame.label}", ui.banner)
            }

            val settled = ui
            for (stale in listOf(frames[1], frames[3], frames[4])) {
                ui = vm.reduce(ui, stale)
                assertEquals(settled, ui)
            }
            assertEquals("offline", ui.agentLifecycles.getValue(AGENT).state)
        }
    }

    @Test
    fun higher_lifecycle_generation_replaces_a_higher_old_state_revision() {
        val old = vm.reduce(UiState(), lifecycle(8UL, 99UL, "offline"))
        val replacement = vm.reduce(old, lifecycle(9UL, 0UL, "starting"))
        assertEquals("starting", replacement.agentLifecycles.getValue(AGENT).state)
        assertEquals("info", replacement.bannerKind)
    }

    private companion object {
        const val OPERATION = "3558c68b-a02e-4529-9cf8-5ba95bcc7951"
        const val SUBMISSION = "0cf52102-cffc-4f3a-9867-8dc744593a55"
        const val CONNECTION = "dbe2670f-04ce-40c8-ab08-615500571f90"
        const val REQUEST = "b1876d0c-7401-47fa-8c78-8cdedba692a8"
        const val CHAT = "acfa80bf-3387-46a4-b06b-a708057a0413"
        const val OTHER = "945a7952-2f25-48e8-8ca4-dd79895b880a"
        const val FOREIGN = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        const val REVISION = "2e9bca16-898b-4f51-8549-eaa81d97dc23"
        const val RUNTIME = "91a03450-f0fc-4c32-a61c-085e7779d74a"
        const val AGENT = "ua-dice"
    }
}
