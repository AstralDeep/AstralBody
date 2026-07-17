import XCTest

@testable import AstralCore

final class StatusLifecycleTests: XCTestCase {
    private let chat = "11111111-1111-4111-8111-111111111111"
    private let connection = "22222222-2222-4222-8222-222222222222"
    private let request = "33333333-3333-4333-8333-333333333333"
    private let operation = "44444444-4444-4444-8444-444444444444"
    private let revision = "55555555-5555-4555-8555-555555555555"
    private let runtime = "66666666-6666-4666-8666-666666666666"

    private func inbound(_ text: String) -> InboundFrame {
        InboundFrame.parse(text)!
    }

    private func status(
        sequence: UInt64,
        state: String,
        request: String? = nil,
        chatId: String? = nil,
        action: String = "curated_example",
        surface: String = "chat"
    ) -> OperationStatus {
        let terminal = ["completed", "failed", "cancelled", "retryable"].contains(state)
        let retryable = state == "retryable"
        let error =
            ["failed", "cancelled", "retryable"].contains(state)
            ? #"{"code":"operation_failed","message":"Safe failure"}"#
            : "null"
        return OperationStatus(
            frame: inbound(
                """
                {"type":"operation_status","operation_id":"\(operation)",
                 "action":"\(action)","surface":"\(surface)",
                 "chat_id":\(chatId.map { "\"\($0)\"" } ?? "null"),
                 "connection_generation":"\(connection)",
                 "request_generation":"\(request ?? self.request)",
                 "sequence":\(sequence),"state":"\(state)","phase":"\(state)",
                 "label":"\(state.capitalized)","terminal":\(terminal),
                 "retryable":\(retryable),"error":\(error),
                 "retry_after_ms":\(retryable ? "500" : "null"),
                 "updated_at":"2026-07-16T12:00:00Z"}
                """))!
    }

    private func lifecycle(
        generation: UInt64,
        revision stateRevision: UInt64,
        state: String
    ) -> AgentLifecycle {
        let runtimeValue = ["failed", "offline"].contains(state) ? "null" : #""\#(runtime)""#
        let reason = state == "failed" ? #""child_exited""# : "null"
        return AgentLifecycle(
            frame: inbound(
                """
                {"type":"agent_lifecycle","agent_id":"ua-dice",
                 "revision_id":"\(revision)","runtime_instance_id":\(runtimeValue),
                 "lifecycle_generation":\(generation),"state_revision":\(stateRevision),
                 "state":"\(state)","reason_code":\(reason),
                 "label":"Agent \(state)","updated_at":"2026-07-16T12:00:00Z"}
                """))!
    }

    func testOperationKeepsHighestSequenceAndFirstTerminal() {
        var reducer = StatusLifecycleReducer()

        XCTAssertTrue(
            reducer.accept(
                operation: status(sequence: 0, state: "accepted", chatId: chat),
                connectionGeneration: connection,
                requestGeneration: request,
                activeChatId: chat))
        XCTAssertTrue(
            reducer.accept(
                operation: status(sequence: 1, state: "running", chatId: chat),
                connectionGeneration: connection,
                requestGeneration: request,
                activeChatId: chat))
        XCTAssertFalse(
            reducer.accept(
                operation: status(sequence: 0, state: "accepted", chatId: chat),
                connectionGeneration: connection,
                requestGeneration: request,
                activeChatId: chat))
        XCTAssertTrue(
            reducer.accept(
                operation: status(sequence: 2, state: "failed", chatId: chat),
                connectionGeneration: connection,
                requestGeneration: request,
                activeChatId: chat))
        XCTAssertFalse(
            reducer.accept(
                operation: status(sequence: 3, state: "completed", chatId: chat),
                connectionGeneration: connection,
                requestGeneration: request,
                activeChatId: chat))
        XCTAssertEqual(reducer.operations[operation]?.state, "failed")
    }

    func testOperationRejectsTheWrongRequestFence() {
        var reducer = StatusLifecycleReducer()
        let stale = "77777777-7777-4777-8777-777777777777"

        XCTAssertFalse(
            reducer.accept(
                operation: status(
                    sequence: 0, state: "accepted", request: stale, chatId: chat),
                connectionGeneration: connection,
                requestGeneration: request,
                activeChatId: chat))
        XCTAssertTrue(reducer.operations.isEmpty)
    }

