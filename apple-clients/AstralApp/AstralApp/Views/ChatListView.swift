// Feature 051 — the History screen (Android HistoryScreen parity): recent chats
// (from the `get_history` → `history_list` WS round trip) as tappable cards; a
// skeleton while loading; tap opens the conversation.
import SwiftUI
import AstralCore

struct HistoryView: View {
    @EnvironmentObject var model: AppModel
    @EnvironmentObject var theme: ThemeStore
    private var p: AstralPalette { theme.palette }

    var body: some View {
        Group {
            if model.historyLoading && model.history.isEmpty {
                SkeletonList()
            } else if model.history.isEmpty {
                VStack(spacing: 8) {
                    Text("💬").font(.system(size: 40))
                    Text("No conversations yet.").foregroundStyle(p.muted)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(model.history) { chat in
                            Button { model.openChat(chat.id) } label: { row(chat) }
                                .buttonStyle(.plain)
                                .contextMenu {
                                    Button(role: .destructive) {
                                        model.deleteChat(chat.id)
                                    } label: {
                                        Label("Delete conversation", systemImage: "trash")
                                    }
                                }
                        }
                    }
                    .padding(16)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(p.bg)
    }

    private func row(_ chat: ChatSummary) -> some View {
        Text(chat.title.isEmpty ? "Untitled conversation" : chat.title)
            .foregroundStyle(p.text)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
            .background(p.surface2, in: RoundedRectangle(cornerRadius: AstralRadius.md))
    }
}
