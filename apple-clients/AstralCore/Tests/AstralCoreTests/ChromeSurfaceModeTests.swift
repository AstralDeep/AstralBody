// Feature 054 — the additive chrome_surface `mode` field (first-run gate).
// `mode` is a reserved field on an EXISTING frame type: the manifest drift
// guard asserts frame TYPE names only, so this field rides with no
// ui_protocol.json change and no disposition churn.
import XCTest

@testable import AstralCore

final class ChromeSurfaceModeTests: XCTestCase {

    private func frame(_ json: String) -> InboundFrame {
        InboundFrame.parse(json)!
    }

    func testMandatoryModeParsesWhenPresent() {
        let f = frame(
            #"{"type":"chrome_surface","surface_key":"llm","title":"Set up your AI provider","components":[],"mode":"mandatory"}"#
        )
        XCTAssertEqual(f.surfaceMode, "mandatory")
    }

    func testModeDefaultsToReplaceWhenAbsent() {
        // Pre-054 servers never send `mode` — the accessor must default.
        let f = frame(#"{"type":"chrome_surface","surface_key":"theme","title":"Appearance","components":[]}"#)
        XCTAssertEqual(f.surfaceMode, "replace")
    }

    func testExplicitReplaceParses() {
        // The blank close instruction carries mode:"replace" explicitly.
        let f = frame(#"{"type":"chrome_surface","surface_key":"","components":[],"mode":"replace"}"#)
        XCTAssertEqual(f.surfaceMode, "replace")
    }

    func testNonStringModeFallsBackToReplace() {
        // Lenient decode (FR-003): a malformed field can never crash a client.
        let f = frame(#"{"type":"chrome_surface","surface_key":"llm","components":[],"mode":7}"#)
        XCTAssertEqual(f.surfaceMode, "replace")
    }
}
