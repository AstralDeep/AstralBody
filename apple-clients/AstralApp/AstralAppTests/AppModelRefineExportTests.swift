import AstralCore
// Feature 055 (US4/US5) — send-side tests for the refine affordance and the
// export menu entries. The context menu's "Refine…" sheet lands in
// `refineComponent` (trim + guard + `component_refine` ui_event, wire-contract
// §3); refine/restore are timeline mutations (refused client-side while the
// read-only timeline view is active, like component_action); the export
// entries open URLs built by `exportComponentURL`/`exportCanvasURL`
// (chat-scoped per contracts/rest-endpoints.md). Outbound frames are observed
// via the model's `outboundTap` seam.
import XCTest

@testable import AstralDeep

@MainActor
final class AppModelRefineExportTests: XCTestCase {

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

    override func tearDown() {
        // serverBaseText persists via UserDefaults — never leak a test
        // endpoint into other suites (or the simulator's app defaults).
        UserDefaults.standard.removeObject(forKey: "serverBase")
        super.tearDown()
    }

    // MARK: component_refine send path

    func testRefineSendsComponentRefineUiEvent() {
        let model = AppModel()
        model.activeChatId = "chat-1"
        let log = record(model)
        model.refineComponent("wc_budget", instruction: "  make it monthly  ")
        XCTAssertEqual(log.frames.count, 1)
        let frame = log.frames[0]
        XCTAssertEqual(frame["type"]?.stringValue, "ui_event")
        XCTAssertEqual(frame["action"]?.stringValue, "component_refine")
        XCTAssertEqual(frame["session_id"]?.stringValue, "chat-1")
        XCTAssertEqual(frame["payload"]?["component_id"]?.stringValue, "wc_budget")
        XCTAssertEqual(frame["payload"]?["instruction"]?.stringValue, "make it monthly")
    }

    func testRefineEmptyInstructionNeverSends() {
        let model = AppModel()
        let log = record(model)
        model.refineComponent("wc_budget", instruction: "   \n ")
        XCTAssertTrue(log.frames.isEmpty)
    }

    func testRefineEmptyComponentIdNeverSends() {
        let model = AppModel()
        let log = record(model)
        model.refineComponent("", instruction: "sort it")
        XCTAssertTrue(log.frames.isEmpty)
    }

    func testRefineAndRestoreBlockedWhileTimelineReadOnly() {
        let model = AppModel()
        model.handleFrame(InboundFrame.parse(#"{"type":"workspace_timeline_mode","active":true}"#)!)
        let log = record(model)
        model.refineComponent("wc_budget", instruction: "sort it")
        model.sendEvent(
            "component_restore",
            .object([
                "component_id": .string("wc_budget"), "version_no": .number(2),
            ]))
        XCTAssertTrue(log.frames.isEmpty)
        // Leaving the timeline view unblocks the same call.
        model.handleFrame(InboundFrame.parse(#"{"type":"workspace_timeline_mode","active":false}"#)!)
        model.refineComponent("wc_budget", instruction: "sort it")
        XCTAssertEqual(log.frames.count, 1)
    }

    // MARK: export URL builders

    func testExportComponentURLIsChatScoped() {
        let model = AppModel()
        model.serverBaseText = "https://astral.example"
        model.activeChatId = "chat-9"
        XCTAssertEqual(
            model.exportComponentURL("wc_tbl")?.absoluteString,
            "https://astral.example/api/export/component/wc_tbl.csv?chat_id=chat-9")
    }

    func testExportCanvasURL() {
        let model = AppModel()
        model.serverBaseText = "https://astral.example"
        model.activeChatId = "chat-9"
        XCTAssertEqual(
            model.exportCanvasURL()?.absoluteString,
            "https://astral.example/api/export/canvas/chat-9.html")
    }

    func testExportURLsNilWithoutActiveChat() {
        let model = AppModel()
        model.serverBaseText = "https://astral.example"
        model.activeChatId = nil
        XCTAssertNil(model.exportComponentURL("wc_tbl"))
        XCTAssertNil(model.exportCanvasURL())
    }
}
