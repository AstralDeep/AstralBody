import XCTest

@testable import AstralCore

final class ConversationSnapshotTests: XCTestCase {
    private let chat = "11111111-1111-4111-8111-111111111111"
    private let connection = "22222222-2222-4222-8222-222222222222"
    private let hydration = "33333333-3333-4333-8333-333333333333"
    private let commit = "44444444-4444-4444-8444-444444444444"

    private func frame(_ text: String) throws -> InboundFrame {
        try XCTUnwrap(InboundFrame.parse(text))
    }

    private func snapshot(
        id: String = "55555555-5555-4555-8555-555555555555",
        request: String? = nil,
        purpose: String = "hydration",
        revision: Int = 0,
        text: String = "Restored"
    ) throws -> ConversationSnapshot {
        try XCTUnwrap(
            ConversationSnapshot(
                frame: frame(
                    """
                    {
                      "type":"conversation_snapshot",
                      "schema_version":1,
                      "snapshot_id":"\(id)",
                      "chat_id":"\(chat)",
                      "connection_generation":"\(connection)",
                      "request_generation":"\(request ?? hydration)",
                      "snapshot_purpose":"\(purpose)",
                      "render_revision":\(revision),
                      "committed_at":"2026-07-15T18:41:00Z",
                      "transcript":[{
                        "message_id":"m-1",
                        "role":"assistant",
                        "created_at":"2026-07-15T18:40:59Z",
                        "parts":[
                          {"type":"text","text":"\(text)"},
                          {"type":"components","components":[{"type":"text","content":"Card text"}]},
                          {"type":"structured","value":{"total":21},"plain_text":"total: 21"},
                          {"type":"recovery","code":"saved_content_unrenderable","message":"A saved response could not be displayed."}
                        ],
                        "attachments":[]
                      }],
                      "canvas":{"target":"canvas","components":[{"type":"text","content":"Canvas"}]}
                    }
                    """)))
    }

    func testSemanticSnapshotDecodesEveryCanonicalPartWithoutBlanking() throws {
        let value = try snapshot()

        XCTAssertEqual(value.messages.count, 1)
        XCTAssertEqual(value.messages[0].parts.count, 4)
        XCTAssertEqual(value.messages[0].visibleText, "Restored\ntotal: 21\nA saved response could not be displayed.")
        XCTAssertEqual(value.messages[0].components.map(\.fallbackText), ["Card text"])
        XCTAssertEqual(value.canvasComponents.map(\.fallbackText), ["Canvas"])
    }

    func testMalformedSemanticPartsAndWebPresentationAreRejectedAtomically() throws {
        let blank = try frame(
            """
            {"type":"conversation_snapshot","schema_version":1,
             "snapshot_id":"55555555-5555-4555-8555-555555555555",
             "chat_id":"\(chat)","connection_generation":"\(connection)",
             "request_generation":"\(hydration)","snapshot_purpose":"hydration",
             "render_revision":0,"committed_at":"2026-07-15T18:41:00Z",
             "transcript":[{"message_id":"m","role":"assistant",
               "created_at":"2026-07-15T18:40:59Z",
               "parts":[{"type":"text","text":""}],"attachments":[]}],
             "canvas":{"target":"canvas","components":[]}}
            """)
        let webEnvelope = try frame(
            """
            {"type":"conversation_snapshot","schema_version":1,
             "snapshot_id":"55555555-5555-4555-8555-555555555555",
             "chat_id":"\(chat)","connection_generation":"\(connection)",
             "request_generation":"\(hydration)","snapshot_purpose":"hydration",
             "render_revision":0,"committed_at":"2026-07-15T18:41:00Z",
             "transcript":[],"canvas":{"target":"canvas","components":[{
               "type":"text","content":"native",
               "_presentation":{"target":"web","html":"<p>bad</p>","workspace":{"export":false,"share":false}}
             }]}}
            """)

        XCTAssertNil(ConversationSnapshot(frame: blank))
        XCTAssertNil(ConversationSnapshot(frame: webEnvelope))
    }

