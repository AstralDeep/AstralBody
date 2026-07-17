import AstralCore
import XCTest

@testable import AstralDeep

@MainActor
final class LLMFirstLoginOperationTests: XCTestCase {
    private let connection = "11111111-1111-4111-8111-111111111111"
    private let operation = "22222222-2222-4222-8222-222222222222"

    private final class FrameLog {
        var frames: [JSONValue] = []
    }

    private func modelWithConnection() -> (AppModel, FrameLog) {
        let model = AppModel()
        XCTAssertTrue(model.beginConversationConnection(connection))
        let log = FrameLog()
        model.outboundTap = { text in
            if let value = try? JSONValue.parse(Data(text.utf8)) {
                log.frames.append(value)
            }
        }
        return (model, log)
    }

    private var fields: [String: JSONValue] {
        [
            "provider": .string("openai"),
            "model": .string("gpt-4o-mini"),
            "api_key": .string("test-only-key"),
        ]
    }

    private func status(
        request: String,
        sequence: UInt64,
        state: String,
        phase: String,
        label: String,
        code: String? = nil,
        message: String? = nil
    ) -> InboundFrame {
        let terminal = ["completed", "failed", "cancelled", "retryable"].contains(state)
        let retryable = state == "retryable"
        let error: String
        if let code, let message {
            error = #"{"code":"\#(code)","message":"\#(message)"}"#
        } else {
            error = "null"
        }
        return InboundFrame.parse(
            """
            {"type":"operation_status","operation_id":"\(operation)",
             "action":"chrome_llm_save","surface":"llm_settings","chat_id":null,
             "connection_generation":"\(connection)","request_generation":"\(request)",
             "sequence":\(sequence),"state":"\(state)","phase":"\(phase)",
             "label":"\(label)","terminal":\(terminal),"retryable":\(retryable),
             "error":\(error),"retry_after_ms":null,
             "updated_at":"2026-07-15T18:41:00Z"}
            """)!
    }

    private func start(_ model: AppModel) -> LLMFirstLoginOperation {
        XCTAssertTrue(
            model.submitParamPicker(
                action: "chrome_llm_save",
                fields: fields,
                payload: [:]))
        return model.llmFirstLoginOperation!
    }

    func testImmediateSubmittingUsesOneClientIdentityAndDuplicateSaveIsSingleFlight() throws {
        XCTAssertEqual(AppModel.llmFirstLoginPhaseDelayNanoseconds, 1_000_000_000)
        XCTAssertEqual(AppModel.llmFirstLoginWatchdogNanoseconds, 10_000_000_000)
        let (model, log) = modelWithConnection()

        let local = start(model)

        XCTAssertEqual(local.state, .submitting)
        XCTAssertNil(local.operationId)
        XCTAssertTrue(local.isLoading)
        XCTAssertFalse(local.phaseVisible)
        XCTAssertEqual(local.label, "Submitting…")
        XCTAssertEqual(log.frames.count, 1)
        let sent = try XCTUnwrap(log.frames.first)
        XCTAssertEqual(sent["action"]?.stringValue, "chrome_llm_save")
        XCTAssertEqual(sent["payload"]?["surface"]?.stringValue, "llm_settings")
        XCTAssertEqual(sent["submission_id"]?.stringValue, local.submissionId)
        XCTAssertEqual(sent["request_generation"]?.stringValue, local.requestGeneration)
        XCTAssertEqual(sent["payload"]?["submission_id"]?.stringValue, local.submissionId)
        XCTAssertEqual(sent["payload"]?["request_generation"]?.stringValue, local.requestGeneration)
        XCTAssertEqual(sent["payload"]?["fields"]?["api_key"]?.stringValue, "test-only-key")

        XCTAssertFalse(
            model.submitParamPicker(
                action: "chrome_llm_save",
                fields: fields,
                payload: [:]))
        XCTAssertEqual(log.frames.count, 1)
        XCTAssertEqual(model.llmFirstLoginOperation?.submissionId, local.submissionId)
    }

