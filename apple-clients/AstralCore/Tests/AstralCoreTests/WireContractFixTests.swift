// Feature 053 — regression pins for the wire-contract fixes found in the
// pre-release cross-check: keyvalue reads `items[]` (the only key the server
// emits), detailed list items compose readable lines, chat_status machine
// codes map to human text (and terminal codes CLEAR the line), and the block
// markdown segmenter handles the shapes the backend actually produces.
import XCTest

@testable import AstralCore

final class WireContractFixTests: XCTestCase {

    private func component(_ json: String) -> AstralComponent {
        let value = try! JSONValue.parse(json.data(using: .utf8)!)
        return AstralComponent(json: value)!
    }

    // MARK: keyvalue

    func testKeyValueReadsWireItemsShape() {
        let c = component(
            #"{"type":"keyvalue","items":[{"label":"Region","value":"US"},{"label":"Tier","value":"Pro"}]}"#)
        XCTAssertEqual(c.keyValuePairs.map(\.0), ["Region", "Tier"])
        XCTAssertEqual(c.keyValuePairs.map(\.1), ["US", "Pro"])
    }

    func testKeyValueToleratesLegacyPairsAlias() {
        let c = component(#"{"type":"keyvalue","pairs":[{"key":"A","value":"1"}]}"#)
        XCTAssertEqual(c.keyValuePairs.count, 1)
        XCTAssertEqual(c.keyValuePairs[0].0, "A")
    }

    // MARK: detailed list items

    func testDetailedListItemsComposeTitleAndSubtitle() {
        let c = component(
            #"{"type":"list","variant":"detailed","items":[{"title":"Result","url":"https://x","subtitle":"A snippet"}]}"#
        )
        XCTAssertEqual(c.listItems, ["Result — A snippet"])
    }

    func testDetailedListItemFallsBackToDescription() {
        let c = component(#"{"type":"list","items":[{"title":"Only title"},{"description":"Only description"}]}"#)
        XCTAssertEqual(c.listItems, ["Only title", "Only description"])
    }

    func testPlainAndLabeledListItemsUnchanged() {
        let c = component(#"{"type":"list","items":["plain",{"text":"texted"},{"label":"labeled"}]}"#)
        XCTAssertEqual(c.listItems, ["plain", "texted", "labeled"])
    }

    // MARK: chat_status / chat_step statusText

    private func frame(_ json: String) -> InboundFrame {
        InboundFrame.parse(json)!
    }

    func testStatusDoneClearsTheLine() {
        XCTAssertNil(frame(#"{"type":"chat_status","status":"done"}"#).statusText)
        XCTAssertNil(frame(#"{"type":"chat_status","status":"idle","message":"leftover"}"#).statusText)
    }

    func testStatusMachineCodesMapToHumanText() {
        XCTAssertEqual(frame(#"{"type":"chat_status","status":"thinking"}"#).statusText, "Thinking…")
        XCTAssertEqual(frame(#"{"type":"chat_status","status":"executing"}"#).statusText, "Working…")
    }

    func testStatusPrefersHumanMessage() {
        XCTAssertEqual(
            frame(#"{"type":"chat_status","status":"executing","message":"Calling weather"}"#).statusText,
            "Calling weather")
    }

    func testChatStepObjectYieldsItsName() {
        XCTAssertEqual(
            frame(#"{"type":"chat_step","step":{"name":"web_search","status":"running"}}"#).statusText,
            "web_search")
    }

    // MARK: MarkdownBlocks

    func testBlocksSplitHeadingParagraphAndFence() {
        let blocks = MarkdownBlocks.parse("## Findings\n\nBody text here.\n\n```\nlet x = 1\n```")
        XCTAssertEqual(
            blocks,
            [
                .heading(level: 2, text: "Findings"),
                .paragraph("Body text here."),
                .code("let x = 1"),
            ])
    }

    func testBlocksParseBulletsAndOrderedLists() {
        let blocks = MarkdownBlocks.parse("- one\n- two\n\n1. first\n2. second")
        XCTAssertEqual(
            blocks,
            [
                .bullets(items: ["one", "two"], ordered: false, start: 1),
                .bullets(items: ["first", "second"], ordered: true, start: 1),
            ])
    }

    func testOrderedListKeepsAuthoredNumbering() {
        XCTAssertEqual(
            MarkdownBlocks.parse("3. third\n4. fourth"),
            [.bullets(items: ["third", "fourth"], ordered: true, start: 3)])
    }

    func testIndentedContinuationStaysInsideItsListItem() {
        XCTAssertEqual(
            MarkdownBlocks.parse("- item one\n  continues here\n- item two"),
            [
                .bullets(
                    items: ["item one continues here", "item two"],
                    ordered: false, start: 1)
            ])
    }

    func testNestedBulletDoesNotSplitAnOrderedList() {
        let blocks = MarkdownBlocks.parse("1. first\n   - detail\n2. second")
        guard case .bullets(let items, true, 1) = blocks.first, blocks.count == 1 else {
            return XCTFail("expected one ordered list, got \(blocks)")
        }
        XCTAssertEqual(items.count, 2)
        XCTAssertTrue(items[0].contains("detail"))
    }

    func testBlocksParsePipeTableWithHeader() {
        let blocks = MarkdownBlocks.parse("| City | Temp |\n|---|---|\n| Lexington | 88 |")
        XCTAssertEqual(
            blocks,
            [
                .table(rows: [["City", "Temp"], ["Lexington", "88"]], hasHeader: true)
            ])
    }

    func testUnterminatedFenceStillRendersAsCode() {
        XCTAssertEqual(MarkdownBlocks.parse("```\nabandoned"), [.code("abandoned")])
    }

    func testPlainProseIsOneParagraph() {
        XCTAssertEqual(MarkdownBlocks.parse("just a sentence"), [.paragraph("just a sentence")])
    }

    func testPipePrefixedProseIsNotATable() {
        // Not pipe-wrapped → prose, verbatim (never restructure prose).
        XCTAssertEqual(
            MarkdownBlocks.parse("|x - 3| < 5 holds"),
            [.paragraph("|x - 3| < 5 holds")])
    }

    func testLonePipeWrappedLineWithoutSeparatorStaysProse() {
        XCTAssertEqual(MarkdownBlocks.parse("|a|b|"), [.paragraph("|a|b|")])
    }

    func testQuotedFenceRendersAsCode() {
        XCTAssertEqual(
            MarkdownBlocks.parse("> ```\n> pip install foo\n> ```"),
            [.code("pip install foo")])
    }

    func testLiteralQuoteLinesInsideUnquotedFenceSurvive() {
        XCTAssertEqual(
            MarkdownBlocks.parse("```\n> not a quote\n```"),
            [.code("> not a quote")])
    }

    func testPlainTextFlattensStructureForTheWatch() {
        XCTAssertEqual(
            MarkdownBlocks.plainText("## Findings\n- **a**\n- b"),
            "Findings\n• **a**\n• b")
        XCTAssertEqual(
            MarkdownBlocks.plainText("no markdown at all"),
            "no markdown at all")
    }
}
