// Feature 051 US4 — the conversation on the wrist: crown-scrollable adapted
// components, dictation-first input with confirm-before-send, and speech
// controls (stop/replay; navigation away stops playback).
import SwiftUI
import AstralCore

struct WatchChatView: View {
    @EnvironmentObject var model: WatchModel

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(model.entries) { entry in
                        entryView(entry).id(entry.id)
                    }
                    if let status = model.statusText {
                        HStack(spacing: 4) {
                            ProgressView().controlSize(.mini)
                            Text(status).font(.footnote).foregroundStyle(.secondary)
                        }
                    }
                    if let banner = model.errorBanner {
                        Label(banner, systemImage: "exclamationmark.triangle")
                            .font(.footnote)
                            .foregroundStyle(.orange)
                    }
                    inputArea
                }
            }
            .onChange(of: model.entries.count) { _, _ in
                if let last = model.entries.last {
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
        }
        .navigationTitle("Chat")
        .toolbar {
            ToolbarItemGroup(placement: .bottomBar) {
                Button {
                    model.speaker.replay()
                } label: {
                    Image(systemName: "arrow.counterclockwise.circle")
                }
                .accessibilityLabel("Replay spoken response")
                Spacer()
                Button {
                    model.speaker.stop()
                } label: {
                    Image(systemName: model.speaker.isSpeaking
                          ? "speaker.slash.circle.fill" : "speaker.circle")
                }
                .accessibilityLabel("Stop speaking")
            }
        }
        .onDisappear { model.speaker.stop() }   // navigation stops playback
    }

    @ViewBuilder
    private func entryView(_ entry: WatchModel.Entry) -> some View {
        switch entry {
        case .user(_, let text):
            Text(text)
                .font(.footnote)
                .padding(6)
                .frame(maxWidth: .infinity, alignment: .trailing)
                .background(.blue.opacity(0.25), in: RoundedRectangle(cornerRadius: 8))
        case .status(_, let text):
            Text(text).font(.footnote).foregroundStyle(.secondary)
        case .turn(_, let components):
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(components.enumerated()), id: \.offset) { _, comp in
                    WatchComponentView(component: comp)
                }
            }
        }
    }

    /// Dictation-first (TextFieldLink opens the system dictation/scribble
    /// sheet); the dictated text lands in a pending row with explicit
    /// Send/Discard — garbled dictation never auto-sends (FR-029).
    @ViewBuilder
    private var inputArea: some View {
        if model.pendingDictation.isEmpty {
            TextFieldLink(prompt: Text("Ask by voice")) {
                Label("Ask", systemImage: "mic.fill")
                    .frame(maxWidth: .infinity)
            } onSubmit: { text in
                model.pendingDictation = text
            }
        } else {
            VStack(alignment: .leading, spacing: 4) {
                Text("“\(model.pendingDictation)”")
                    .font(.footnote)
                    .italic()
                HStack {
                    Button("Send") { model.sendPending() }
                        .buttonStyle(.borderedProminent)
                    Button("Discard", role: .destructive) {
                        model.pendingDictation = ""
                    }
                }
                .font(.footnote)
            }
        }
    }
}