    func testCanonicalAcceptanceAndMonotonicPhaseOrderingKeepFirstServerTerminal() {
        let (model, _) = modelWithConnection()
        let local = start(model)

        model.handleFrame(
            status(
                request: local.requestGeneration,
                sequence: 0,
                state: "accepted",
                phase: "accepted",
                label: "Accepted"))
        XCTAssertEqual(model.llmFirstLoginOperation?.state, .accepted)
        XCTAssertEqual(model.llmFirstLoginOperation?.operationId, operation)

        model.handleFrame(
            status(
                request: local.requestGeneration,
                sequence: 2,
                state: "persisting",
                phase: "saving_credentials",
                label: "Saving credentials"))
        model.handleFrame(
            status(
                request: local.requestGeneration,
                sequence: 1,
                state: "validating",
                phase: "validating_credentials",
                label: "Late validation"))
        XCTAssertEqual(model.llmFirstLoginOperation?.state, .persisting)
        XCTAssertEqual(model.llmFirstLoginOperation?.sequence, 2)

        model.handleFrame(
            status(
                request: local.requestGeneration,
                sequence: 3,
                state: "failed",
                phase: "validation_failed",
                label: "Check your credentials",
                code: "validation_failed",
                message: "The provider rejected these credentials."))
        model.handleFrame(
            status(
                request: local.requestGeneration,
                sequence: 4,
                state: "completed",
                phase: "completed",
                label: "Saved"))

        XCTAssertEqual(model.llmFirstLoginOperation?.state, .failed)
        XCTAssertEqual(model.llmFirstLoginOperation?.errorCode, "validation_failed")
        XCTAssertTrue(model.llmFirstLoginOperation?.isAuthoritativelyTerminal == true)
        XCTAssertFalse(model.llmFirstLoginOperation?.isLoading == true)
    }

    func testTenSecondWatchdogEndsLoadingWithoutInventingOrSuppressingServerTerminal() async {
        let (model, log) = modelWithConnection()
        model.llmFirstLoginPhaseDelay = 5_000_000
        model.llmFirstLoginWatchdogDelay = 20_000_000
        let local = start(model)

        try? await Task.sleep(nanoseconds: 10_000_000)
        XCTAssertTrue(model.llmFirstLoginOperation?.phaseVisible == true)
        XCTAssertTrue(model.llmFirstLoginOperation?.isLoading == true)

        try? await Task.sleep(nanoseconds: 30_000_000)
        XCTAssertEqual(model.llmFirstLoginOperation?.state, .unconfirmed)
        XCTAssertEqual(model.llmFirstLoginOperation?.submissionId, local.submissionId)
        XCTAssertEqual(model.llmFirstLoginOperation?.label, "Unable to confirm; reconnecting")
        XCTAssertFalse(model.llmFirstLoginOperation?.isLoading == true)
        XCTAssertFalse(model.llmFirstLoginOperation?.isAuthoritativelyTerminal == true)
        XCTAssertTrue(model.llmFirstLoginOperation?.retryable == true)

        // Save while acceptance is unknown is a status retry for the same
        // submission, never a second credential write.
        XCTAssertFalse(
            model.submitParamPicker(
                action: "chrome_llm_save",
                fields: fields,
                payload: [:]))
        XCTAssertEqual(log.frames.count, 1)

        // The watchdog is only a local connectivity projection: the first
        // durable server terminal must still converge this same attempt.
        model.handleFrame(
            status(
                request: local.requestGeneration,
                sequence: 0,
                state: "accepted",
                phase: "accepted",
                label: "Accepted"))
        XCTAssertEqual(model.llmFirstLoginOperation?.state, .unconfirmed)
        model.handleFrame(
            status(
                request: local.requestGeneration,
                sequence: 1,
                state: "completed",
                phase: "completed",
                label: "Provider setup complete"))
        XCTAssertEqual(model.llmFirstLoginOperation?.state, .completed)
        XCTAssertTrue(model.llmFirstLoginOperation?.isAuthoritativelyTerminal == true)
    }

