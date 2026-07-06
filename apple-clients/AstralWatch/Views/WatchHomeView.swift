// Feature 051 US4 — signed-in watch home: one-tap new conversation, bounded
// recents, visible account identity, one-tap sign-out (FR-028).
import SwiftUI
import AstralCore

struct WatchHomeView: View {
    @EnvironmentObject var model: WatchModel

    var body: some View {
        List {
            Section {
                NavigationLink {
                    WatchChatView()
                        .onAppear { model.newConversation() }
                } label: {
                    Label("New conversation", systemImage: "plus.bubble.fill")
                        .font(.headline)
                }
            }

            if !model.recents.isEmpty {
                Section("Recent") {
                    ForEach(model.recents) { chat in
                        NavigationLink {
                            WatchChatView()
                                .onAppear { model.openChat(chat) }
                        } label: {
                            Text(chat.title).lineLimit(2)
                        }
                    }
                }
            }

            Section {
                // The approving account is always visible so a mistaken
                // approval is immediately obvious (spec edge case).
                Label(model.accountName.isEmpty ? "Signed in" : model.accountName,
                      systemImage: "person.crop.circle")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                Button(role: .destructive) {
                    Task { await model.signOut() }
                } label: {
                    Label("Sign out", systemImage: "rectangle.portrait.and.arrow.right")
                }
            }
        }
        .navigationTitle("AstralBody")
        .task { await model.refreshRecents() }
        .overlay(alignment: .bottom) {
            if !model.connected {
                Text("Reconnecting…")
                    .font(.footnote)
                    .padding(4)
                    .background(.ultraThinMaterial, in: Capsule())
            }
        }
    }
}