    func testSurfaceOperationBeforeActiveChatRequiresKnownPendingGeneration() {
        var reducer = StatusLifecycleReducer()
        let surface = status(
            sequence: 0,
            state: "accepted",
            chatId: nil,
            action: "chrome_open",
            surface: "llm_settings")

        XCTAssertFalse(
            reducer.accept(
                operation: surface,
                connectionGeneration: connection,
                conversationRequestGeneration: nil,
                activeChatId: nil,
                pendingChatRequestGenerations: [],
                pendingSurfaceRequestGenerations: []))
        XCTAssertTrue(
            reducer.accept(
                operation: surface,
                connectionGeneration: connection,
                conversationRequestGeneration: nil,
                activeChatId: nil,
                pendingChatRequestGenerations: [],
                pendingSurfaceRequestGenerations: [request]))
        XCTAssertEqual(reducer.operations[operation]?.state, "accepted")
    }

    func testRetainedChatSubmissionAcceptsTerminalAfterConversationFenceMoves() {
        var reducer = StatusLifecycleReducer()
        let next = "77777777-7777-4777-8777-777777777777"
        let terminal = status(sequence: 1, state: "completed", chatId: chat)

        XCTAssertTrue(
            reducer.accept(
                operation: terminal,
                connectionGeneration: connection,
                conversationRequestGeneration: next,
                activeChatId: chat,
                pendingChatRequestGenerations: [request],
                pendingSurfaceRequestGenerations: []))
        XCTAssertEqual(reducer.operations[operation]?.state, "completed")

        var wrongChatReducer = StatusLifecycleReducer()
        XCTAssertFalse(
            wrongChatReducer.accept(
                operation: terminal,
                connectionGeneration: connection,
                conversationRequestGeneration: next,
                activeChatId: "88888888-8888-4888-8888-888888888888",
                pendingChatRequestGenerations: [request],
                pendingSurfaceRequestGenerations: []))
    }

    func testQueuedReplayParsesExactIdentityAndRejectsMalformedCopies() throws {
        let submission = "77777777-7777-4777-8777-777777777777"
        let frame = Outbound.chatMessage(
            "queued",
            sessionId: chat,
            submissionId: submission,
            requestGeneration: request)
        let replay = try XCTUnwrap(QueuedOperationReplay(frameText: frame))

        XCTAssertEqual(replay.identity.submissionId, submission)
        XCTAssertEqual(replay.identity.requestGeneration, request)
        XCTAssertEqual(replay.action, "chat_message")
        XCTAssertEqual(replay.surface, "chat")
        XCTAssertEqual(replay.chatId, chat)
        XCTAssertEqual(replay.conversationPurpose, .commit)
        XCTAssertNil(
            QueuedOperationReplay(
                frameText: frame.replacingOccurrences(
                    of: #""submission_id":"77777777-7777-4777-8777-777777777777""#,
                    with: #""submission_id":"not-a-uuid""#,
                    options: [],
                    range: frame.range(
                        of: #""submission_id":"77777777-7777-4777-8777-777777777777""#))))
        XCTAssertNil(QueuedOperationReplay(frameText: #"{"type":"ui_event","action":"bad","payload":{}}"#))
    }

    func testTwentyFiveStateLifecycleSequencesConvergeLexicographically() {
        var reducer = StatusLifecycleReducer()
        let states = ["starting", "online", "updating", "failed", "offline"]

        for generation in 1...20 {
            for (stateRevision, state) in states.enumerated() {
                XCTAssertTrue(
                    reducer.accept(
                        lifecycle: lifecycle(
                            generation: UInt64(generation),
                            revision: UInt64(stateRevision),
                            state: state)))
            }
            XCTAssertFalse(
                reducer.accept(
                    lifecycle: lifecycle(
                        generation: UInt64(generation),
                        revision: 1,
                        state: "online")))
        }

        XCTAssertEqual(reducer.agents["ua-dice"]?.lifecycleGeneration, 20)
        XCTAssertEqual(reducer.agents["ua-dice"]?.state, "offline")
    }
}
