// Feature 051 (FR-038) — manifest drift guard, the Swift twin of
// windows-client/tests/test_protocol_manifest.py and the Android
// VocabularyParityTest: if backend/shared/ui_protocol.json changes vocabulary
// and the Apple dispositions don't account for it, this suite fails CI.
import XCTest
@testable import AstralCore

final class ManifestDriftTests: XCTestCase {

    struct Manifest: Decodable {
        struct Named: Decodable { let name: String }
        // ui_protocol.json shape: push_types are {name, category} objects;
        // component_types and accept_actions are plain strings.
        let push_types: [Named]
        let component_types: [String]
        let accept_actions: [String]
    }

    /// Walk up from this file until the committed manifest is found.
    static func manifestURL() throws -> URL {
        var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        for _ in 0..<8 {
            let candidate = dir.appendingPathComponent("backend/shared/ui_protocol.json")
            if FileManager.default.fileExists(atPath: candidate.path) {
                return candidate
            }
            dir.deleteLastPathComponent()
        }
        throw XCTSkip("ui_protocol.json not found (package checked out standalone)")
    }

    func loadManifest() throws -> Manifest {
        let data = try Data(contentsOf: try Self.manifestURL())
        return try JSONDecoder().decode(Manifest.self, from: data)
    }

    func testManifestVocabularyMatchesEmbeddedLists() throws {
        let manifest = try loadManifest()
        XCTAssertEqual(Set(manifest.push_types.map(\.name)),
                       Set(ClientDispositions.allPushTypes),
                       "push_types drift — update Dispositions.swift + parity matrix")
        XCTAssertEqual(Set(manifest.component_types),
                       Set(ClientDispositions.allComponentTypes),
                       "component_types drift — update Dispositions.swift + parity matrix")
        XCTAssertEqual(manifest.push_types.count, 47)
        XCTAssertEqual(manifest.component_types.count, 35)
        // 73 = 67 + the four feature-054 chrome_llm_sys_* admin actions
        //        + the two feature-055 component_refine/component_restore actions.
        XCTAssertEqual(manifest.accept_actions.count, 73)
    }

    func testEveryClientDispositionsEveryFrameAndComponent() throws {
        for client in [ClientDispositions.ios, ClientDispositions.macos, ClientDispositions.watch] {
            for name in ClientDispositions.allPushTypes {
                XCTAssertNotNil(client.frames[name],
                                "\(client.client): missing frame disposition for \(name)")
            }
            for name in ClientDispositions.allComponentTypes {
                XCTAssertNotNil(client.components[name],
                                "\(client.client): missing component disposition for \(name)")
            }
            // No disposition for a name the manifest doesn't have (stale row).
            for name in client.frames.keys {
                XCTAssertTrue(ClientDispositions.allPushTypes.contains(name),
                              "\(client.client): stale frame disposition \(name)")
            }
            for name in client.components.keys {
                XCTAssertTrue(ClientDispositions.allComponentTypes.contains(name),
                              "\(client.client): stale component disposition \(name)")
            }
        }
    }

    func testWatchHandlesNotificationForBackgroundContinuity() {
        // 055 background-task continuity: a completion notification must reach
        // the wrist. There is no watch test target to pin the reduce, so this
        // pins the disposition — a regression to .ignored would silently drop
        // background completions on the watch again.
        XCTAssertEqual(ClientDispositions.watch.frames["notification"], .handled)
    }

    func testWatchNativeSetIsWithinProfileVocabulary() {
        // The watch renders natively exactly what the watch ROTE profile can
        // emit — charts/tables/code are degraded server-side and must NOT be
        // advertised as natively supported.
        let native = Set(ClientDispositions.watch.nativeComponentTypes)
        for forbidden in ["bar_chart", "line_chart", "pie_chart", "plotly_chart",
                          "table", "code", "tabs", "file_upload", "file_download"] {
            XCTAssertFalse(native.contains(forbidden),
                           "watch must not advertise \(forbidden) as native")
        }
        for required in ["text", "alert", "list", "metric", "keyvalue"] {
            XCTAssertTrue(native.contains(required))
        }
    }

    func testSupportedTypesRideOnDeviceDescriptors() {
        XCTAssertEqual(
            Set(DeviceDescriptor.watch(viewportWidth: 200, viewportHeight: 240)
                .supportedTypes),
            Set(ClientDispositions.watch.nativeComponentTypes))
        XCTAssertFalse(DeviceDescriptor.ios(viewportWidth: 390, viewportHeight: 844)
            .supportedTypes.isEmpty)
    }
}