    func testPurposeAwareEqualRevisionRulesAndOneCommittedUpdate() throws {
        var reducer = ConversationContinuityReducer()
        XCTAssertTrue(reducer.beginConnection(connection))
        XCTAssertTrue(
            reducer.openRequest(chatId: chat, requestGeneration: hydration, purpose: .hydration))

        let first = try snapshot()
        XCTAssertEqual(reducer.apply(first), .applied)
        XCTAssertEqual(reducer.apply(first), .replay)

        let conflict = try snapshot(
            id: "66666666-6666-4666-8666-666666666666",
            text: "Conflicting restore")
        XCTAssertEqual(reducer.apply(conflict), .rejected(.revisionConflict))

        XCTAssertTrue(reducer.openRequest(chatId: chat, requestGeneration: commit, purpose: .commit))
        let equalCommit = try snapshot(request: commit, purpose: "commit")
        XCTAssertEqual(reducer.apply(equalCommit), .rejected(.unexpectedEqualCommit))

        let next = try snapshot(
            id: "77777777-7777-4777-8777-777777777777",
            request: commit,
            purpose: "commit",
            revision: 1)
        XCTAssertEqual(reducer.apply(next), .applied)
        XCTAssertEqual(reducer.lastCommittedRenderRevision, 1)
        XCTAssertEqual(reducer.apply(next), .replay)

        let secondCommitSameGeneration = try snapshot(
            id: "88888888-8888-4888-8888-888888888888",
            request: commit,
            purpose: "commit",
            revision: 2)
        XCTAssertEqual(
            reducer.apply(secondCommitSameGeneration),
            .rejected(.generationAlreadyCompleted))
    }

    func testCommitReadyOpensOnlyExactNewerCommitFence() throws {
        var reducer = ConversationContinuityReducer(lastCommittedRenderRevision: 4)
        XCTAssertTrue(reducer.beginConnection(connection))
        XCTAssertTrue(
            reducer.openRequest(chatId: chat, requestGeneration: hydration, purpose: .hydration))

        let reusedHydration = try XCTUnwrap(
            ConversationCommitReady(
                frame: frame(
                    """
                    {"type":"conversation_commit_ready","schema_version":1,
                     "chat_id":"\(chat)","connection_generation":"\(connection)",
                     "request_generation":"\(hydration)","render_revision":5}
                    """)))
        XCTAssertFalse(reducer.accept(reusedHydration))

        let valid = try XCTUnwrap(
            ConversationCommitReady(
                frame: frame(
                    """
                    {"type":"conversation_commit_ready","schema_version":1,
                     "chat_id":"\(chat)","connection_generation":"\(connection)",
                     "request_generation":"\(commit)","render_revision":5}
                    """)))
        XCTAssertTrue(reducer.accept(valid))
        XCTAssertEqual(reducer.requestGeneration, commit)
        XCTAssertEqual(reducer.requestPurpose, .commit)

        let committed = try snapshot(request: commit, purpose: "commit", revision: 5)
        XCTAssertEqual(reducer.apply(committed), .applied)

        let stale = try XCTUnwrap(
            ConversationCommitReady(
                frame: frame(
                    """
                    {"type":"conversation_commit_ready","schema_version":1,
                     "chat_id":"\(chat)","connection_generation":"\(connection)",
                     "request_generation":"99999999-9999-4999-8999-999999999999",
                     "render_revision":5}
                    """)))
        XCTAssertFalse(reducer.accept(stale))

        let unknown = try frame(
            """
            {"type":"conversation_commit_ready","schema_version":1,
             "chat_id":"\(chat)","connection_generation":"\(connection)",
             "request_generation":"99999999-9999-4999-8999-999999999999",
             "render_revision":6,"extra":true}
            """)
        XCTAssertNil(ConversationCommitReady(frame: unknown))

        let wrongConnection = try XCTUnwrap(
            ConversationCommitReady(
                frame: frame(
                    """
                    {"type":"conversation_commit_ready","schema_version":1,
                     "chat_id":"\(chat)",
                     "connection_generation":"99999999-9999-4999-8999-999999999999",
                     "request_generation":"99999999-9999-4999-8999-999999999999",
                     "render_revision":6}
                    """)))
        XCTAssertFalse(reducer.accept(wrongConnection))

        for client in [ClientDispositions.ios, .macos, .watch] {
            XCTAssertEqual(client.frames["conversation_commit_ready"], .handled)
            XCTAssertEqual(client.frames["chat_deleted"], .handled)
        }
    }

