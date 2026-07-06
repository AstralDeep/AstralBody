// Feature 051 — the canvas + input: streaming lifecycle (ack → progress →
// narrative → components), visible error banners (FR-012/FR-015), and the
// 040 slash-command typeahead parity touch.
import SwiftUI
import AstralCore

struct ChatView: View {
    @EnvironmentObject var model: AppModel
    @State private var draft = ""
    @FocusState private var inputFocused: Bool

    private let slashCommands = ["/help", "/agents", "/summarize", "/research", "/weather"]

    var body: some View {
        VStack(spacing: 0) {
            if let banner = model.errorBanner {
                Label(banner, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout)
                    .padding(8)
                    .frame(maxWidth: .infinity)
                    .background(.red.opacity(0.15))
                    .onTapGesture { model.errorBanner = nil }
                    .accessibilityLabel("Error: \(banner). Tap to dismiss.")
            }

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 10) {
                        ForEach(model.entries) { entry in
                            entryView(entry).id(entry.id)
                        }
                        if !model.streamingText.isEmpty {
                            Text(model.streamingText)
                                .textSelection(.enabled)
                                .id("streaming")
                        }
                        if let status = model.statusText {
                            HStack(spacing: 6) {
                                ProgressView().controlSize(.small)
                                Text(status)
                                    .font(.callout)
                                    .foregroundStyle(.secondary)
                            }
                            .id("status")
                        }
                    }
                    .padding()
                }
                .onChange(of: model.entries.count) { _, _ in
                    if let last = model.entries.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
            }

            Divider()
            inputBar
        }
    }

    @ViewBuilder
    private func entryView(_ entry: AppModel.Entry) -> some View {
        switch entry {
        case .user(_, let text):
            Text(text)
                .padding(10)
                .background(.blue.opacity(0.15), in: RoundedRectangle(cornerRadius: 10))
                .frame(maxWidth: .infinity, alignment: .trailing)
        case .turn(_, let components):
            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(components.enumerated()), id: \.offset) { _, comp in
                    ComponentView(component: comp)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var inputBar: some View {
        VStack(alignment: .leading, spacing: 4) {
            // Slash-command typeahead (feature 040 parity).
            if draft.hasPrefix("/") && !draft.contains(" ") {
                HStack {
                    ForEach(slashCommands.filter { $0.hasPrefix(draft) }, id: \.self) { cmd in
                        Button(cmd) { draft = cmd + " " }
                            .font(.callout.monospaced())
                            .buttonStyle(.bordered)
                    }
                }
                .padding(.horizontal, 8)
            }
            HStack(spacing: 8) {
                TextField("Message AstralBody…", text: $draft, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(1...5)
                    .focused($inputFocused)
                    .onSubmit(sendDraft)
                Button(action: sendDraft) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title2)
                }
                .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
                .accessibilityLabel("Send message")
            }
            .padding(8)
        }
    }

    private func sendDraft() {
        model.send(draft)
        draft = ""
        inputFocused = true
    }
}
