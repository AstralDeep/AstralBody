// Feature 051 — shared app model for iOS/macOS: system-browser PKCE
// (ASWebAuthenticationSession, hand-rolled like the Windows client), direct
// IdP refresh, WS session with the ios/macos device profile, chat state.
import Foundation
import SwiftUI
import AuthenticationServices
import AstralCore
#if os(iOS)
import UIKit
#else
import AppKit
#endif

@MainActor
final class AppModel: NSObject, ObservableObject {

    enum Entry: Identifiable, Equatable {
        case user(id: String, text: String)
        case turn(id: String, components: [AstralComponent])

        var id: String {
            switch self {
            case .user(let id, _), .turn(let id, _): return id
            }
        }
    }

    // MARK: configuration (dev defaults; editable on the sign-in screen)

    @AppStorage("serverBase") var serverBaseText = "http://127.0.0.1:8001"
    @AppStorage("authority") var authorityText = ""

    #if os(macOS)
    let clientId = "astral-macos"
    #else
    let clientId = "astral-ios"
    #endif
    let redirectURI = "astral://oauth2redirect"

    // MARK: published state

    @Published var signedIn = false
    @Published var accountName = ""
    @Published var connected = false
    @Published var chats: [ChatSummary] = []
    @Published var entries: [Entry] = []
    @Published var statusText: String?
    @Published var errorBanner: String?
    @Published var streamingText = ""
    @Published var signInError: String?
    @Published var searchText = ""

    // MARK: session plumbing

    private let sessionId = UUID().uuidString
    private let store: TokenStorage = {
        #if canImport(Security)
        KeychainTokenStore()
        #else
        InMemoryTokenStore()
        #endif
    }()
    private var tokens: TokenSet?
    private var ws: WSClient?
    private var wsTask: Task<Void, Never>?
    private var authSession: ASWebAuthenticationSession?

    var serverBase: URL {
        URL(string: serverBaseText) ?? URL(string: "http://127.0.0.1:8001")!
    }

    var oidc: OIDCConfig? {
        guard let authority = URL(string: authorityText), !authorityText.isEmpty else { return nil }
        return OIDCConfig(authority: authority, clientId: clientId, redirectURI: redirectURI)
    }

    var rest: RestClient {
        RestClient(serverBase: serverBase) { [weak self] in
            await self?.freshAccessToken()
        }
    }

    var filteredChats: [ChatSummary] {
        guard !searchText.isEmpty else { return chats }
        return chats.filter { $0.title.localizedCaseInsensitiveContains(searchText) }
    }

    // MARK: lifecycle

    func bootstrap() async {
        if let stored = store.load() {
            tokens = stored.tokenSet
            if await freshAccessToken() != nil {
                await enterSignedIn(resumedSession: true)
                return
            }
            store.wipe()
            tokens = nil
        }
    }

    // MARK: sign-in (FR-007)

    func signIn() {
        guard let oidc else {
            signInError = "Set the Keycloak realm URL first."
            return
        }
        signInError = nil
        let verifier = PKCE.makeVerifier()
        let state = PKCE.makeVerifier()
        let url = oidc.authorizeURL(state: state, challenge: PKCE.challenge(for: verifier))

        let session = ASWebAuthenticationSession(url: url, callbackURLScheme: "astral") {
            [weak self] callback, error in
            guard let self else { return }
            Task { @MainActor in
                if let error {
                    self.signInError = error.localizedDescription
                    return
                }
                guard let callback,
                      let items = URLComponents(url: callback, resolvingAgainstBaseURL: false)?.queryItems,
                      items.first(where: { $0.name == "state" })?.value == state,
                      let code = items.first(where: { $0.name == "code" })?.value else {
                    self.signInError = "Sign-in was cancelled."
                    return
                }
                await self.exchange(code: code, verifier: verifier, oidc: oidc)
            }
        }
        session.presentationContextProvider = self
        session.prefersEphemeralWebBrowserSession = false
        authSession = session
        session.start()
    }

