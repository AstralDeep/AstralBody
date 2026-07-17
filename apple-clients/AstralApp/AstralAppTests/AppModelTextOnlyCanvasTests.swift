import AstralCore
// Regression cover for two ways a native client could strand the user on a
// screen it has no way to leave:
//
//  1. The canvas skeleton (`pendingReplace && !liveOpsThisTurn`) is armed at
//     turn start and, in CONTINUITY mode, was released only by a committed
//     `conversation_snapshot`. A text-only answer ("hello") produces no canvas
//     ops and no snapshot, so the shimmer latched forever over a canvas that
//     was already correct. `chat_status done` now releases it — safe because
//     the server publishes any snapshot BEFORE the terminal status.
//  2. `SurfaceView` is a full screen with no ✕ (web's modal shell) and no
//     system Back (Android), so `closeSurface()` is its only dismissal — and,
//     like web's `data-mandatory` card, it must refuse while the 054 pin is set.
import XCTest

@testable import AstralDeep

@MainActor
final class AppModelTextOnlyCanvasTests: XCTestCase {

    private let doneStatus = #"{"type":"chat_status","status":"done"}"#
    private let resultUpsert =
        #"{"type":"ui_upsert","ops":[{"op":"upsert","component_id":"wc_result","component":{"type":"card","component_id":"wc_result","title":"Result"}}]}"#

    private func component(_ fields: [String: JSONValue]) -> AstralComponent {
        AstralComponent(json: .object(fields))!
    }

    private var welcomeExamples: AstralComponent {
        component([
            "type": .string("card"), "id": .string("wel_examples"),
            "component_id": .string("wel_examples"), "title": .string("Try asking"),
        ])
    }
    private var workspaceCard: AstralComponent {
        component([
            "type": .string("card"), "component_id": .string("wc_abc123"),
            "title": .string("Budget"),
        ])
    }

    private func reduce(_ model: AppModel, _ json: String) {
        model.handleFrame(InboundFrame.parse(json)!)
    }

    /// A model in continuity mode (the `FF_BG_CONTINUITY` posture).
    private func continuityModel() -> AppModel {
        let model = AppModel()
        XCTAssertTrue(
            model.beginConversationConnection(UUID().uuidString.lowercased()))
        return model
    }

    // MARK: text-only turn releases the skeleton

    func testTextOnlyTurnInContinuityModeKeepsTheWelcomeAndClearsTheSkeleton() {
        let model = continuityModel()
        model.canvas = [welcomeExamples]
        model.sendChat("hello")
        XCTAssertTrue(model.showSkeleton)  // armed while the turn runs

        reduce(model, doneStatus)  // text-only: no ops, no snapshot

        XCTAssertFalse(model.showSkeleton, "the shimmer must not latch forever")
        XCTAssertFalse(model.turnActive)
        // Nothing replaced the canvas, so the run-examples screen stays put.
        XCTAssertEqual(model.canvas.map(\.componentId), ["wel_examples"])
    }

    func testTextOnlyTurnInContinuityModeKeepsAnExistingCanvas() {
        let model = continuityModel()
        model.canvas = [workspaceCard]
        model.sendChat("hello")

        reduce(model, doneStatus)

        XCTAssertFalse(model.showSkeleton)
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_abc123"])
    }

    /// Legacy mode still commits through `commitTurn` untouched: a live op
    /// retires the welcome and the committed canvas is the turn's output.
    func testLegacyComponentTurnStillCommitsItsComponents() {
        let model = AppModel()
        model.canvas = [welcomeExamples]
        model.sendChat("chart it")
        reduce(model, resultUpsert)
        reduce(model, doneStatus)

        XCTAssertFalse(model.showSkeleton)
        XCTAssertEqual(model.canvas.map(\.componentId), ["wc_result"])
    }

    // MARK: surface dismissal

    func testCloseSurfaceDismissesASettingsSurface() {
        let model = AppModel()
        model.screen = .surface
        model.pendingSurfaceKey = "llm"
        model.pendingSurface = AppModel.SurfaceContent(
            surfaceKey: "llm", title: "AI provider", components: [])

        model.closeSurface()

        XCTAssertEqual(model.screen, .chat)
        XCTAssertNil(model.pendingSurface)
        XCTAssertEqual(model.pendingSurfaceKey, "")
    }

    func testCloseSurfaceRefusesWhileTheMandatoryGateIsPinned() {
        let model = AppModel()
        model.screen = .surface
        model.pendingSurfaceKey = "llm"
        model.pendingSurface = AppModel.SurfaceContent(
            surfaceKey: "llm", title: "Set up your AI provider", components: [])
        model.mandatorySurface = true

        model.closeSurface()

        // 054 FR-013: the pin is server-owned; sign-out is the one escape.
        XCTAssertEqual(model.screen, .surface)
        XCTAssertNotNil(model.pendingSurface)
    }

    /// The server's blank close instruction (a settings-path save now sends it
    /// to natives, and the 054 unlock always did) lands on the chat.
    func testBlankChromeSurfaceClosesTheSurfaceAndLiftsThePin() {
        let model = AppModel()
        model.screen = .surface
        model.pendingSurfaceKey = "llm"
        model.mandatorySurface = true
        model.pendingSurface = AppModel.SurfaceContent(
            surfaceKey: "llm", title: "AI provider", components: [])

        reduce(
            model,
            #"{"type":"chrome_surface","region":"modal","surface_key":"","title":"","components":[],"mode":"replace"}"#
        )

        XCTAssertEqual(model.screen, .chat)
        XCTAssertFalse(model.mandatorySurface)
        XCTAssertNil(model.pendingSurface)
    }
}
