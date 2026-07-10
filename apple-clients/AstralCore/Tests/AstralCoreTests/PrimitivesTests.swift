// AstralPrims mirror-fidelity tests. The known-answer fixtures in
// Fixtures/astralprims-fixtures.json were generated from the LIVE Python
// package (astralprims 0.3.0) inside the astraldeep container — every Swift
// construction below mirrors the Python construction that produced its
// fixture, and the serialized dicts must be EQUAL. Regenerate the fixtures
// from the container (see the file header in the generator notes in
// specs/051) whenever the pip package version bumps.
import XCTest
@testable import AstralCore

final class PrimitivesTests: XCTestCase {

    // MARK: fixture plumbing

    static var fixtures: [String: JSONValue] = [:]
    static var fixtureVersion = ""

    override class func setUp() {
        super.setUp()
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("Fixtures/astralprims-fixtures.json")
        guard let data = try? Data(contentsOf: url),
              let root = try? JSONValue.parse(data),
              case .object(let rootDict) = root,
              case .object(let fixtureDict)? = rootDict["fixtures"] else {
            return
        }
        fixtures = fixtureDict
        fixtureVersion = rootDict["astralprims_version"]?.stringValue ?? ""
    }

    private func assertMirrors(_ primitive: AstralPrims.Primitive,
                               fixture name: String,
                               file: StaticString = #filePath, line: UInt = #line) {
        guard let expected = Self.fixtures[name] else {
            XCTFail("missing fixture \(name) — regenerate astralprims-fixtures.json",
                    file: file, line: line)
            return
        }
        XCTAssertEqual(primitive.toDict(), expected,
                       "\(name): Swift toDict() != astralprims to_dict()",
                       file: file, line: line)
    }

    func testFixturesLoaded() {
        XCTAssertEqual(Self.fixtureVersion, "0.3.0",
                       "fixtures generated from a different astralprims version — re-check the mirror")
        XCTAssertEqual(Self.fixtures.count, 33)
    }

    // MARK: layout

    func testContainerNested() {
        assertMirrors(
            AstralPrims.Container(direction: "row").add(
                AstralPrims.Card(title: "Welcome",
                                 content: [AstralPrims.Button(label: "Get started", action: "go")]),
                AstralPrims.Divider()),
            fixture: "container_nested")
    }

    func testCardVariantAndClassAlias() {
        assertMirrors(
            AstralPrims.Card(title: "KPIs",
                             content: [AstralPrims.MetricCard(
                                title: "Revenue", value: "$1.2M", subtitle: "+12%",
                                icon: "📈", variant: "success", progress: 0.72)],
                             variant: "elevated")
                .className("wide"),
            fixture: "card_variant")
    }

    func testGrid() {
        assertMirrors(
            AstralPrims.Grid(columns: 3, gap: 12)
                .add(AstralPrims.Text(content: "a"), AstralPrims.Text(content: "b")),
            fixture: "grid")
    }

    func testTabsWithTabItems() {
        assertMirrors(
            AstralPrims.Tabs(tabs: [
                AstralPrims.TabItem(label: "One",
                                    content: [AstralPrims.Text(content: "first")],
                                    value: "one"),
                AstralPrims.TabItem(label: "Two",
                                    content: [AstralPrims.Alert(message: "careful",
                                                                variant: "warning",
                                                                title: "Heads up")]),
            ], variant: "pills"),
            fixture: "tabs")
    }

    func testCollapsibleWithCode() {
        assertMirrors(
            AstralPrims.Collapsible(title: "Details",
                                    content: [AstralPrims.CodeBlock(code: "print('hi')",
                                                                    language: "python",
                                                                    showLineNumbers: true)],
                                    defaultOpen: true),
            fixture: "collapsible")
    }

    func testDivider() {
        assertMirrors(AstralPrims.Divider(variant: "dashed"), fixture: "divider")
    }

    // MARK: content & controls

    func testButtonDoctest() {
        // The package README doctest, byte-for-byte.
        assertMirrors(
            AstralPrims.Button(label: "Click me", action: "open")
                .css(["background-color": "white", "color": "#000000"]),
            fixture: "button_doctest")
    }

    func testTextWithIdAndTooltip() {
        assertMirrors(
            AstralPrims.Text(content: "Hello **md**", variant: "h2")
                .id("t1").tooltip("tip"),
            fixture: "text_variant")
    }

    func testInput() {
        assertMirrors(AstralPrims.Input(placeholder: "Type...", name: "q", value: "seed"),
                      fixture: "input")
    }

