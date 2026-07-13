// Feature 055 (US1) — first-turn contract reduce tests: welcome components
// arrive with `wel_`-prefixed identities and the server no longer sends the
// turn-start blanking `ui_render []`, so the CLIENT purges `wel_` from the
// committed canvas in the same mutation that arms `pendingReplace` (sendChat
// AND the sendEvent chat_message path) and keeps `wel_` out of every
// canvas-history archive (commitTurn). The purge is unconditional — with the
// server flag off the welcome ships id-less and nothing matches. The pinned
// commit-on-done lifecycle is otherwise untouched (regression pinned below).
import XCTest
import AstralCore
@testable import AstralDeep

@MainActor
final class AppModelFirstTurnContractTests: XCTestCase {

    private let doneStatus = #"{"type":"chat_status","status":"done"}"#
    private let resultUpsert = #"{"type":"ui_upsert","ops":[{"op":"upsert","component_id":"wc_result","component":{"type":"card","component_id":"wc_result","title":"Result"}}]}"#

    private func component(_ fields: [String: JSONValue]) -> AstralComponent {
        AstralComponent(json: .object(fields))!
    }

    private var welcomeHero: AstralComponent {
        component(["type": .string("hero"), "id": .string("wel_hero"),
                   "component_id": .string("wel_hero"), "heading": .string("Welcome")])
    }
    private var welcomeExamples: AstralComponent {
        component(["type": .string("card"), "id": .string("wel_examples"),
                   "component_id": .string("wel_examples"), "title": .string("Try asking")])
    }
    /// Carries only `id` — the purge keys on `component_id ?? id`.
    private var welcomeHint: AstralComponent {
        component(["type": .string("text"), "id": .string("wel_hint"),
                   "content": .string("Pick an agent")])
    }
    private var workspaceCard: AstralComponent {
        component(["type": .string("card"), "component_id": .string("wc_abc123"),
                   "title": .string("Budget")])
    }

    private func reduce(_ model: AppModel, _ json: String) {
        model.handleFrame(InboundFrame.parse(json)!)
    }

    // MARK: arming purge (sendChat / sendEvent chat_message)

    func testSendChatPurgesWelcomeWhenArming() {
        let model = AppModel()
        model.canvas = [welcomeHero, welcomeExamples, welcomeHint]
        model.sendChat("what's the weather?")
        XCTAssertTrue(model.pendingReplace)
        XCTAssertTrue(model.canvas.isEmpty)
    }

    func testSendChatKeepsNonWelcomeComponents() {
        let model = AppModel()
        model.canvas = [welcomeHero, workspaceCard]
        model.sendChat("hello")
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_abc123"])
    }

    func testSendEventChatMessagePurgesWelcomeWhenArming() {
        let model = AppModel()
        model.canvas = [welcomeHero, welcomeHint]
        model.sendEvent("chat_message", .object(["message": .string("hi")]))
        XCTAssertTrue(model.pendingReplace)
        XCTAssertTrue(model.canvas.isEmpty)
    }

    // MARK: history-leak regression (commitTurn archive filter)

    func testCommitNeverArchivesWelcomeToHistory() {
        let model = AppModel()
        model.canvas = [workspaceCard]
        model.sendChat("first")
        // A welcome resurrecting mid-turn (reconnect re-register) must still
        // never reach the timeline.
        model.canvas = [welcomeHero, workspaceCard]
        reduce(model, resultUpsert)   // buffers into pendingCanvas
        reduce(model, doneStatus)     // commit
        XCTAssertEqual(model.canvasHistory.count, 1)
        XCTAssertEqual(model.canvasHistory[0].components.map(\.componentId), ["wc_abc123"])
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_result"])
    }

    func testCommitSkipsHistoryWhenOnlyWelcomeWasShowing() {
        let model = AppModel()
        model.canvas = [welcomeHero, welcomeExamples]
        model.sendChat("first")
        model.canvas = [welcomeHero]   // resurrected mid-turn
        reduce(model, resultUpsert)
        reduce(model, doneStatus)
        XCTAssertTrue(model.canvasHistory.isEmpty)   // welcome-only ⇒ no snapshot
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_result"])
    }

    // MARK: text-only resurrection regression

    func testTextOnlyTurnDropsWelcomeFromKeptCanvas() {
        let model = AppModel()
        model.sendChat("just a question")
        model.canvas = [welcomeHero, workspaceCard]   // resurrected mid-turn
        reduce(model, doneStatus)   // no components this turn — canvas kept
        XCTAssertFalse(model.turnActive)
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_abc123"])
        XCTAssertTrue(model.canvasHistory.isEmpty)
    }

    // MARK: pinned lifecycle unchanged for non-welcome canvases

    func testCommitStillArchivesAPlainCanvas() {
        let model = AppModel()
        model.canvas = [workspaceCard]
        model.sendChat("next")
        reduce(model, resultUpsert)
        reduce(model, doneStatus)
        XCTAssertEqual(model.canvasHistory.count, 1)
        XCTAssertEqual(model.canvasHistory[0].components, [workspaceCard])
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_result"])
    }
}
