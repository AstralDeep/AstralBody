import Foundation
import XCTest

final class ConversationContinuityUITests: XCTestCase {
    private var app: XCUIApplication!

    override func tearDown() {
        app?.terminate()
        app = nil
        super.tearDown()
    }

    func testDeterministicProcessRelaunchRestoresSemanticConversationTwentyTimes() {
        launch(scenario: "continuity-seed")
        assertSemanticConversation(timeout: 5)
        app.terminate()

        var durations: [TimeInterval] = []
        for trial in 1...20 {
            let startedAt = Date()
            launch(scenario: "continuity-resume")
            assertSemanticConversation(timeout: 5)
            let duration = Date().timeIntervalSince(startedAt)
            durations.append(duration)
            XCTAssertLessThan(
                duration,
                5,
                "trial \(trial) exceeded the five-second deterministic restoration bound")
            if trial < 20 { app.terminate() }
        }

        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "apple-continuity-twentieth-relaunch"
        screenshot.lifetime = .keepAlways
        add(screenshot)

        let hierarchy = XCTAttachment(
            data: Data(app.debugDescription.utf8),
            uniformTypeIdentifier: "public.plain-text")
        hierarchy.name = "apple-continuity-twentieth-relaunch-hierarchy"
        hierarchy.lifetime = .keepAlways
        add(hierarchy)

        let sorted = durations.sorted()
        let report = [
            "trials=\(durations.count)",
            "mean_seconds=\(format(durations.reduce(0, +) / Double(durations.count)))",
            "p50_seconds=\(format(percentile(0.50, sorted: sorted)))",
            "p95_seconds=\(format(percentile(0.95, sorted: sorted)))",
            "max_seconds=\(format(sorted.last ?? 0))",
            "samples_seconds=\(durations.map(format).joined(separator: ","))",
        ].joined(separator: "\n")
        let timing = XCTAttachment(
            data: Data(report.utf8), uniformTypeIdentifier: "public.plain-text")
        timing.name = "apple-continuity-relaunch-timings"
        timing.lifetime = .keepAlways
        add(timing)
    }

    func testLiveAuthenticatedProviderGateSurvivesTwentyRelaunches() throws {
        app = XCUIApplication()
        app.launch()
        guard app.staticTexts["Set up your AI provider"].waitForExistence(timeout: 5) else {
            throw XCTSkip("requires an explicitly prepared authenticated simulator session")
        }
        app.terminate()

        var durations: [TimeInterval] = []
        for trial in 1...20 {
            app = XCUIApplication()
            let startedAt = Date()
            app.launch()

            let providerGate = app.staticTexts["Set up your AI provider"]
            XCTAssertTrue(
                providerGate.waitForExistence(timeout: 5),
                "authenticated provider gate was not restored on trial \(trial)")
            XCTAssertFalse(app.buttons["Sign in"].exists)
            let duration = Date().timeIntervalSince(startedAt)
            durations.append(duration)
            XCTAssertLessThan(
                duration,
                5,
                "authenticated relaunch trial \(trial) exceeded five seconds")
            if trial < 20 { app.terminate() }
        }

        let sorted = durations.sorted()
        let report = [
            "surface=mandatory_provider_setup",
            "authentication=persisted_keycloak_pkce_session",
            "trials=\(durations.count)",
            "mean_seconds=\(format(durations.reduce(0, +) / Double(durations.count)))",
            "p50_seconds=\(format(percentile(0.50, sorted: sorted)))",
            "p95_seconds=\(format(percentile(0.95, sorted: sorted)))",
            "max_seconds=\(format(sorted.last ?? 0))",
            "samples_seconds=\(durations.map(format).joined(separator: ","))",
        ].joined(separator: "\n")
        let timing = XCTAttachment(
            data: Data(report.utf8), uniformTypeIdentifier: "public.plain-text")
        timing.name = "apple-live-authenticated-relaunch-timings"
        timing.lifetime = .keepAlways
        add(timing)
    }

    private func launch(scenario: String) {
        if app == nil { app = XCUIApplication() }
        app.launchArguments = ["--astral-ui-test-first-login", scenario]
        app.launchEnvironment["ASTRAL_UI_TESTING"] = "1"
        app.launch()
    }

    private func assertSemanticConversation(timeout: TimeInterval) {
        XCTAssertTrue(text(containing: "Continuity question").waitForExistence(timeout: timeout))
        XCTAssertTrue(text(containing: "continuity.pdf").exists)
        XCTAssertTrue(text(containing: "Continuity total: 21").exists)
        XCTAssertTrue(text(containing: "Continuity component answer").exists)
        XCTAssertTrue(text(containing: "Restored continuity canvas").exists)
        XCTAssertFalse(text(containing: "Your generated interface appears here").exists)
        XCTAssertFalse(text(containing: "locator was not restored").exists)
    }

    private func text(containing fragment: String) -> XCUIElement {
        app.staticTexts.matching(
            NSPredicate(format: "label CONTAINS[c] %@", fragment)
        ).firstMatch
    }

    private func percentile(_ fraction: Double, sorted: [TimeInterval]) -> TimeInterval {
        guard !sorted.isEmpty else { return 0 }
        let rank = max(0, min(sorted.count - 1, Int(ceil(fraction * Double(sorted.count))) - 1))
        return sorted[rank]
    }

    private func format(_ value: TimeInterval) -> String {
        String(format: "%.3f", value)
    }
}
