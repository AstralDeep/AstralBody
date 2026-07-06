// Feature 051 — desktop/mobile component renderer (FR-004/FR-025). Native
// views for the core set; the readable-text fallback (with the type badge)
// for everything else, per ClientDispositions.ios/.macos. A type flips to a
// richer renderer as its parity row is implemented and verified.
import SwiftUI
import AstralCore

struct ComponentView: View {
    let component: AstralComponent

    var body: some View {
        switch component.type {
        case "text":
            Text(component.textContent ?? component.fallbackText)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        case "alert":
            Label(component.message ?? component.fallbackText, systemImage: alertIcon)
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(alertColor.opacity(0.14), in: RoundedRectangle(cornerRadius: 8))
        case "card", "container", "collapsible":
            VStack(alignment: .leading, spacing: 6) {
                titleLine
                childViews
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.gray.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
        case "grid":
            VStack(alignment: .leading, spacing: 6) {
                titleLine
                childViews
            }
        case "metric":
            VStack(alignment: .leading, spacing: 2) {
                Text(component.title ?? component.label ?? "")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(component.value ?? "—")
                    .font(.title.bold())
            }
            .padding(10)
            .background(.gray.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
        case "badge":
            Text(component.label ?? component.fallbackText)
                .font(.caption.bold())
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(.tint.opacity(0.2), in: Capsule())
        case "hero":
            VStack(alignment: .leading, spacing: 4) {
                Text(component.raw["heading"]?.stringValue ?? component.title ?? "")
                    .font(.title2.bold())
                if let sub = component.raw["subheading"]?.stringValue {
                    Text(sub).foregroundStyle(.secondary)
                }
            }
        case "list":
            VStack(alignment: .leading, spacing: 3) {
                titleLine
                ForEach(Array(component.listItems.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .top, spacing: 6) {
                        Text("•")
                        Text(item)
                    }
                }
            }
        case "keyvalue":
            VStack(alignment: .leading, spacing: 3) {
                titleLine
                ForEach(Array(component.keyValuePairs.enumerated()), id: \.offset) { _, pair in
                    HStack(alignment: .top) {
                        Text(pair.0).foregroundStyle(.secondary)
                        Spacer(minLength: 12)
                        Text(pair.1)
                    }
                    .font(.callout)
                }
            }
        case "table":
            tableView
        case "code":
            ScrollView(.horizontal) {
                Text(component.textContent ?? "")
                    .font(.body.monospaced())
                    .textSelection(.enabled)
                    .padding(10)
            }
            .background(.black.opacity(0.85), in: RoundedRectangle(cornerRadius: 8))
            .foregroundStyle(.green)
        case "image":
            if let url = component.url.flatMap(URL.init(string:)) {
                AsyncImage(url: url) { image in
                    image.resizable().scaledToFit()
                } placeholder: {
                    ProgressView()
                }
                .frame(maxHeight: 360)
            }
        case "progress":
            VStack(alignment: .leading, spacing: 3) {
                titleLine
                ProgressView(value: progressFraction)
            }
        case "divider":
            Divider()
        default:
            VStack(alignment: .leading, spacing: 2) {
                Text(component.fallbackText)
                    .fixedSize(horizontal: false, vertical: true)
                Text(component.type)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.gray.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
        }
    }

    // MARK: pieces

    @ViewBuilder
    private var titleLine: some View {
        if let title = component.title, !title.isEmpty {
            Text(title).font(.headline)
        }
    }

    @ViewBuilder
    private var childViews: some View {
        ForEach(Array(component.children.enumerated()), id: \.offset) { _, child in
            ComponentView(component: child)
        }
    }

    private var tableView: some View {
        VStack(alignment: .leading, spacing: 4) {
            titleLine
            SwiftUI.Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 4) {
                if !component.tableHeaders.isEmpty {
                    GridRow {
                        ForEach(Array(component.tableHeaders.enumerated()), id: \.offset) { _, header in
                            Text(header).font(.caption.bold()).foregroundStyle(.secondary)
                        }
                    }
                    Divider()
                }
                ForEach(Array(component.tableRows.enumerated()), id: \.offset) { _, row in
                    GridRow {
                        ForEach(Array(row.enumerated()), id: \.offset) { _, cell in
                            Text(cell).font(.callout)
                        }
                    }
                }
            }
        }
        .padding(10)
        .background(.gray.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
    }

    private var alertIcon: String {
        switch component.variant {
        case "error": return "xmark.octagon.fill"
        case "warning": return "exclamationmark.triangle.fill"
        case "success": return "checkmark.circle.fill"
        default: return "info.circle.fill"
        }
    }

    private var alertColor: Color {
        switch component.variant {
        case "error": return .red
        case "warning": return .orange
        case "success": return .green
        default: return .blue
        }
    }

    private var progressFraction: Double {
        let value = component.raw["value"]?.numberValue ?? 0
        let max = component.raw["max"]?.numberValue ?? 100
        return max > 0 ? min(value / max, 1) : 0
    }
}
