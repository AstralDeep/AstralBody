// Feature 055 edge case — a device joining mid-stream gets the current
// component state, not a blank placeholder: `stream_subscribed` after
// load_chat has already re-hydrated the streamed component must leave it in
// place (web twin: the client.js `stream_subscribed` guard). The guard checks
// the pendingReplace-selected list — the same one applyCanvasOps mutates —
// so a mid-turn ack can't blank a buffered component either.
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

    func testMidTurnGuardChecksPendingCanvasNotCommitted() {
        let model = AppModel()
        model.sendChat("working…")   // arms pendingReplace
        model.pendingCanvas = [liveChartCard]
        reduce(model, subscribedFrame)
        XCTAssertEqual(model.pendingCanvas.map(\.componentId), ["wc_abc"])
        XCTAssertEqual(model.pendingCanvas[0].type, "card")
    }

    func testMidTurnPlaceholderStillBuffersWhenPendingCanvasLacksIdentity() {
        let model = AppModel()
        model.canvas = [liveChartCard]   // committed copy doesn't shadow the pending list
        model.sendChat("working…")
        reduce(model, subscribedFrame)
        XCTAssertEqual(model.pendingCanvas.map(\.componentId), ["wc_abc"])
        XCTAssertEqual(model.pendingCanvas[0].type, "text")
    }
}
