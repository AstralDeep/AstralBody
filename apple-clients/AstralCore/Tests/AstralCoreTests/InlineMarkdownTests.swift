// Feature 053 — the shared inline-markdown parse every surface renders through.
// The contract under test: inline spans are styled (no literal asterisks reach
// a screen), block syntax and newlines survive verbatim, and no input can
// yield a blank or thrown result.
import XCTest

@testable import AstralCore

final class InlineMarkdownTests: XCTestCase {

    private func plain(_ s: String) -> String {
        String(InlineMarkdown.attributed(s).characters)
    }

    func testBoldMarkersAreConsumed() {
        XCTAssertEqual(plain("The **answer** is 42"), "The answer is 42")
    }

    func testItalicAndCodeMarkersAreConsumed() {
        XCTAssertEqual(plain("*emphasis* and `code`"), "emphasis and code")
    }

    func testLinkShowsItsLabel() {
        XCTAssertEqual(plain("see [the docs](https://sandbox.ai.uky.edu)"), "see the docs")
    }

    func testNewlinesArePreserved() {
        // inlineOnlyPreservingWhitespace: multi-line narrative keeps its shape.
        XCTAssertEqual(plain("line one\nline two"), "line one\nline two")
    }

    func testBlockSyntaxStaysLiteral() {
        // Inline-only by design (parity with the phone renderer): a heading
        // marker is not a style, it is content.
        XCTAssertEqual(plain("# Heading"), "# Heading")
    }

    func testPlainTextPassesThroughUnchanged() {
        XCTAssertEqual(plain("2 * 3 * 4 = 24"), "2 * 3 * 4 = 24")
    }

    func testEmptyStringDoesNotThrowOrBlank() {
        XCTAssertEqual(plain(""), "")
    }
}