    func testTransientFramesRequireExactScopeBaseAndIncreasingSequence() throws {
        var reducer = ConversationContinuityReducer(lastCommittedRenderRevision: 7)
        XCTAssertTrue(reducer.beginConnection(connection))
        XCTAssertTrue(reducer.openRequest(chatId: chat, requestGeneration: commit, purpose: .commit))

        let first = try frame(
            """
            {"type":"ui_upsert","chat_id":"\(chat)",
             "connection_generation":"\(connection)","request_generation":"\(commit)",
             "base_render_revision":7,"frame_sequence":1,"ops":[]}
            """)
        let duplicate = try frame(
            """
            {"type":"ui_upsert","chat_id":"\(chat)",
             "connection_generation":"\(connection)","request_generation":"\(commit)",
             "base_render_revision":7,"frame_sequence":1,"ops":[]}
            """)
        let wrongBase = try frame(
            """
            {"type":"ui_upsert","chat_id":"\(chat)",
             "connection_generation":"\(connection)","request_generation":"\(commit)",
             "base_render_revision":6,"frame_sequence":2,"ops":[]}
            """)

        XCTAssertTrue(reducer.acceptTransient(first))
        XCTAssertFalse(reducer.acceptTransient(duplicate))
        XCTAssertFalse(reducer.acceptTransient(wrongBase))
    }

    func testOutboundRegistrationLoadAndTurnCarryUUID4Generations() throws {
        let resume = try XCTUnwrap(
            ConversationResumeRegistration(
                activeChatId: chat,
                requestGeneration: hydration))
        let registration = Outbound.registerUI(
            token: "token",
            sessionId: chat,
            device: .ios(viewportWidth: 390, viewportHeight: 844),
            resumed: true,
            connectionGeneration: connection,
            resume: resume)
        let registerJSON = try JSONValue.parse(Data(registration.utf8))
        XCTAssertEqual(registerJSON["connection_generation"]?.stringValue, connection)
        XCTAssertEqual(registerJSON["resume"]?["active_chat_id"]?.stringValue, chat)
        XCTAssertEqual(registerJSON["resume"]?["request_generation"]?.stringValue, hydration)

        let submission = "77777777-7777-4777-8777-777777777777"
        let load = try JSONValue.parse(
            Data(
                Outbound.loadChat(
                    sessionId: chat,
                    chatId: chat,
                    submissionId: submission,
                    requestGeneration: hydration
                ).utf8))
        XCTAssertEqual(load["payload"]?["request_generation"]?.stringValue, hydration)
        XCTAssertEqual(load["payload"]?["snapshot_purpose"]?.stringValue, "hydration")
        XCTAssertEqual(load["submission_id"]?.stringValue, submission)
        XCTAssertEqual(load["request_generation"]?.stringValue, hydration)
        XCTAssertEqual(load["payload"]?["submission_id"]?.stringValue, submission)

        let turn = try JSONValue.parse(
            Data(
                Outbound.chatMessage(
                    "hello",
                    sessionId: chat,
                    submissionId: submission,
                    requestGeneration: commit
                ).utf8))
        XCTAssertEqual(turn["payload"]?["request_generation"]?.stringValue, commit)
        XCTAssertEqual(turn["payload"]?["snapshot_purpose"]?.stringValue, "commit")
        XCTAssertEqual(turn["submission_id"]?.stringValue, submission)
        XCTAssertEqual(turn["request_generation"]?.stringValue, commit)
        XCTAssertEqual(turn["payload"]?["submission_id"]?.stringValue, submission)

        let freshChatRequest = "88888888-8888-4888-8888-888888888888"
        let newChat = try JSONValue.parse(
            Data(
                Outbound.newChat(
                    sessionId: nil,
                    submissionId: submission,
                    requestGeneration: freshChatRequest
                ).utf8))
        XCTAssertEqual(newChat["submission_id"]?.stringValue, submission)
        XCTAssertEqual(newChat["request_generation"]?.stringValue, freshChatRequest)
        XCTAssertEqual(newChat["payload"]?["submission_id"]?.stringValue, submission)
        XCTAssertEqual(
            newChat["payload"]?["request_generation"]?.stringValue,
            freshChatRequest)
    }
}
