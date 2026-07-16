// Feature 055 (US1) — the uniform welcome purge (`[AstralComponent].dropWelcome`):
// welcome components carry `wel_`-prefixed identities on BOTH `id` and
// `component_id` (wire-contract §1), and the client drops them from committed
// canvas state at turn start — the watch, which has no turn state, at every
// `ui_upsert` apply. Unconditional client-side: an id-less legacy welcome
// (server flag off) matches nothing and the purge is a byte-equivalent no-op.
import XCTest

@testable import AstralCore

final class WelcomePurgeTests: XCTestCase {

    private func component(_ json: String) -> AstralComponent {
        let value = try! JSONValue.parse(json.data(using: .utf8)!)
        return AstralComponent(json: value)!
    }

    // MARK: dropWelcome

    func testDropsWelcomeByComponentIdAndByIdFallback() {
        let canvas = [
            component(#"{"type":"hero","id":"wel_hero","component_id":"wel_hero","heading":"Welcome"}"#),
            component(#"{"type":"text","id":"wel_hint","content":"Pick an agent"}"#),  // id-only read
            component(#"{"type":"card","component_id":"wc_kept","title":"Budget"}"#),
        ]
        XCTAssertEqual(canvas.dropWelcome().map(\.componentId), ["wc_kept"])
    }

    func testKeepsIdLessAndNearMissIdentities() {
        let canvas = [
            component(#"{"type":"text","content":"anonymous"}"#),  // id-less (flag off)
            component(#"{"type":"card","component_id":"weld_report","title":"Welding"}"#),
            component(#"{"type":"card","component_id":"welcome","title":"No underscore"}"#),
        ]
        XCTAssertEqual(canvas.dropWelcome().count, 3)
    }

    // MARK: watch ui_upsert composition — WatchModel has no test target, so the
    // exact reducer expression `Canvas.apply(canvas.dropWelcome(), ops)` is
    // pinned here: first-turn content never lands under a retained welcome.

    func testWatchUpsertNeverLandsUnderRetainedWelcome() {
        let welcome = [
            component(#"{"type":"hero","id":"wel_hero","component_id":"wel_hero","heading":"Welcome"}"#),
            component(#"{"type":"card","id":"wel_examples","component_id":"wel_examples","title":"Try asking"}"#),
        ]
        let ops = [
            UpsertOp(
                op: "upsert", componentId: "wc_result",
                component: component(#"{"type":"card","component_id":"wc_result","title":"Result"}"#))
        ]
        XCTAssertEqual(Canvas.apply(welcome.dropWelcome(), ops).map(\.componentId), ["wc_result"])
    }

    func testWatchUpsertKeepsNonWelcomeComponents() {
        let mixed = [
            component(#"{"type":"card","id":"wel_enable","component_id":"wel_enable","title":"Enable agents"}"#),
            component(#"{"type":"table","component_id":"wc_prior","title":"Prior"}"#),
        ]
        let ops = [
            UpsertOp(
                op: "upsert", componentId: "wc_new",
                component: component(#"{"type":"card","component_id":"wc_new","title":"New"}"#))
        ]
        XCTAssertEqual(Canvas.apply(mixed.dropWelcome(), ops).map(\.componentId), ["wc_prior", "wc_new"])
    }
}
