// Feature 051 — watchOS client (US3 QR sign-in, US4 voice + TTS, US5
// degraded rendering). Independent watch app; the server pre-degrades every
// payload via the `watch` ROTE profile and attaches the spoken rendition.
import SwiftUI
import AstralCore

@main
struct AstralWatchApp: App {
    @State private var model = WatchModel()

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
            .environment(model)
            .tint(Color(red: 99 / 255, green: 102 / 255, blue: 241 / 255)) // AstralDeep indigo
            .task { await model.bootstrap() }
        }
    }
}
