// Feature 053 — the endpoint resolution ladder (override > Info.plist > fallback).
//
// The ladder is the only place the client decides *which backend it talks to*, and
// it is exercised in three states the app really hits: a healthy build, a build
// whose xcconfig was never wired, and a watch with no companion to push it an
// override. It is isolated from `Bundle` so these run headlessly.
import XCTest
@testable import AstralCore

final class ConfigurationResolutionTests: XCTestCase {
    private let plistValue = "https://sandbox.ai.uky.edu"

    // MARK: - the ladder

    func testOverrideWinsOverInfoPlist() {
        XCTAssertEqual(
            AstralConfig.resolve(override: "https://staging.example.edu",
                                 infoValue: plistValue,
                                 fallback: AstralConfig.fallbackServerBaseURL),
            "https://staging.example.edu")
    }

    func testInfoPlistUsedWhenNoOverride() {
        XCTAssertEqual(
            AstralConfig.resolve(override: nil,
                                 infoValue: plistValue,
                                 fallback: AstralConfig.fallbackServerBaseURL),
            plistValue)
    }

    /// A watch with no paired companion gets no override; AstralCore's own unit
    /// tests get no bundle. Both land here, and both must stay usable.
    func testFallbackWhenNeitherOverrideNorInfoPlistResolves() {
        XCTAssertEqual(
            AstralConfig.resolve(override: nil, infoValue: nil,
                                 fallback: AstralConfig.fallbackServerBaseURL),
            AstralConfig.fallbackServerBaseURL)
    }

    // MARK: - a bad override must never strand the app

    func testBlankAndEmptyOverridesAreIgnored() {
        for bad in ["", "   ", "\n\t"] {
            XCTAssertEqual(
                AstralConfig.resolve(override: bad, infoValue: plistValue,
                                     fallback: AstralConfig.fallbackServerBaseURL),
                plistValue, "override \(bad.debugDescription) should be ignored")
        }
    }

    func testNonHTTPOverridesAreIgnored() {
        // A scheme we cannot talk to, a relative path, and a host-less URL.
        for bad in ["ftp://example.edu", "sandbox.ai.uky.edu", "/relative/path", "https://"] {
            XCTAssertEqual(
                AstralConfig.resolve(override: bad, infoValue: plistValue,
                                     fallback: AstralConfig.fallbackServerBaseURL),
                plistValue, "override \(bad.debugDescription) should be ignored")
        }
    }

    /// The failure this guard exists for: a project that forgot to wire the
    /// xcconfig leaves the literal build setting in Info.plist. Treating that as
    /// an endpoint would point the app at a nonsense host instead of production.
    func testUnsubstitutedBuildSettingIsRejected() {
        XCTAssertEqual(
            AstralConfig.resolve(override: nil,
                                 infoValue: "$(ASTRAL_SERVER_BASE_URL)",
                                 fallback: AstralConfig.fallbackServerBaseURL),
            AstralConfig.fallbackServerBaseURL)
    }

    func testOverrideIsTrimmed() {
        XCTAssertEqual(
            AstralConfig.resolve(override: "  https://staging.example.edu  ",
                                 infoValue: plistValue,
                                 fallback: AstralConfig.fallbackServerBaseURL),
            "https://staging.example.edu")
    }

    func testLocalhostDebugEndpointIsUsable() {
        XCTAssertEqual(AstralConfig.usableEndpoint("http://localhost:8001"),
                       "http://localhost:8001")
    }

    // MARK: - realm resolves through the same ladder

    func testAuthorityFallsBackToTheProductionRealm() {
        XCTAssertEqual(
            AstralConfig.resolve(override: nil, infoValue: nil,
                                 fallback: AstralConfig.fallbackKeycloakAuthority),
            "https://iam.ai.uky.edu/realms/Astral")
    }

    // MARK: - identities are backend contracts

    func testOAuthClientIdsMatchTheBackendContract() {
        XCTAssertEqual(AstralConfig.iosClientId, "astral-mobile")     // shared with Android
        XCTAssertEqual(AstralConfig.macosClientId, "astral-desktop")  // shared with Windows
        XCTAssertEqual(AstralConfig.watchClientId, "astral-watch")
        XCTAssertEqual(AstralConfig.redirectURI, "com.personalailabs.astraldeep:/oauth2redirect")
    }
}