    func testParamPicker() {
        assertMirrors(
            AstralPrims.ParamPicker(
                title: "Train", description: "Pick params",
                fields: [.object(["name": .string("epochs"), "label": .string("Epochs"),
                                  "kind": .string("number"), "default": .number(3),
                                  "step": .number(1)])],
                submitLabel: "Go", submitMessageTemplate: "Train with {epochs}"),
            fixture: "param_picker")
    }

    func testImage() {
        assertMirrors(AstralPrims.Image(url: "https://x/y.png", alt: "alt",
                                        width: "320", height: "200"),
                      fixture: "image")
    }

    func testAlert() {
        assertMirrors(AstralPrims.Alert(message: "ok", variant: "success"), fixture: "alert")
    }

    func testProgressBar() {
        assertMirrors(AstralPrims.ProgressBar(value: 0.4, label: "Loading",
                                              variant: "info", showPercentage: false),
                      fixture: "progress")
    }

    func testMetricMinimalEmitsDefaults() {
        // Non-optional defaults are EMITTED (title/value/variant); optionals dropped.
        assertMirrors(AstralPrims.MetricCard(), fixture: "metric_minimal")
    }

    func testListMixedItems() {
        assertMirrors(
            AstralPrims.List(items: [.string("a"),
                                     .object(["label": .string("b"), "hint": .string("h")])],
                             ordered: true, variant: "compact"),
            fixture: "list_mixed")
    }

    func testTablePaginated() {
        assertMirrors(
            AstralPrims.Table(
                headers: ["City", "Pop"],
                rows: [[.string("NYC"), .number(8.3)], [.string("LA"), .number(3.9)]],
                totalRows: 12, pageSize: 2, pageOffset: 0, pageSizes: [2, 5],
                sourceTool: "cities", sourceAgent: "demo-1",
                sourceParams: ["country": .string("US")]),
            fixture: "table_paginated")
    }

    // MARK: charts

    func testBarChartWithDataset() {
        assertMirrors(
            AstralPrims.BarChart(title: "Bars", labels: ["a", "b"],
                                 datasets: [AstralPrims.ChartDataset(label: "s1", data: [1, 2],
                                                                     color: "#fff")]),
            fixture: "bar_chart")
    }

    func testLineChartPlainDatasets() {
        assertMirrors(
            AstralPrims.LineChart(title: "Lines", labels: ["t1"],
                                  datasets: [.object(["label": .string("s"),
                                                      "data": .array([.number(3.5)])])]),
            fixture: "line_chart")
    }

    func testPieChart() {
        assertMirrors(
            AstralPrims.PieChart(title: "Pie", labels: ["x", "y"],
                                 data: [60, 40], colors: ["#111", "#222"]),
            fixture: "pie_chart")
    }

    func testPlotlyChart() {
        assertMirrors(
            AstralPrims.PlotlyChart(
                title: "P",
                data: [.object(["y": .array([.number(1), .number(2), .number(3)]),
                                "type": .string("scatter")])],
                layout: ["height": .number(300)],
                config: ["displayModeBar": .bool(false)]),
            fixture: "plotly_chart")
    }

    // MARK: media & I/O

    func testAudioCamelCaseKeys() {
        assertMirrors(
            AstralPrims.Audio(src: "data:audio/wav;base64,AAA", contentType: "audio/wav",
                              autoplay: true, loop: false, label: "Clip",
                              showControls: true, description: "desc"),
            fixture: "audio")
    }

    func testFileUpload() {
        assertMirrors(AstralPrims.FileUpload(label: "Up", accept: ".csv", action: "upload_csv"),
                      fixture: "file_upload")
    }

    func testFileDownload() {
        assertMirrors(AstralPrims.FileDownload(label: "Get", url: "/f.txt", filename: "f.txt"),
                      fixture: "file_download")
    }

    // MARK: dashboard & status

    func testBadge() {
        assertMirrors(AstralPrims.Badge(label: "LIVE", variant: "accent", icon: "!"),
                      fixture: "badge")
    }

    func testHero() {
        assertMirrors(
            AstralPrims.Hero(title: "Q3", subtitle: "sub", eyebrow: "REPORT",
                             icon: "R", variant: "gradient", badges: ["A", "B"]),
            fixture: "hero")
    }

