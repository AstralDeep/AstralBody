// Feature 051 — watchOS client (US3 QR sign-in, US4 voice + TTS, US5
// degraded rendering). Independent watch app; the server pre-degrades every
// payload via the `watch` ROTE profile and attaches the spoken rendition.
import SwiftUI
import AstralCore

@main
struct AstralWatchApp: App {
    @StateObject private var model = WatchModel()

    var body: some Scene {
        WindowGroup {
            Group {
                switch model.phase {
                case .signedOut, .waitingApproval, .loginFailed, .unavailable:
                    DeviceLoginView()
                case .signedIn:
                    NavigationStack {
                        WatchHomeView()
                    }
                }
            }
            .environmentObject(model)
            .task { await model.bootstrap() }
        }
    }
}
