import AstralCore
import XCTest

@testable import AstralWatch

@MainActor
final class ConversationContinuityTests: XCTestCase {
    private let account = ConversationAccount(
        issuer: "https://id.example.test/realms/astral",
        subject: "watch-user")!
    private let chat = "11111111-1111-4111-8111-111111111111"
    private let connection = "22222222-2222-4222-8222-222222222222"
    private let hydration = "33333333-3333-4333-8333-333333333333"
    private let commit = "44444444-4444-4444-8444-444444444444"

    private var defaults: UserDefaults!
    private var store: ConversationResumeStore!

    override func setUp() {
        super.setUp()
        let suite = "WatchConversationContinuityTests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suite)!
        defaults.removePersistentDomain(forName: suite)
        store = ConversationResumeStore(
            defaults: defaults,
            now: { Date(timeIntervalSince1970: 1_752_605_260) })
    }

    private func inbound(_ text: String) -> InboundFrame {
        InboundFrame.parse(text)!
    }

    private func snapshot(
        id: String = "55555555-5555-4555-8555-555555555555",
        request: String? = nil,
        purpose: String = "hydration",
        revision: Int = 0,
        text: String = "Watch canvas"
    ) -> InboundFrame {
        inbound(
            """
            {"type":"conversation_snapshot","schema_version":1,
             "snapshot_id":"\(id)","chat_id":"\(chat)",
             "connection_generation":"\(connection)",
             "request_generation":"\(request ?? hydration)",
             "snapshot_purpose":"\(purpose)","render_revision":\(revision),
             "committed_at":"2026-07-15T18:41:00Z",
             "transcript":[
               {"message_id":"u1","role":"user","created_at":"2026-07-15T18:40:00Z",
                "parts":[{"type":"text","text":"Question"}],
                "attachments":[{"filename":"watch.txt"}]},
               {"message_id":"a1","role":"assistant","created_at":"2026-07-15T18:40:59Z",
                "parts":[
                  {"type":"recovery","code":"saved_content_unrenderable","message":"A saved response could not be displayed."},
                  {"type":"components","components":[{"type":"text","content":"Component answer"}]}
                ],"attachments":[]}
             ],
             "canvas":{"target":"canvas","components":[{"type":"text","content":"\(text)"}]}}
            """)
    }

    func testWatchOwnsOpaqueAccountLocatorIndependentOfEndpointOverride() {
        XCTAssertTrue(store.save(chatId: chat, for: account))
        defaults.set("https://another.example.test", forKey: AstralConfig.serverOverrideDefaultsKey)

        XCTAssertEqual(store.load(for: account)?.chatId, chat)
        XCTAssertNotEqual(account.locatorStorageKey, AstralConfig.serverOverrideDefaultsKey)
        XCTAssertFalse(account.locatorStorageKey.contains(account.subject))
    }

    func testWatchRelaunchRegistersStoredChatAndRetainsItAcrossDisconnect() async throws {
        XCTAssertTrue(store.save(chatId: chat, for: account))
        let model = WatchModel(conversationResumeStore: store)
        model.bindConversationAccount(account)
        let registration = try JSONValue.parse(
            Data(model.registrationFrame(token: "token", resumed: true).utf8))

        XCTAssertEqual(registration["resume"]?["active_chat_id"]?.stringValue, chat)
        XCTAssertEqual(model.activeChatId, chat)
        await model.handle(.disconnected(reason: "offline"))
        XCTAssertEqual(store.load(for: account)?.chatId, chat)
        XCTAssertEqual(model.activeChatId, chat)
    }

    func testWatchAppliesOneSemanticSnapshotAndSequencesTransientOverlay() {
        let model = WatchModel(conversationResumeStore: store)
        XCTAssertTrue(model.beginConversationConnection(connection))
        XCTAssertTrue(
            model.openConversationRequest(
                chatId: chat,
                requestGeneration: hydration,
                purpose: .hydration))
        model.handleFrame(snapshot())

        XCTAssertEqual(model.entries.count, 3)
        XCTAssertEqual(model.canvas.map(\.fallbackText), ["Watch canvas"])
        XCTAssertEqual(model.lastCommittedRenderRevision, 0)

        XCTAssertTrue(
            model.openConversationRequest(
                chatId: chat,
                requestGeneration: commit,
                purpose: .commit))
        model.handleFrame(
            inbound(
                """
                {"type":"ui_render","target":"canvas","chat_id":"\(chat)",
                 "connection_generation":"\(connection)","request_generation":"\(commit)",
                 "base_render_revision":0,"frame_sequence":1,
                 "components":[{"type":"text","content":"Preview"}]}
                """))
        XCTAssertEqual(model.canvas.map(\.fallbackText), ["Watch canvas"])
        XCTAssertEqual(model.visibleCanvas.map(\.fallbackText), ["Preview"])

        model.handleFrame(
            snapshot(
                id: "66666666-6666-4666-8666-666666666666",
                request: commit,
                purpose: "commit",
                revision: 1,
                text: "Committed"))
        XCTAssertEqual(model.canvas.map(\.fallbackText), ["Committed"])
        XCTAssertEqual(model.visibleCanvas.map(\.fallbackText), ["Committed"])
    }

