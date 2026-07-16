import XCTest

final class Accessibility060UITests: XCTestCase {
    private var app: XCUIApplication!

    override func tearDown() {
        app?.terminate()
        app = nil
        super.tearDown()
    }

    func testFirstLoginControlsExposeStableRoleNameStateAndFocusBehavior() {
        app = XCUIApplication()
        app.launchArguments = ["--astral-ui-test-first-login", "invalid-credentials"]
        app.launchEnvironment["ASTRAL_UI_TESTING"] = "1"
        app.launch()

        let apiKey = app.secureTextFields["param-field-api_key"]
        let save = app.buttons["llm-save-button"]
        XCTAssertTrue(apiKey.waitForExistence(timeout: 5))
        XCTAssertEqual(apiKey.elementType, .secureTextField)
        XCTAssertEqual(apiKey.label, "API key")
        XCTAssertTrue(apiKey.isEnabled)
        XCTAssertTrue(apiKey.isHittable)

        apiKey.tap()
        #if os(iOS)
            XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 2))
        #endif
        apiKey.typeText("accessibility-placeholder")
        XCTAssertFalse((apiKey.value as? String ?? "").isEmpty)

        XCTAssertTrue(save.waitForExistence(timeout: 2))
        XCTAssertEqual(save.elementType, .button)
        XCTAssertEqual(save.label, "Save")
        XCTAssertEqual(save.value as? String, "Ready")
        XCTAssertTrue(save.isEnabled)
        XCTAssertTrue(save.isHittable)

        save.tap()
        let status = app.descendants(matching: .any)["llm-save-status"]
        XCTAssertTrue(status.waitForExistence(timeout: 0.25))
        XCTAssertEqual(status.label, "AI provider setup status")
        XCTAssertFalse((status.value as? String ?? "").isEmpty)
        XCTAssertFalse(save.isEnabled)
        XCTAssertEqual(save.value as? String, "Submitting")
    }

    func testMainComposerUsesSystemKeyboardWithoutApplicationDrawnDoneAccessory() {
        app = XCUIApplication()
        app.launchArguments = ["--astral-ui-test-first-login", "chat-composer"]
        app.launchEnvironment["ASTRAL_UI_TESTING"] = "1"
        app.launch()

        let composer = app.textFields["chat-composer-input"]
        XCTAssertTrue(composer.waitForExistence(timeout: 5))
        XCTAssertEqual(composer.label, "Message AstralDeep")
        XCTAssertTrue(composer.isEnabled)
        XCTAssertTrue(composer.isHittable)

        composer.tap()
        let keyboard = app.keyboards.firstMatch
        XCTAssertTrue(keyboard.waitForExistence(timeout: 2))
        composer.typeText("runtime keyboard check")

        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "ios-main-composer-system-keyboard"
        screenshot.lifetime = .keepAlways
        add(screenshot)

        let hierarchy = XCTAttachment(
            data: Data(app.debugDescription.utf8), uniformTypeIdentifier: "public.plain-text")
        hierarchy.name = "ios-main-composer-ui-hierarchy"
        hierarchy.lifetime = .keepAlways
        add(hierarchy)

        let doneButtons = app.buttons.matching(
            NSPredicate(format: "label ==[c] %@", "Done"))
        for button in doneButtons.allElementsBoundByIndex {
            XCTAssertTrue(
                keyboard.frame.intersects(button.frame),
                "A Done button outside the system keyboard is an application-drawn accessory")
        }

        let nativeSend = keyboard.buttons["send"]
        XCTAssertTrue(nativeSend.waitForExistence(timeout: 2))
        XCTAssertTrue(keyboard.frame.intersects(nativeSend.frame))

        // The fixture initially renders the overflowing transcript at its top.
        // Scroll into the transcript, then use the native interactive downward
        // dismissal gesture rather than an application-drawn keyboard accessory.
        let messageScroll = app.scrollViews["conversation-message-scroll"]
        XCTAssertTrue(messageScroll.waitForExistence(timeout: 2))
        messageScroll.swipeUp()
        if keyboard.exists { messageScroll.swipeDown() }
        XCTAssertTrue(waitForNonExistence(keyboard, timeout: 2))
    }

    private func waitForNonExistence(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == false"), object: element)
        return XCTWaiter.wait(for: [expectation], timeout: timeout) == .completed
    }
}