    private func exchange(code: String, verifier: String, oidc: OIDCConfig) async {
        var request = URLRequest(url: oidc.tokenEndpoint)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        request.httpBody = Data(oidc.tokenRequestBody(code: code, verifier: verifier).utf8)
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard status == 200, let json = try? JSONValue.parse(data),
                  let set = TokenSet(json: json) else {
                signInError = "Token exchange failed (HTTP \(status))."
                return
            }
            tokens = set
            store.save(StoredTokens(from: set))
            await enterSignedIn(resumedSession: false)
        } catch {
            signInError = error.localizedDescription
        }
    }

    private func freshAccessToken() async -> String? {
        guard var current = tokens else { return nil }
        if current.needsRefresh() {
            guard let refresh = current.refreshToken, let oidc else { return nil }
            do {
                current = try await RefreshStrategy.direct(oidc)
                    .refresh(refreshToken: refresh)
                tokens = current
                store.save(StoredTokens(from: current))
            } catch {
                return nil
            }
        }
        return current.accessToken
    }

    private func enterSignedIn(resumedSession: Bool) async {
        accountName = tokens?.displayName ?? ""
        signedIn = true
        connectWS(resumed: resumedSession)
        chats = (try? await rest.chats()) ?? []
    }

    func signOut() async {
        if let refresh = tokens?.refreshToken {
            _ = try? await rest.logout(clientId: clientId, refreshToken: refresh)
        }
        wsTask?.cancel()
        await ws?.stop()
        ws = nil
        store.wipe()
        tokens = nil
        signedIn = false
        chats = []
        entries = []
    }

    // MARK: WS (FR-002/FR-005)

    private var device: DeviceDescriptor {
        #if os(macOS)
        return .macos(viewportWidth: 1280, viewportHeight: 800)
        #else
        let size = UIScreen.main.bounds.size
        return .ios(viewportWidth: Int(size.width), viewportHeight: Int(size.height))
        #endif
    }

    private func connectWS(resumed initialResumed: Bool) {
        wsTask?.cancel()
        let client = WSClient(url: rest.webSocketURL)
        ws = client
        var resumed = initialResumed
        wsTask = Task {
            let events = await client.events()
            await client.start(onConnect: { [weak self] in
                guard let self else { return nil }
                guard let token = await self.freshAccessToken() else { return nil }
                let frame = Outbound.registerUI(
                    token: token, sessionId: await self.sessionId,
                    device: await self.device, resumed: resumed)
                resumed = true
                return frame
            })
            for await event in events {
                await self.handle(event)
            }
        }
    }

    private func handle(_ event: WSEvent) async {
        switch event {
        case .connected: connected = true
        case .disconnected: connected = false
        case .sendDropped(let total):
            errorBanner = "Offline queue overflowed (\(total) dropped)."
        case .frame(let frame): handleFrame(frame)
        }
    }

    private func handleFrame(_ frame: InboundFrame) {
        switch frame.name {
        case "ui_render":
            let comps = frame.renderComponents
            guard !comps.isEmpty else { return }
            streamingText = ""
            statusText = nil
            entries.append(.turn(id: "render-\(entries.count)", components: comps))
        case "ui_upsert":
            applyUpsert(frame.upsertOps)
        case "ui_stream_data":
            if let text = frame.streamComponents.compactMap(\.textContent).last {
                streamingText = text
            }
            if frame.streamTerminal { statusText = nil }
        case "chat_status", "chat_step":
            statusText = frame.statusText
        case "user_message_acked":
            statusText = "Working…"
        case "chat_created":
            entries = []
            Task { self.chats = (try? await self.rest.chats()) ?? self.chats }
        case "chat_loaded":
            entries = []
            let messages = frame.payload["chat"]?["messages"]?.arrayValue ?? []
            for (index, message) in messages.enumerated() {
                if let text = message["content"]?.stringValue,
                   message["role"]?.stringValue == "user" {
                    entries.append(.user(id: "hist-u\(index)", text: text))
                }
                let comps = AstralComponent.list(from: message["components"])
                if !comps.isEmpty {
                    entries.append(.turn(id: "hist-c\(index)", components: comps))
                }
            }
        case "history_list":
            break // chats come from REST; WS twin acknowledged
        case "error", "stream_error":
            errorBanner = frame.errorMessage
            statusText = nil
        case "auth_required":
            Task { await self.signOut() }
        default:
            break // ClientDispositions.ios/.macos — deliberate ignores
        }
    }

    /// In-place op application preserving order (FR-013): replace by
    /// component identity where known, else append; remove drops.
    private func applyUpsert(_ ops: [UpsertOp]) {
        for op in ops {
            switch op.op {
            case "remove":
                guard let cid = op.componentId else { continue }
                for (index, entry) in entries.enumerated() {
                    if case .turn(let id, var comps) = entry {
                        comps.removeAll { $0.componentId == cid }
                        entries[index] = .turn(id: id, components: comps)
                    }
                }
            default:
                guard let component = op.component else { continue }
                var replaced = false
                if let cid = op.componentId {
                    for (index, entry) in entries.enumerated() {
                        if case .turn(let id, var comps) = entry,
                           let slot = comps.firstIndex(where: { $0.componentId == cid }) {
                            comps[slot] = component
                            entries[index] = .turn(id: id, components: comps)
                            replaced = true
                            break
                        }
                    }
                }
                if !replaced {
                    entries.append(.turn(id: "upsert-\(entries.count)",
                                         components: [component]))
                }
            }
        }
    }

    // MARK: chat actions

    func newChat() {
        entries = []
        errorBanner = nil
        Task { await ws?.send(Outbound.newChat(sessionId: sessionId)) }
    }

    func openChat(_ chat: ChatSummary) {
        entries = []
        Task { await ws?.send(Outbound.loadChat(sessionId: sessionId, chatId: chat.id)) }
    }

    func deleteChat(_ chat: ChatSummary) {
        Task {
            _ = try? await rest.deleteChat(id: chat.id)
            chats = (try? await rest.chats()) ?? chats
        }
    }

    func send(_ text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        entries.append(.user(id: "user-\(entries.count)", text: trimmed))
        statusText = "Sending…"
        Task { await ws?.send(Outbound.chatMessage(trimmed, sessionId: sessionId)) }
    }
}

extension AppModel: ASWebAuthenticationPresentationContextProviding {
    nonisolated func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        #if os(macOS)
        return NSApplication.shared.mainWindow ?? ASPresentationAnchor()
        #else
        return UIApplication.shared.connectedScenes
            .compactMap { ($0 as? UIWindowScene)?.keyWindow }
            .first ?? ASPresentationAnchor()
        #endif
    }
}
