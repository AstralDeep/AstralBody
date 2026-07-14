// Feature 055 edge case — a device joining mid-stream gets the current
// component state, not a blank placeholder: `stream_subscribed` after
// load_chat has already re-hydrated the streamed component must leave it in
// place (web twin: the client.js `stream_subscribed` guard). Under the
// live-op rule ops target the VISIBLE canvas even mid-turn, so the guard
// reads the live canvas ids — the same list applyCanvasOps mutates — and a
// mid-turn ack can't blank what the user is looking at.
import XCTest
import AstralCore
@testable import AstralDeep

@MainActor
final class AppModelStreamJoinTests: XCTestCase {

    private var liveChartCard: AstralComponent {
        AstralComponent(json: .object([
            "type": .string("card"), "component_id": .string("wc_abc"),
            "title": .string("Live chart"),
        ]))!
    }

    private let subscribedFrame =
        #"{"type":"stream_subscribed","stream_id":"s1","tool_name":"live_chart","component_id":"wc_abc"}"#

    private func reduce(_ model: AppModel, _ json: String) {
        model.handleFrame(InboundFrame.parse(json)!)
    }

    func testMidStreamJoinKeepsRehydratedComponent() {
        let model = AppModel()
        model.canvas = [liveChartCard]
        reduce(model, subscribedFrame)
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_abc"])
        XCTAssertEqual(model.canvas[0].type, "card")   // not the text placeholder
    }

    func testSubscribedBuildsPlaceholderOnFreshCanvas() {
        let model = AppModel()
        reduce(model, subscribedFrame)
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_abc"])
        XCTAssertEqual(model.canvas[0].type, "text")
    }

    func testMidTurnGuardReadsTheLiveCanvas() {
        let model = AppModel()
        model.canvas = [liveChartCard]
        model.sendChat("working…")   // arms pendingReplace — the canvas stays live
        reduce(model, subscribedFrame)
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_abc"])
        XCTAssertEqual(model.canvas[0].type, "card")   // not the text placeholder
    }

    func testMidTurnPlaceholderAppliesLiveWhenCanvasLacksIdentity() {
        let model = AppModel()
        model.sendChat("working…")
        reduce(model, subscribedFrame)
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_abc"])
        XCTAssertEqual(model.canvas[0].type, "text")
        XCTAssertTrue(model.pendingCanvas.isEmpty)   // placeholders never start a buffer
    }
}
