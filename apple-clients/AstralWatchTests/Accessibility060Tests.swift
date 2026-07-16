import XCTest

@testable import AstralWatch

final class Accessibility060Tests: XCTestCase {
    func testEveryChangedInteractiveControlHasRoleNameStateAndFocusContract() {
        let controls = [
            WatchAccessibility060.replay,
            WatchAccessibility060.stop(isSpeaking: false),
            WatchAccessibility060.dictate,
            WatchAccessibility060.send,
            WatchAccessibility060.discard,
        ]

        XCTAssertEqual(Set(controls.map(\.identifier)).count, controls.count)
        for control in controls {
            XCTAssertEqual(control.role, .button)
            XCTAssertFalse(control.name.isEmpty)
            XCTAssertFalse(control.state.isEmpty)
            XCTAssertTrue(control.focusable)
        }
        XCTAssertEqual(WatchAccessibility060.stop(isSpeaking: false).state, "Idle")
        XCTAssertEqual(WatchAccessibility060.stop(isSpeaking: true).state, "Speaking")
    }

    func testOperationStatusHasStableLiveRegionMetadataAndIsNotInteractive() {
        let status = WatchAccessibility060.operationStatus("Working…")

        XCTAssertEqual(status.identifier, "watch-operation-status")
        XCTAssertEqual(status.role, .status)
        XCTAssertEqual(status.name, "Operation status")
        XCTAssertEqual(status.state, "Working…")
        XCTAssertFalse(status.focusable)

        let root = WatchAccessibility060.rootStatus("ua-dice: Online")
        XCTAssertEqual(root.identifier, "watch-root-live-status")
        XCTAssertEqual(root.role, .status)
        XCTAssertEqual(root.name, "Live status")
        XCTAssertEqual(root.state, "ua-dice: Online")
        XCTAssertFalse(root.focusable)
    }
}
