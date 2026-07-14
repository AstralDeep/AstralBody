// Live-op rule (retires the 044 origin/co-viewer divergence): while a turn is
// armed (`pendingReplace`), identity-keyed `ui_upsert`/stream ops apply
// IMMEDIATELY to the visible canvas — morph-in-place, exactly as when no turn
// is armed — so the originating device renders partial output just like
// co-viewing devices. Only full `ui_render` replaces still buffer into
// `pendingCanvas` (the actual mid-turn clobber hazard); a buffered render
// wins at commit, with mid-turn ops mirrored into it so nothing applied live
// is lost. The first live op clears the query-start skeleton (web parity:
// first canvas content hides it) without ending the turn-active state.
import XCTest
import AstralCore
@testable import AstralDeep

@MainActor
final class AppModelLiveCanvasTests: XCTestCase {

    private var workspaceCard: AstralComponent {
        AstralComponent(json: .object([
            "type": .string("card"), "component_id": .string("wc_abc123"),
            "title": .string("Budget"),
        ]))!
    }

    private let doneStatus = #"{"type":"chat_status","status":"done"}"#
    private let resultUpsert = #"{"type":"ui_upsert","ops":[{"op":"upsert","component_id":"wc_result","component":{"type":"card","component_id":"wc_result","title":"Result"}}]}"#
    private let designedRender = #"{"type":"ui_render","target":"canvas","components":[{"type":"card","component_id":"wc_designed","title":"Designed"}]}"#

    private func reduce(_ model: AppModel, _ json: String) {
        model.handleFrame(InboundFrame.parse(json)!)
    }

    // MARK: upsert ops go live mid-turn

    func testUpsertAppliesToVisibleCanvasMidTurn() {
        let model = AppModel()
        model.canvas = [workspaceCard]
        model.sendChat("go")
        reduce(model, resultUpsert)
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_abc123", "wc_result"])
        XCTAssertTrue(model.pendingCanvas.isEmpty)   // no render — nothing buffered
        XCTAssertTrue(model.turnActive)              // the turn is still running
    }

    func testUpsertOnlyTurnCommitsTheLiveCanvas() {
        let model = AppModel()
        model.canvas = [workspaceCard]
        model.sendChat("go")
        reduce(model, resultUpsert)
        reduce(model, doneStatus)
        // No replace happened: the live canvas IS the committed state —
        // no double-apply, no loss, and nothing archived to the timeline.
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_abc123", "wc_result"])
        XCTAssertTrue(model.canvasHistory.isEmpty)
        XCTAssertFalse(model.turnActive)
    }

    // MARK: full renders still buffer; the buffered render wins at commit

    func testRenderStaysBufferedUntilCommit() {
        let model = AppModel()
        model.canvas = [workspaceCard]
        model.sendChat("go")
        reduce(model, designedRender)
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_abc123"])   // visible canvas untouched
        XCTAssertEqual(model.pendingCanvas.map(\.componentId), ["wc_designed"])
        reduce(model, doneStatus)
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_designed"])
        XCTAssertEqual(model.canvasHistory.count, 1)
    }

    func testOpsAfterBufferedRenderMirrorIntoCommit() {
        let model = AppModel()
        model.sendChat("go")
        reduce(model, designedRender)
        reduce(model, resultUpsert)   // live AND mirrored into the buffer
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_result"])
        XCTAssertEqual(model.pendingCanvas.map(\.componentId), ["wc_designed", "wc_result"])
        reduce(model, doneStatus)
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_designed", "wc_result"])
    }

    // MARK: skeleton clears on the first live op, turn stays active

    func testFirstLiveOpClearsSkeletonWithoutEndingTurn() {
        let model = AppModel()
        model.sendChat("go")
        XCTAssertTrue(model.showSkeleton)
        reduce(model, resultUpsert)
        XCTAssertFalse(model.showSkeleton)
        XCTAssertTrue(model.turnActive)
    }

    func testBufferedRenderKeepsSkeleton() {
        let model = AppModel()
        model.sendChat("go")
        reduce(model, designedRender)   // invisible until commit — keep the shimmer
        XCTAssertTrue(model.showSkeleton)
    }

    func testStreamOpsGoLiveMidTurnAndClearSkeleton() {
        let model = AppModel()
        model.sendChat("go")
        reduce(model, #"{"type":"ui_stream_data","stream_id":"s1","seq":1,"components":[{"type":"text","content":"partial"}]}"#)
        XCTAssertEqual(model.canvas.map(\.componentId), ["stream-s1"])
        XCTAssertFalse(model.showSkeleton)
        XCTAssertTrue(model.pendingCanvas.isEmpty)
    }

    func testNextTurnReArmsSkeleton() {
        let model = AppModel()
        model.sendChat("one")
        reduce(model, resultUpsert)
        reduce(model, doneStatus)
        model.sendChat("two")
        XCTAssertTrue(model.showSkeleton)   // liveOpsThisTurn resets on arm
    }
}