    func testWatchCommitReadyAcceptsDetachedCommitOnlyForCurrentConnection() {
        let model = WatchModel(conversationResumeStore: store)
        XCTAssertTrue(model.beginConversationConnection(connection))
        XCTAssertTrue(
            model.openConversationRequest(
                chatId: chat,
                requestGeneration: hydration,
                purpose: .hydration))
        model.handleFrame(snapshot(revision: 3))

        model.handleFrame(
            inbound(
                """
                {"type":"conversation_commit_ready","schema_version":1,
                 "chat_id":"\(chat)","connection_generation":"\(connection)",
                 "request_generation":"\(commit)","render_revision":4}
                """))
        model.handleFrame(
            snapshot(
                id: "66666666-6666-4666-8666-666666666666",
                request: commit,
                purpose: "commit",
                revision: 4,
                text: "Detached"))
        XCTAssertEqual(model.canvas.map(\.fallbackText), ["Detached"])

        model.handleFrame(
            inbound(
                """
                {"type":"conversation_commit_ready","schema_version":1,
                 "chat_id":"\(chat)",
                 "connection_generation":"99999999-9999-4999-8999-999999999999",
                 "request_generation":"88888888-8888-4888-8888-888888888888",
                 "render_revision":5}
                """))
        model.handleFrame(
            snapshot(
                id: "77777777-7777-4777-8777-777777777777",
                request: "88888888-8888-4888-8888-888888888888",
                purpose: "commit",
                revision: 5,
                text: "Wrong"))
        XCTAssertEqual(model.canvas.map(\.fallbackText), ["Detached"])
    }

    func testWatchNewTurnUsesCommitGenerationAndKeepsCommittedEntries() throws {
        let model = WatchModel(conversationResumeStore: store)
        XCTAssertTrue(model.beginConversationConnection(connection))
        XCTAssertTrue(
            model.openConversationRequest(
                chatId: chat,
                requestGeneration: hydration,
                purpose: .hydration))
        model.entries = [.status(id: "committed", text: "Committed")]
        model.pendingDictation = "Pending question"
        var sent: JSONValue?
        model.outboundTap = { text in
            sent = try? JSONValue.parse(Data(text.utf8))
        }

        model.sendPending()

        XCTAssertEqual(model.entries, [.status(id: "committed", text: "Committed")])
        XCTAssertEqual(model.visibleEntries.count, 2)
        XCTAssertEqual(sent?["payload"]?["snapshot_purpose"]?.stringValue, "commit")
        let request = try XCTUnwrap(sent?["payload"]?["request_generation"]?.stringValue)
        XCTAssertNotNil(
            request.range(
                of: "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
                options: .regularExpression))
    }

    func testWatchOpenChatPersistsBeforeSendingAndFourClearsAreDefinitive() {
        let model = WatchModel(conversationResumeStore: store)
        model.bindConversationAccount(account)
        let summary = ChatSummary(
            json: .object([
                "id": .string(chat), "title": .string("Saved"), "updated_at": .string("now"),
            ]))!
        var persistedAtSend = false
        model.outboundTap = { [store, account, chat] _ in
            persistedAtSend = store?.load(for: account)?.chatId == chat
        }
        model.openChat(summary)
        XCTAssertTrue(persistedAtSend)

        for reason in [
            ConversationResumeClearReason.newChat,
            .signOut,
            .accountRemoval,
        ] {
            XCTAssertTrue(store.save(chatId: chat, for: account))
            XCTAssertTrue(store.clear(reason, for: account))
        }
        XCTAssertTrue(store.save(chatId: chat, for: account))
        XCTAssertTrue(store.clear(.confirmedDeletion, for: account, chatId: chat))
    }
}
