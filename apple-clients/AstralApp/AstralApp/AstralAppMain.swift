// Feature 051 — iOS (twin of Android, US1) + macOS (twin of Windows, US2)
// in one multiplatform SwiftUI target on the shared AstralCore package.
import SwiftUI
import AstralCore

@main
struct AstralApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .environment(model.themeStore)
                .tint(model.themeStore.palette.primary)
                .preferredColorScheme(.dark)
                .task { await model.bootstrap() }
                #if os(macOS)
                .frame(minWidth: 900, minHeight: 600)
                #endif
        }
        #if os(macOS)
        .windowStyle(.titleBar)
        #endif
    }
}
