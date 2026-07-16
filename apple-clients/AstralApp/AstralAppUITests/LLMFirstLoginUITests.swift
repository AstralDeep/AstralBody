import XCTest

final class LLMFirstLoginUITests: XCTestCase {
    private var app: XCUIApplication!

    override func tearDown() {
        app?.terminate()
        app = nil
        super.tearDown()
    }

    func testImmediateFeedbackPhaseResponsivenessAndSuccess() {
        launch(scenario: "slow-success")
        let form = element("llm-provider-form-title")
        let apiKey = app.secureTextFields["param-field-api_key"]
        let save = app.buttons["llm-save-button"]

        XCTAssertTrue(form.waitForExistence(timeout: 5))
        XCTAssertTrue(apiKey.waitForExistence(timeout: 2))
        XCTAssertTrue(save.waitForExistence(timeout: 2))
        apiKey.tap()
        apiKey.typeText("ui-only-placeholder")

        save.tap()
        let status = element("llm-save-status")
        XCTAssertTrue(
            status.waitForExistence(timeout: 0.25),
            "Save must expose local-only submitting feedback within 250 ms")
        let acknowledgedAt = Date()
        XCTAssertEqual(status.label, "AI provider setup status")
        XCTAssertFalse(save.isEnabled, "only the duplicate Save control is single-flight disabled")
        XCTAssertEqual(save.value as? String, "Submitting")

        // Editing and focus stay responsive while the operation is active.
        XCTAssertTrue(apiKey.isEnabled)
        apiKey.tap()
        apiKey.typeText("x")

        let activePhaseObserved = waitForStatus(
            status,
            containingAny: [
                "Waiting to check",
                "Checking your provider credentials",
                "Saving credentials",
            ],
            timeout: 1.25)
        XCTAssertTrue(
            activePhaseObserved || !form.exists,
            "an operation still active after one second must expose its current phase")
        let remaining = max(0, 5 - Date().timeIntervalSince(acknowledgedAt))
        XCTAssertTrue(form.waitForNonExistence(timeout: remaining))
        let advanceObservedAt = Date()
        XCTAssertLessThan(
            advanceObservedAt.timeIntervalSince(acknowledgedAt),
            5,
            "durably completed first-login setup must advance exactly once within five seconds")
    }

    func testInvalidCredentialTerminalKeepsSecureFormEditableAndRetryable() {
        launch(scenario: "invalid-credentials")
        let apiKey = app.secureTextFields["param-field-api_key"]
        let save = app.buttons["llm-save-button"]
        XCTAssertTrue(apiKey.waitForExistence(timeout: 5))
        apiKey.tap()
        apiKey.typeText("invalid-ui-placeholder")
        save.tap()

        let status = element("llm-save-status")
        XCTAssertTrue(
            waitForStatus(status, containingAny: ["Check your provider credentials"], timeout: 3))
        XCTAssertTrue(apiKey.isEnabled)
        XCTAssertTrue(waitForEnabled(save, enabled: true, timeout: 2))
        XCTAssertEqual(save.value as? String, "Ready")

        apiKey.tap()
        apiKey.typeText("-corrected")
    }

    func testProviderUnavailableTerminalIsExplicitAndRetryable() {
        launch(scenario: "provider-unavailable")
        let apiKey = app.secureTextFields["param-field-api_key"]
        let save = app.buttons["llm-save-button"]
        XCTAssertTrue(apiKey.waitForExistence(timeout: 5))
        apiKey.tap()
        apiKey.typeText("unavailable-ui-placeholder")
        save.tap()

        let status = element("llm-save-status")
        XCTAssertTrue(
            waitForStatus(status, containingAny: ["Provider unavailable"], timeout: 3))
        XCTAssertTrue(apiKey.isEnabled)
        XCTAssertTrue(save.isEnabled)
        XCTAssertTrue(element("llm-provider-form-title").exists)
    }

    func testTenSecondWatchdogEndsLoadingWithoutInventingServerTerminal() {
        launch(scenario: "client-watchdog")
        let apiKey = app.secureTextFields["param-field-api_key"]
        let save = app.buttons["llm-save-button"]
        XCTAssertTrue(apiKey.waitForExistence(timeout: 5))
        apiKey.tap()
        apiKey.typeText("timeout-ui-placeholder")

        save.tap()
        let status = element("llm-save-status")
        XCTAssertTrue(status.waitForExistence(timeout: 0.25))
        let acknowledgedAt = Date()
        exerciseSceneOrWindowResponsiveness()
        XCTAssertTrue(
            waitForStatus(status, containingAny: ["Unable to confirm; reconnecting"], timeout: 11))
        XCTAssertLessThan(Date().timeIntervalSince(acknowledgedAt), 11.5)
        XCTAssertTrue(apiKey.isEnabled)
        XCTAssertTrue(save.isEnabled)
        XCTAssertEqual(save.value as? String, "Ready")

        // Explicit status retry reconciles the same identity; it must not
        // create another local submitting operation or restart the spinner.
        save.tap()
        XCTAssertTrue(save.isEnabled)
        let retainedStatus = element("llm-save-status")
        XCTAssertEqual(retainedStatus.value as? String, "Unable to confirm; reconnecting")
    }

    private func launch(scenario: String) {
        app = XCUIApplication()
        app.launchArguments = ["--astral-ui-test-first-login", scenario]
        app.launchEnvironment["ASTRAL_UI_TESTING"] = "1"
        app.launch()
    }

    private func element(_ identifier: String) -> XCUIElement {
        app.descendants(matching: .any)[identifier]
    }

    private func waitForStatus(
        _ status: XCUIElement,
        containingAny fragments: [String],
        timeout: TimeInterval
    ) -> Bool {
        let predicate = NSPredicate { candidate, _ in
            guard let element = candidate as? XCUIElement,
                let value = element.value as? String
            else { return false }
            return fragments.contains { value.localizedCaseInsensitiveContains($0) }
        }
        let expectation = XCTNSPredicateExpectation(predicate: predicate, object: status)
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    private func waitForEnabled(
        _ element: XCUIElement,
        enabled: Bool,
        timeout: TimeInterval
    ) -> Bool {
        let predicate = NSPredicate { candidate, _ in
            (candidate as? XCUIElement)?.isEnabled == enabled
        }
        let expectation = XCTNSPredicateExpectation(predicate: predicate, object: element)
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }

    private func exerciseSceneOrWindowResponsiveness() {
        #if os(iOS)
            XCUIDevice.shared.press(.home)
            app.activate()
            let foreground = NSPredicate { candidate, _ in
                (candidate as? XCUIApplication)?.state == .runningForeground
            }
            let expectation = XCTNSPredicateExpectation(predicate: foreground, object: app)
            XCTAssertEqual(XCTWaiter.wait(for: [expectation], timeout: 2), .completed)
        #else
            app.activate()
            XCTAssertTrue(app.windows.firstMatch.waitForExistence(timeout: 1))
        #endif
    }
}
