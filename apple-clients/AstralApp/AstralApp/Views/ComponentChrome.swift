// Feature 055 (US4/US5) — chrome for one TOP-LEVEL canvas component:
// the provenance badge (T036, wire-contract §6: render the server-stamped
// `provenance` field, distinct per value, absent = nothing — web footer
// parity) and the context menu carrying the refine affordance (T040 →
// `component_refine` ui_event via a small text sheet) plus the CSV export
// entry for tables (T045, opened in the system browser). Nested children
// keep rendering bare ComponentViews; chrome never recurses.
import SwiftUI
import AstralCore

struct RefineTarget: Identifiable, Equatable {
    let componentId: String
    let title: String
    var id: String { componentId }
}

struct ComponentChrome: View {
    let component: AstralComponent
    /// False while viewing a timeline snapshot — the badge still renders
    /// (read-only trust mark) but mutating affordances are withheld.
    var interactive: Bool = true
    var onRefine: ((RefineTarget) -> Void)?
    @Environment(ThemeStore.self) var theme
    @Environment(AppModel.self) var model
    private var p: AstralPalette { theme.palette }

    var body: some View {
        VStack(alignment: .trailing, spacing: 2) {
            // A bare long-press/right-click gesture on menu-less components
            // would still fire the preview — attach only when entries exist.
            if hasMenu {
                baseComponent.contextMenu { menuEntries }
            } else {
                baseComponent
            }
            ProvenanceBadge(kind: component.raw["provenance"]?.stringValue)
        }
    }

    private var baseComponent: some View {
        ComponentView(component: component)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Refinable = carries a persistent workspace identity. `wel_` welcome
    /// components are ephemeral by contract (never persisted) — no affordance.
    private var refinableId: String? {
        guard let cid = component.componentId, !cid.isEmpty,
              !cid.hasPrefix("wel_") else { return nil }
        return cid
    }

    // CSV export is a table-only route (422 otherwise) — offer it only where
    // it can succeed.
    private var csvExportURL: URL? {
        guard component.type == "table", let cid = refinableId else { return nil }
        return model.exportComponentURL(cid)
    }

    private var hasMenu: Bool {
        interactive && !model.mutationsLocked &&
            ((refinableId != nil && onRefine != nil) || csvExportURL != nil)
    }

    @ViewBuilder
    private var menuEntries: some View {
        if let cid = refinableId, let onRefine {
            Button {
                onRefine(RefineTarget(componentId: cid, title: component.title ?? ""))
            } label: {
                Label("Refine…", systemImage: "wand.and.stars")
            }
        }
        if let url = csvExportURL {
            Link(destination: url) {
                Label("Export as CSV", systemImage: "square.and.arrow.up")
            }
        }
    }
}

/// Compact trust mark under the component (web `_provenance_footer` parity:
/// same icons/labels, trailing-aligned). Unknown or absent values render
/// nothing — the server stamps exactly grounded|estimated|generated.
struct ProvenanceBadge: View {
    let kind: String?
    @Environment(ThemeStore.self) var theme
    private var p: AstralPalette { theme.palette }

    var body: some View {
        if let (icon, label, color) = style {
            HStack(spacing: 3) {
                Text(icon)
                Text(label)
            }
            .font(.caption2)
            .foregroundStyle(color.opacity(0.75))
            .accessibilityLabel("Provenance: \(label)")
        }
    }

    private var style: (String, String, Color)? {
        switch kind {
        case "grounded": return ("✓", "tool data", p.success)
        case "estimated": return ("≈", "estimated", p.warning)
        case "generated": return ("✦", "AI-generated", p.muted)
        default: return nil
        }
    }
}

/// Small instruction-entry sheet backing the "Refine…" context-menu item.
struct RefineSheet: View {
    let target: RefineTarget
    @Environment(AppModel.self) var model
    @Environment(ThemeStore.self) var theme
    @Environment(\.dismiss) private var dismiss
    @State private var instruction = ""
    private var p: AstralPalette { theme.palette }

    private var trimmed: String {
        instruction.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(target.title.isEmpty ? "Refine this component" : "Refine \(target.title)")
                .font(.headline).foregroundStyle(p.text)
            Text("Describe the change. The component updates in place — earlier versions stay restorable.")
                .font(.caption).foregroundStyle(p.muted)
                .fixedSize(horizontal: false, vertical: true)
            TextField("e.g. sort by total, highest first", text: $instruction, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(2...4)
                .onSubmit(submit)
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }
                    .buttonStyle(AstralButtonStyle(palette: p, variant: "secondary"))
                Button("Refine") { submit() }
                    .buttonStyle(AstralButtonStyle(palette: p, variant: "primary"))
                    .disabled(trimmed.isEmpty)
            }
        }
        .padding(20)
        #if os(macOS)
        .frame(minWidth: 380)
        #endif
        .presentationDetents([.medium])
        .background(p.bg)
    }

    private func submit() {
        guard !trimmed.isEmpty else { return }
        model.refineComponent(target.componentId, instruction: trimmed)
        dismiss()
    }
}
