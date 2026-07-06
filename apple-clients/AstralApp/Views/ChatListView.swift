// Feature 051 — the chat rail: history with open/delete (swipe on iOS,
// context menu on macOS — Windows-rail parity, FR-011/FR-016).
import SwiftUI
import AstralCore

struct ChatListView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        List {
            ForEach(model.filteredChats) { chat in
                Button {
                    model.openChat(chat)
                } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(chat.title)
                            .lineLimit(2)
                        if !chat.updatedAt.isEmpty {
                            Text(chat.updatedAt)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .buttonStyle(.plain)
                .contextMenu {
                    Button("Delete", role: .destructive) {
                        model.deleteChat(chat)
                    }
                }
                #if os(iOS)
                .swipeActions {
                    Button("Delete", role: .destructive) {
                        model.deleteChat(chat)
                    }
                }
                #endif
            }
        }
        .overlay {
            if model.chats.isEmpty {
                ContentUnavailableView("No chats yet",
                                       systemImage: "bubble.left.and.bubble.right",
                                       description: Text("Start a new conversation."))
            }
        }
        .refreshable {
            model.chats = (try? await model.rest.chats()) ?? model.chats
        }
    }
}
