/// Deterministic accessibility metadata shared by the Watch view and its tests.
struct WatchAccessibilityControl: Equatable {
    enum Role: String {
        case button
        case status
    }

    let identifier: String
    let role: Role
    let name: String
    let state: String
    let focusable: Bool
}

enum WatchAccessibility060 {
    static let replay = WatchAccessibilityControl(
        identifier: "watch-replay-response",
        role: .button,
        name: "Replay spoken response",
        state: "Ready",
        focusable: true)

    static func stop(isSpeaking: Bool) -> WatchAccessibilityControl {
        WatchAccessibilityControl(
            identifier: "watch-stop-speaking",
            role: .button,
            name: "Stop speaking",
            state: isSpeaking ? "Speaking" : "Idle",
            focusable: true)
    }

    static let dictate = WatchAccessibilityControl(
        identifier: "watch-dictate-message",
        role: .button,
        name: "Dictate message",
        state: "Ready",
        focusable: true)

    static let send = WatchAccessibilityControl(
        identifier: "watch-send-dictation",
        role: .button,
        name: "Send dictated message",
        state: "Ready",
        focusable: true)

    static let discard = WatchAccessibilityControl(
        identifier: "watch-discard-dictation",
        role: .button,
        name: "Discard dictated message",
        state: "Ready",
        focusable: true)

    static func operationStatus(_ state: String) -> WatchAccessibilityControl {
        WatchAccessibilityControl(
            identifier: "watch-operation-status",
            role: .status,
            name: "Operation status",
            state: state,
            focusable: false)
    }

    static func rootStatus(_ state: String) -> WatchAccessibilityControl {
        WatchAccessibilityControl(
            identifier: "watch-root-live-status",
            role: .status,
            name: "Live status",
            state: state,
            focusable: false)
    }
}
