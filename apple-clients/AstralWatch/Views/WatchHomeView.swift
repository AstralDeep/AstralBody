import AstralCore
// Feature 051 US4 — signed-in watch home: one-tap new conversation, bounded
// recents, visible account identity, one-tap sign-out (FR-028).
import SwiftUI

struct WatchHomeView: View {
    @Environment(WatchModel.self) var model

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

            if let status = model.rootStatusText {
                let accessibility = WatchAccessibility060.rootStatus(status)
                Section("Live status") {
                    Label {
                        Text(status).lineLimit(3)
                    } icon: {
                        Image(systemName: "waveform.path.ecg")
                    }
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .accessibilityElement(children: .ignore)
                    .accessibilityIdentifier(accessibility.identifier)
                    .accessibilityLabel(accessibility.name)
                    .accessibilityValue(accessibility.state)
                    .accessibilityAddTraits(.updatesFrequently)
                }
            }

            Section {
                // The approving account is always visible so a mistaken
                // approval is immediately obvious (spec edge case).
                Label(
                    model.accountName.isEmpty ? "Signed in" : model.accountName,
                    systemImage: "person.crop.circle"
                )
                .font(.footnote)
                .foregroundStyle(.secondary)
                Button(role: .destructive) {
                    Task { await model.signOut() }
                } label: {
                    Label("Sign out", systemImage: "rectangle.portrait.and.arrow.right")
                }
            }
        }
        .navigationTitle("AstralDeep")
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
