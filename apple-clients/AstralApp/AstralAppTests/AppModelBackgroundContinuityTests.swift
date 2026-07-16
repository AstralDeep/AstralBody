import AstralCore
// 055 — cross-device background-task continuity, iOS/macOS reduce side:
// `task_completed`/`notification` frames that name the OPEN chat re-issue
// load_chat (the server persisted the output; reloading re-hydrates narrative
// + canvas); frames for a different chat surface as an info banner instead.
// `task_started` keeps the in-chat status line for the open chat and banners
// otherwise. Reconnect (`.connected` with an active chat) also re-issues
// load_chat — register_ui resumes the session but replays no turn frames.
// Outbound frames are observed via the model's `outboundTap` seam.
import XCTest

@testable import AstralDeep

@MainActor
final class AppModelBackgroundContinuityTests: XCTestCase {

    private final class FrameLog {
        var frames: [JSONValue] = []
    }

    private func record(_ model: AppModel) -> FrameLog {
        let log = FrameLog()
        model.outboundTap = { text in
            if let json = try? JSONValue.parse(Data(text.utf8)) { log.frames.append(json) }
        }
        return log
    }

    private func reduce(_ model: AppModel, _ json: String) {
        model.handleFrame(InboundFrame.parse(json)!)
    }

    private func loadChats(_ log: FrameLog) -> [String] {
        log.frames
            .filter { $0["action"]?.stringValue == "load_chat" }
            .compactMap { $0["payload"]?["chat_id"]?.stringValue }
    }

    // MARK: task_completed

    func testTaskCompletedForOpenChatReloadsIt() {
        let model = AppModel()
        model.activeChatId = "c1"
        let log = record(model)
        reduce(model, #"{"type":"task_completed","payload":{"task_id":"t1","chat_id":"c1","status":"completed"}}"#)
        XCTAssertEqual(loadChats(log), ["c1"])
        XCTAssertEqual(model.errorBanner, "Background task finished")
        XCTAssertFalse(model.bannerIsError)
    }

    func testTaskCompletedForOtherChatBannersWithoutReload() {
        let model = AppModel()
        model.activeChatId = "c1"
        let log = record(model)
        reduce(model, #"{"type":"task_completed","payload":{"task_id":"t1","chat_id":"c2","status":"completed"}}"#)
        XCTAssertTrue(loadChats(log).isEmpty)
        XCTAssertEqual(model.errorBanner, "Background task finished in another chat")
        XCTAssertFalse(model.bannerIsError)
    }

    func testTaskCompletedWithoutChatIdKeepsIssuingSocketBehavior() {
        // Pre-fan-out servers (watch_task ack) omit chat_id — the frame
        // targets the issuing socket and still refreshes the open chat.
        let model = AppModel()
        model.activeChatId = "c1"
        let log = record(model)
        reduce(model, #"{"type":"task_completed","payload":{"task_id":"t1","status":"completed"}}"#)
        XCTAssertEqual(loadChats(log), ["c1"])
        XCTAssertEqual(model.errorBanner, "Background task finished")
    }

    // MARK: task_started

    func testTaskStartedForOpenChatSetsStatusLine() {
        let model = AppModel()
        model.activeChatId = "c1"
        reduce(model, #"{"type":"task_started","payload":{"task_id":"t1","chat_id":"c1","status":"queued"}}"#)
        XCTAssertEqual(model.statusText, "Working in the background…")
        XCTAssertTrue(model.asyncDetached)
        XCTAssertNil(model.errorBanner)
    }

    func testTaskStartedForOtherChatBannersInstead() {
        let model = AppModel()
        model.activeChatId = "c1"
        reduce(model, #"{"type":"task_started","payload":{"task_id":"t1","chat_id":"c2","status":"queued"}}"#)
        XCTAssertNil(model.statusText)
        XCTAssertFalse(model.asyncDetached)
        XCTAssertEqual(model.errorBanner, "Background task started in another chat")
        XCTAssertFalse(model.bannerIsError)
    }

    // MARK: notification

    func testNotificationForOpenChatBannersAndReloads() {
        let model = AppModel()
        model.activeChatId = "c1"
        let log = record(model)
        // Scheduler shape: chat_id/title/body/level at the top level.
        reduce(
            model, #"{"type":"notification","level":"info","chat_id":"c1","title":"Job done","body":"Digest ready"}"#)
        XCTAssertEqual(model.errorBanner, "Job done: Digest ready")
        XCTAssertFalse(model.bannerIsError)
        XCTAssertEqual(loadChats(log), ["c1"])
    }

    func testNotificationForOtherChatBannersWithoutReload() {
        let model = AppModel()
        model.activeChatId = "c1"
        let log = record(model)
        reduce(model, #"{"type":"notification","level":"error","chat_id":"c2","title":"Job failed","body":"boom"}"#)
        XCTAssertEqual(model.errorBanner, "Job failed: boom")
        XCTAssertTrue(model.bannerIsError)
        XCTAssertTrue(loadChats(log).isEmpty)
    }

    func testChatAgnosticNotificationNeverReloads() {
        let model = AppModel()
        model.activeChatId = "c1"
        let log = record(model)
        reduce(model, #"{"type":"notification","level":"info","title":"Reader live","body":"Ask again"}"#)
        XCTAssertEqual(model.errorBanner, "Reader live: Ask again")
        XCTAssertTrue(loadChats(log).isEmpty)
    }

    // MARK: reconnect

    func testReconnectReissuesLoadChatForActiveChat() async {
        let model = AppModel()
        model.activeChatId = "c1"
        let log = record(model)
        await model.handle(.connected)
        XCTAssertEqual(loadChats(log), ["c1"])
    }

    func testFirstConnectWithoutActiveChatSendsNothing() async {
        let model = AppModel()
        let log = record(model)
        await model.handle(.connected)
        XCTAssertTrue(log.frames.isEmpty)
    }
}
