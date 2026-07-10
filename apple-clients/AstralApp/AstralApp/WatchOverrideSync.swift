// Feature 053 — pushes the backend endpoint override to the paired watch (FR-011).
//
// iOS only. `AstralApp` is one multiplatform target, so this whole file compiles
// to nothing on macOS, where WatchConnectivity does not exist.
//
// The push is best-effort by design: the watch runs independently and treats any
// override as an optimization (see AstralWatch/WatchOverrideSync.swift). If the
// watch is unpaired, the watch app isn't installed, or the session never
// activates, we simply do nothing and the watch keeps its build-time endpoint.
#if os(iOS)
import Foundation
import WatchConnectivity
import AstralCore

final class WatchOverrideSync: NSObject, WCSessionDelegate {
    static let shared = WatchOverrideSync()

    /// The last endpoint we tried to push, so we can replay it once the session
    /// activates (the user may change the server before WCSession is ready).
    private var pending: String?

    /// Safe to call unconditionally; a no-op on a device with no Watch support.
    func activate() {
        guard WCSession.isSupported() else { return }
        let session = WCSession.default
        session.delegate = self
        session.activate()
    }

    /// Push an endpoint override to the watch. Ignores anything unusable so a
    /// half-typed URL in the sign-in field never reaches the watch.
    func push(_ rawEndpoint: String?) {
        guard let endpoint = AstralConfig.usableEndpoint(rawEndpoint) else { return }
        pending = endpoint
        flush()
    }

    private func flush() {
        guard WCSession.isSupported(), let endpoint = pending else { return }
        let session = WCSession.default
        // Only meaningful once activated, and only when there is a watch app to receive it.
        guard session.activationState == .activated,
              session.isPaired,
              session.isWatchAppInstalled
        else { return }
        // `updateApplicationContext` replaces any queued context, which is exactly
        // the semantics we want: the watch only ever needs the *latest* endpoint.
        try? session.updateApplicationContext([AstralConfig.serverOverrideDefaultsKey: endpoint])
        pending = nil
    }

    // MARK: - WCSessionDelegate

    func session(_ session: WCSession,
                 activationDidCompleteWith activationState: WCSessionActivationState,
                 error: Error?) {
        guard error == nil, activationState == .activated else { return }
        flush()
    }

    // Required on iOS. When the user switches watches the session deactivates;
    // reactivate so a later push still reaches the newly-paired watch.
    func sessionDidBecomeInactive(_ session: WCSession) {}

    func sessionDidDeactivate(_ session: WCSession) {
        session.activate()
    }
}
#endif
