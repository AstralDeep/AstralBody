// swift-tools-version: 5.9
// Feature 051 — shared first-party core for the three Apple SDUI clients.
// ZERO third-party dependencies (Constitution V): Foundation, CryptoKit,
// URLSession only. All protocol/transport/auth logic lives here so
// `swift test` covers it headlessly (no Xcode project required).
import PackageDescription

let package = Package(
    name: "AstralCore",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
        .watchOS(.v10),
    ],
    products: [
        .library(name: "AstralCore", targets: ["AstralCore"]),
    ],
    targets: [
        .target(name: "AstralCore", path: "Sources/AstralCore"),
        .testTarget(
            name: "AstralCoreTests",
            dependencies: ["AstralCore"],
            path: "Tests/AstralCoreTests"
        ),
    ]
)
