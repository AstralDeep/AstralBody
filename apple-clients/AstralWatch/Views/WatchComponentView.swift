// Feature 051 US5 — compact watch renderers for the profile's native set,
// readable-text fallback for everything else, and the "continue on another
// device" affordance for over-budget interactivity (FR-032/FR-033).
// The SERVER already degraded this payload via the watch ROTE profile; this
// view is the last line of defense — it must never render blank.
import SwiftUI
import AstralCore

struct WatchComponentView: View {
    let component: AstralComponent

    var body: some View {
        switch component.type {
        case "text":
            Text(component.textContent ?? component.fallbackText)
                .font(.footnote)
                .fixedSize(horizontal: false, vertical: true)
        case "alert":
            Label(component.message ?? component.fallbackText,
                  systemImage: iconForVariant)
                .font(.footnote)
                .foregroundStyle(component.variant == "error" ? .red : .primary)
        case "metric":
            VStack(alignment: .leading, spacing: 0) {
                Text(component.title ?? component.label ?? "")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(component.value ?? "—")
                    .font(.title3.bold())
                    .minimumScaleFactor(0.6)
            }
        case "badge":
            Text(component.label ?? component.fallbackText)
                .font(.caption2.bold())
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(.tint.opacity(0.3), in: Capsule())
        case "list":
            VStack(alignment: .leading, spacing: 2) {
                titleLine
                ForEach(Array(component.listItems.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .top, spacing: 4) {
                        Text("•")
                        Text(item)
                    }
                    .font(.footnote)
                }
            }
        case "keyvalue":
            VStack(alignment: .leading, spacing: 2) {
                titleLine
                ForEach(Array(component.keyValuePairs.enumerated()), id: \.offset) { _, pair in
                    HStack(alignment: .top) {
                        Text(pair.0).font(.caption2).foregroundStyle(.secondary)
                        Spacer(minLength: 4)
                        Text(pair.1).font(.footnote)
                    }
                }
            }
        case "progress":
            VStack(alignment: .leading, spacing: 2) {
                titleLine
                ProgressView(value: progressFraction)
            }
        case "card", "container", "grid", "collapsible":
            VStack(alignment: .leading, spacing: 4) {
                titleLine
                ForEach(Array(component.children.enumerated()), id: \.offset) { _, child in
                    WatchComponentView(component: child)
                }
            }
            .padding(6)
            .background(.gray.opacity(0.15), in: RoundedRectangle(cornerRadius: 8))
        case "divider":
            Divider()
        case "button", "input", "file_upload", "color_picker", "param_picker":
            // Interactivity beyond the wrist: read-only summary + explicit
            // continue-elsewhere affordance (FR-033) instead of broken controls.
            VStack(alignment: .leading, spacing: 2) {
                Text(component.label ?? component.title ?? component.fallbackText)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                Label("Continue on your phone or desktop",
                      systemImage: "iphone.and.arrow.forward")
                    .font(.caption2)
                    .foregroundStyle(.tint)
            }
        default:
            // Deterministic fallback chain terminates in readable text —
            // zero blank canvases (FR-032).
            VStack(alignment: .leading, spacing: 2) {
                Text(component.fallbackText)
                    .font(.footnote)
                    .fixedSize(horizontal: false, vertical: true)
                Text(component.type)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
    }

    @ViewBuilder
    private var titleLine: some View {
        if let title = component.title, !title.isEmpty {
            Text(title).font(.caption.bold())
        }
    }

    private var iconForVariant: String {
        switch component.variant {
        case "error": return "xmark.octagon"
        case "warning": return "exclamationmark.triangle"
        case "success": return "checkmark.circle"
        default: return "info.circle"
        }
    }

    private var progressFraction: Double {
        let value = component.raw["value"]?.numberValue ?? 0
        let max = component.raw["max"]?.numberValue ?? 100
        return max > 0 ? min(value / max, 1) : 0
    }
}