    func testKeyValue() {
        assertMirrors(
            AstralPrims.KeyValue(title: "Facts",
                                 items: [.object(["label": .string("Owner"),
                                                  "value": .string("P&B"),
                                                  "hint": .string("since 2021")])],
                                 columns: 1),
            fixture: "keyvalue")
    }

    func testTimeline() {
        assertMirrors(
            AstralPrims.Timeline(title: "Day",
                                 items: [.object(["time": .string("9:00"),
                                                  "title": .string("Groom"),
                                                  "variant": .string("success")])],
                                 variant: "default"),
            fixture: "timeline")
    }

    func testRating() {
        assertMirrors(
            AstralPrims.Rating(value: 4.5, maxValue: 5, label: "CSAT",
                               subtitle: "n=100", showValue: true),
            fixture: "rating")
    }

    func testChatHistoryDefaultTitle() {
        assertMirrors(
            AstralPrims.ChatHistory(items: [.object(["chat_id": .string("c1"),
                                                     "title": .string("Weather")])]),
            fixture: "chat_history")
    }

    // MARK: theming

    func testColorPicker() {
        assertMirrors(AstralPrims.ColorPicker(label: "Primary", colorKey: "primary",
                                              value: "#6366F1"),
                      fixture: "color_picker")
    }

    func testThemeApply() {
        assertMirrors(AstralPrims.ThemeApply(preset: "ocean", message: "Applied"),
                      fixture: "theme_apply")
    }

    // MARK: base semantics

    func testAttributesMergeLastAndOverride() {
        // attributes override declared fields — the package's escape hatch.
        assertMirrors(
            AstralPrims.Text(content: "x")
                .attributes(["variant": .string("h1"), "data-test": .string("1")]),
            fixture: "attributes_override")
    }

    func testEmptyCSSIsOmitted() {
        let dict = AstralPrims.Text(content: "x").css([:]).toDict()
        XCTAssertNil(dict["css"], "an empty css block must be omitted")
    }

    func testUIResponseEnvelope() {
        guard let expected = Self.fixtures["envelope"] else {
            return XCTFail("missing envelope fixture")
        }
        XCTAssertEqual(
            AstralPrims.createUIResponse([AstralPrims.Text(content: "hi"),
                                          AstralPrims.Badge(label: "ok")]),
            expected)
    }

    func testAuthoredDictsParseAsAstralComponents() {
        // The authoring layer's output must be readable by the consuming model
        // (AstralComponent) — the same dict round-trips both roles.
        let dict = AstralPrims.Card(title: "Welcome",
                                    content: [AstralPrims.Button(label: "Go", action: "go")])
            .toDict()
        let component = AstralComponent(json: dict)
        XCTAssertEqual(component?.type, "card")
        XCTAssertEqual(component?.title, "Welcome")
        XCTAssertEqual(component?.children.first?.type, "button")
    }

    // MARK: vocabulary tie-in (manifest drift)

    func testEveryFixtureTypeIsAuthored() throws {
        // Collect component types RECURSIVELY (nested children/content/tabs
        // count — e.g. "code" lives inside the collapsible fixture).
        var seen: Set<String> = []
        func walk(_ value: JSONValue) {
            switch value {
            case .object(let dict):
                if let type = dict["type"]?.stringValue { seen.insert(type) }
                dict.values.forEach(walk)
            case .array(let items):
                items.forEach(walk)
            default:
                break
            }
        }
        for (name, fixture) in Self.fixtures where name != "envelope" {
            walk(fixture)
        }
        // "scatter" is a plotly trace kind, not a component type.
        seen.remove("scatter")
        XCTAssertEqual(seen, AstralPrims.allTypes,
                       "fixture coverage != authoring registry — add the missing case(s)")
    }

    func testAuthoredTypesMatchManifest() throws {
        // Every authored type exists in the committed manifest, and the delta
        // is EXACTLY the renderer-origin types the package does not define.
        let data = try Data(contentsOf: try ManifestDriftTests.manifestURL())
        let manifest = try JSONDecoder().decode(ManifestDriftTests.Manifest.self, from: data)
        let manifestTypes = Set(manifest.component_types)
        XCTAssertTrue(AstralPrims.allTypes.isSubset(of: manifestTypes),
                      "authored types missing from ui_protocol.json: \(AstralPrims.allTypes.subtracting(manifestTypes))")
        XCTAssertEqual(manifestTypes.subtracting(AstralPrims.allTypes),
                       ["download_card", "generative", "skeleton"],
                       "renderer-origin delta changed — astralprims gained/lost a type; update the mirror")
    }
}