    func testDurableSubmissionLookupConvergesAndNavigatesExactlyOnce() async throws {
        let (model, _) = modelWithConnection()
        model.screen = .surface
        model.mandatorySurface = true
        model.pendingSurfaceKey = "llm"
        let local = start(model)
        let projection = try XCTUnwrap(
            OperationProjection(
                json: try JSONValue.parse(
                    Data(
                        """
                        {"operation_id":"\(operation)","operation_kind":"llm_credential_save",
                         "admission_class":"interactive","owner_scope":"user","chat_id":null,
                         "parent_operation_id":null,"connection_generation":"\(connection)",
                         "request_generation":"\(local.requestGeneration)","state":"completed",
                         "phase_code":"completed","terminal_code":null,"safe_summary":"Saved",
                         "retry_after_ms":null,"state_revision":3,
                         "accepted_at":"2026-07-15T18:41:00Z","queue_deadline_at":null,
                         "started_at":"2026-07-15T18:41:00Z","terminal_at":"2026-07-15T18:41:01Z",
                         "updated_at":"2026-07-15T18:41:01Z","purge_after":"2026-07-16T18:41:01Z"}
                        """.utf8))))
        model.llmOperationReconciler = { operationId, submissionId in
            XCTAssertNil(operationId)
            XCTAssertEqual(submissionId, local.submissionId)
            return .submission(.accepted(projection))
        }

        await model.reconcileLLMFirstLoginOperation()

        XCTAssertEqual(model.llmFirstLoginOperation?.state, .completed)
        XCTAssertEqual(model.llmFirstLoginOperation?.operationId, operation)
        XCTAssertTrue(model.llmFirstLoginOperation?.didAdvance == true)
        XCTAssertEqual(model.screen, .chat)
        model.screen = .surface
        await model.reconcileLLMFirstLoginOperation()
        XCTAssertEqual(model.screen, .surface)
    }

    func testCorrectiveFailureLeavesFieldsEditableAndRetryGetsFreshIdentity() {
        let (model, log) = modelWithConnection()
        let first = start(model)
        model.handleFrame(
            status(
                request: first.requestGeneration,
                sequence: 1,
                state: "failed",
                phase: "validation_failed",
                label: "Check your credentials",
                code: "validation_failed",
                message: "The provider rejected these credentials."))

        XCTAssertTrue(model.llmFirstLoginOperation?.fieldsEditable == true)
        XCTAssertTrue(
            model.submitParamPicker(
                action: "chrome_llm_save",
                fields: fields,
                payload: [:]))
        XCTAssertEqual(log.frames.count, 2)
        XCTAssertNotEqual(model.llmFirstLoginOperation?.submissionId, first.submissionId)
        XCTAssertEqual(model.llmFirstLoginOperation?.state, .submitting)
    }

    func testLLMAdmissionRefusalRequiresTheExactValidatedEnvelope() {
        let (model, _) = modelWithConnection()
        let local = start(model)

        model.handleFrame(
            InboundFrame.parse(
                """
                {"type":"error","submission_id":"\(local.submissionId)",
                 "accepted":false,"code":"capacity_exceeded",
                 "message":"Try again shortly.","retryable":true,
                 "retry_after_ms":250,"unexpected":true}
                """)!)

        XCTAssertEqual(model.llmFirstLoginOperation?.state, .submitting)
        XCTAssertFalse(model.llmFirstLoginOperation?.isAuthoritativelyTerminal == true)

        model.handleFrame(
            InboundFrame.parse(
                """
                {"type":"error","submission_id":"\(local.submissionId)",
                 "accepted":false,"code":"capacity_exceeded",
                 "message":"Try again shortly.","retryable":true,
                 "retry_after_ms":250}
                """)!)

        XCTAssertEqual(model.llmFirstLoginOperation?.state, .retryable)
        XCTAssertEqual(model.llmFirstLoginOperation?.errorCode, "capacity_exceeded")
        XCTAssertTrue(model.llmFirstLoginOperation?.isAuthoritativelyTerminal == true)
    }
}
