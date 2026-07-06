// Feature 051 — window anatomy. macOS mirrors the Windows client (top bar:
// identity, connection status, new chat, search; left chat rail; canvas —
// FR-016). iOS mirrors Android's list→detail flow (FR-011).
import SwiftUI
import AstralCore

struct RootView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        if !model.signedIn {
            SignInView()
        } else {
            NavigationSplitView {
                ChatListView()
                    .navigationTitle("Chats")
            } detail: {
                ChatView()
            }
            .searchable(text: $model.searchText, prompt: "Search chats")
            .toolbar {
                ToolbarItemGroup {
                    connectionDot
                    Text(model.accountName)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                    Button {
                        model.newChat()
                    } label: {
                        Label("New chat", systemImage: "plus.bubble")
                    }
                    .accessibilityLabel("New chat")
                    Menu {
                        Button("Sign out", role: .destructive) {
                            Task { await model.signOut() }
                        }
                    } label: {
                        Label("Account", systemImage: "person.crop.circle")
                    }
                    .accessibilityLabel("Account menu")
                }
            }
        }
    }

    private var connectionDot: some View {
        Circle()
            .fill(model.connected ? Color.green : Color.orange)
            .frame(width: 9, height: 9)
            .accessibilityLabel(model.connected ? "Connected" : "Reconnecting")
    }
}

struct SignInView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: "sparkles")
                .font(.system(size: 42))
                .foregroundStyle(.tint)
            Text("AstralBody")
                .font(.largeTitle.bold())

            Form {
                TextField("Server (e.g. http://127.0.0.1:8001)", text: $model.serverBaseText)
                    .textContentType(.URL)
                    .autocorrectionDisabled()
                TextField("Keycloak realm URL", text: $model.authorityText)
                    .autocorrectionDisabled()
            }
            .formStyle(.grouped)
            .frame(maxWidth: 480, maxHeight: 170)

            Button {
                model.signIn()
            } label: {
                Label("Sign in", systemImage: "person.badge.key")
                    .frame(maxWidth: 240)
            }
            .buttonStyle(.borderedProminent)
            .accessibilityLabel("Sign in with your browser")

            if let error = model.signInError {
                Text(error)
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
            }
        }
        .padding()
    }
}
