import AstralCore
import Foundation
// Feature 051 — iOS (twin of Android, US1) + macOS (twin of Windows, US2)
// in one multiplatform SwiftUI target on the shared AstralCore package.
import SwiftUI

@main
struct AstralApp: App {
    @State private var model = AppModel()
    private let unitTestHost =
        ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .environment(model.themeStore)
                .tint(model.themeStore.palette.primary)
                .preferredColorScheme(.dark)
                .task {
                    #if DEBUG
                        if let scenario = FirstLoginUITestFixture.requestedScenario() {
                            FirstLoginUITestFixture.install(scenario, on: model)
                            return
                        }
                    #endif
                    // A macOS unit-test bundle is injected into the app host.
                    // Starting the real login bootstrap there can block on a
                    // developer login-keychain prompt before XCTest begins.
                    // UI-test apps are separate processes and do not carry
                    // XCTestConfigurationFilePath, so their real launch path
                    // remains unchanged.
                    if !unitTestHost { await model.bootstrap() }
                }
                #if os(macOS)
                    .frame(minWidth: 900, minHeight: 600)
                #endif
        }
        #if os(macOS)
            .windowStyle(.titleBar)
        #endif
    }
}
