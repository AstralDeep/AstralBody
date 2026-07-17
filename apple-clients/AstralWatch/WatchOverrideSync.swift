import AstralCore
// Feature 053 — receives the backend endpoint override pushed by the iPhone
// companion (FR-011).
//
// This is an OPPORTUNISTIC optimization and never a dependency. The watch app is
// an embedded companion that still runs independently
// (`WKRunsIndependentlyOfCompanionApp`), so a user may install it from the Watch
// App Store and never install the iPhone app at all. Apple is explicit that an
// independent watchOS app "can't rely on the Watch Connectivity framework to
// transfer data or files from a companion iOS app".
//
// So: when no companion is installed, or the companion pushes nothing, or it
// pushes junk, the watch keeps its build-time endpoint (Config/*.xcconfig) and
// stays fully usable via QR device-login. The override may only ever *narrow*
// which backend we talk to — it can never strand the watch.
import Foundation
import WatchConnectivity

final class WatchOverrideSync: NSObject, WCSessionDelegate {
    static let shared = WatchOverrideSync()

    /// Posted after a companion override lands, so the model can rebuild its clients.
    static let didChangeNotification = Notification.Name("AstralWatchServerOverrideDidChange")

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        super.init()
    }

    /// The endpoint this watch should talk to right now: a validated companion
    /// override if we have one, else the build-time default.
    static func resolvedServerBase(defaults: UserDefaults = .standard) -> URL {
        let override = defaults.string(forKey: AstralConfig.serverOverrideDefaultsKey)
        let resolved = AstralConfig.resolvedServerBaseURL(override: override)
        // `resolvedServerBaseURL` already fell back to a compiled-in production
        // endpoint, so this force-unwrap cannot trap on user input.
        return URL(string: resolved) ?? URL(string: AstralConfig.fallbackServerBaseURL)!
    }

    /// Safe to call unconditionally; a no-op where Watch Connectivity is unsupported.
    func activate() {
        guard WCSession.isSupported() else { return }
        let session = WCSession.default
        session.delegate = self
        session.activate()
    }

    // MARK: - WCSessionDelegate

    func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {
        guard error == nil, activationState == .activated else { return }
        // No companion installed => nothing will ever arrive. That is a supported
        // state, not an error: we simply keep the build-time endpoint.
        guard session.isCompanionAppInstalled else { return }
        // A context pushed while we were not running is waiting for us here.
        apply(session.receivedApplicationContext)
    }

    func session(_ session: WCSession, didReceiveApplicationContext context: [String: Any]) {
        apply(context)
    }

    // MARK: - internals

    /// Persist a pushed override only if it is a usable endpoint and actually new.
    private func apply(_ context: [String: Any]) {
        let raw = context[AstralConfig.serverOverrideDefaultsKey] as? String
        guard let endpoint = AstralConfig.usableEndpoint(raw) else { return }
        guard endpoint != defaults.string(forKey: AstralConfig.serverOverrideDefaultsKey) else { return }
        defaults.set(endpoint, forKey: AstralConfig.serverOverrideDefaultsKey)
        NotificationCenter.default.post(name: Self.didChangeNotification, object: nil)
    }
}
