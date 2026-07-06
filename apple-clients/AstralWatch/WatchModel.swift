// Feature 051 — the watch app's brain: device-login lifecycle (start → QR →
// poll → tokens, auto-rotate before expiry), broker-based refresh, WS session
// with the `watch` device profile, transcript state, and speech coordination.
import Foundation
import SwiftUI
import AstralCore
#if os(watchOS)
import WatchKit
#endif

@MainActor
final class WatchModel: ObservableObject {

    enum Phase: Equatable {
        case signedOut
        case waitingApproval
        case loginFailed(String)
        case unavailable(String)
        case signedIn
    }

    enum Entry: Identifiable, Equatable {
        case user(id: String, text: String)
        case status(id: String, text: String)
        case turn(id: String, components: [AstralComponent])

        var id: String {
            switch self {
            case .user(let id, _), .status(let id, _), .turn(let id, _): return id
            }
        }
    }

    // MARK: published state

    @Published var phase: Phase = .signedOut
    @Published var login: DeviceLoginStart?
    @Published var loginExpiresAt: Date = .distantFuture
    @Published var recents: [ChatSummary] = []
    @Published var entries: [Entry] = []
    @Published var statusText: String?
    @Published var errorBanner: String?
    @Published var connected = false
    @Published var accountName = ""
    @Published var pendingDictation = ""

    let speaker = Speaker()

    // MARK: config + session

    /// Dev default; long-press the QR screen to change in a later polish task.
    var serverBase = URL(string: "http://127.0.0.1:8001")!
    private let sessionId = UUID().uuidString
    private let store: TokenStorage = {
        #if canImport(Security)
        KeychainTokenStore(service: "com.kyopenscience.astral.watch")
        #else
        InMemoryTokenStore()
        #endif
    }()

    private var tokens: TokenSet?
    private var loginTask: Task<Void, Never>?
    private var wsTask: Task<Void, Never>?
    private var ws: WSClient?

    var deviceLogin: DeviceLoginClient {
        DeviceLoginClient(serverBase: serverBase)
    }

    var rest: RestClient {
        RestClient(serverBase: serverBase) { [weak self] in
            await self?.freshAccessToken()
        }
    }

    // MARK: lifecycle

    func bootstrap() async {
        if let stored = store.load() {
            tokens = stored.tokenSet
            if await freshAccessToken() != nil {
                await enterSignedIn()
                return
            }
            store.wipe()
            tokens = nil
        }
        beginDeviceLogin()
    }

    // MARK: US3 — QR sign-in

    func beginDeviceLogin() {
        loginTask?.cancel()
        phase = .signedOut
        login = nil
        loginTask = Task { await runDeviceLogin() }
    }

    private func runDeviceLogin() async {
        while !Task.isCancelled {
            do {
                let start = try await deviceLogin.start()
                login = start
                loginExpiresAt = Date().addingTimeInterval(start.expiresIn)
                phase = .waitingApproval

                // Rotate to a fresh code shortly before expiry (FR-023).
                let rotation = Task { [expiresIn = start.expiresIn] in
                    try? await Task.sleep(nanoseconds: UInt64(max(expiresIn - 10, 5) * 1_000_000_000))
                }
                let result: DeviceLoginPoll = try await withThrowingTaskGroup(of: DeviceLoginPoll?.self) { group in
                    group.addTask { try await self.deviceLogin.waitForApproval(start: start) }
                    group.addTask { await rotation.value; return nil }
                    defer { group.cancelAll() }
                    while let next = try await group.next() {
                        if let terminal = next { return terminal }
                        return .expired   // rotation fired first
                    }
                    return .expired
                }

                switch result {
                case .approved(let set):
                    tokens = set
                    store.save(StoredTokens(from: set))
                    await enterSignedIn()
                    return
                case .denied(let reason):
                    phase = .loginFailed(reason == "denied_no_access"
                        ? "This account doesn't have access."
                        : "Sign-in was declined.")
                    return
                case .expired:
                    continue          // auto-rotate: fetch a fresh QR
                case .pending, .slowDown:
                    continue
                }
            } catch DeviceLoginError.unavailable(let detail) {
                phase = .unavailable(detail)
                return
            } catch is CancellationError {
                return
            } catch {
                phase = .unavailable("Can't reach the server.")
                return
            }
        }
    }

    // MARK: session

    private func freshAccessToken() async -> String? {
        guard var current = tokens else { return nil }
        if current.needsRefresh() {
            guard let refresh = current.refreshToken else { return nil }
            do {
                current = try await deviceLogin.refresh(refreshToken: refresh)
                tokens = current
                store.save(StoredTokens(from: current))
            } catch {
                return nil
            }
        }
        return current.accessToken
    }

    private func enterSignedIn() async {
        accountName = tokens?.displayName ?? ""
        phase = .signedIn
        connectWS()
        await refreshRecents()
    }

    func signOut() async {
        if let refresh = tokens?.refreshToken {
            _ = try? await rest.logout(clientId: "astral-watch", refreshToken: refresh)
        }
        wsTask?.cancel()
        await ws?.stop()
        ws = nil
        store.wipe()
        tokens = nil
        entries = []
        recents = []
        speaker.stop()
        beginDeviceLogin()
    }

    // MARK: WS

    private var viewport: (Int, Int) {
        #if os(watchOS)
        let bounds = WKInterfaceDevice.current().screenBounds
        return (Int(bounds.width), Int(bounds.height))
        #else
        return (198, 242)
        #endif
    }

    private func connectWS() {
        wsTask?.cancel()
        let client = WSClient(url: rest.webSocketURL)
        ws = client
        var resumed = false
        wsTask = Task {
            let events = await client.events()
            await client.start(onConnect: { [weak self] in
                guard let self else { return nil }
                guard let token = await self.freshAccessToken() else { return nil }
                let (w, h) = await self.viewport
                let register = Outbound.registerUI(
                    token: token, sessionId: await self.sessionId,
                    device: .watch(viewportWidth: w, viewportHeight: h),
                    resumed: resumed)
                resumed = true
                return register
            })
            for await event in events {
                await self.handle(event)
            }
        }
    }

    private func handle(_ event: WSEvent) async {
        switch event {
        case .connected:
            connected = true
        case .disconnected:
            connected = false
        case .sendDropped:
            errorBanner = "Connection is behind; some input was dropped."
        case .frame(let frame):
            handleFrame(frame)
        }
    }

    private func handleFrame(_ frame: InboundFrame) {
        // Dispositions: ClientDispositions.watch — unlisted/ignored frames
        // fall through the default silently (FR-003).
        switch frame.name {
        case "ui_render":
            let comps = frame.renderComponents
            guard !comps.isEmpty else { return }
            let turnId = "render-\(entries.count)"
            entries.append(.turn(id: turnId, components: comps))
            statusText = nil
            speaker.speak(frame.speech, turnId: turnId)
        case "ui_upsert":
            let comps = frame.upsertOps.compactMap(\.component)
            guard !comps.isEmpty else { return }
            let turnId = "upsert-\(entries.count)"
            entries.append(.turn(id: turnId, components: comps))
            speaker.speak(frame.speech, turnId: turnId)
        case "ui_stream_data":
            if let text = frame.streamComponents.first?.textContent {
                statusText = text
            }
        case "chat_status", "chat_step":
            statusText = frame.statusText
        case "user_message_acked":
            statusText = "Thinking…"
        case "chat_created":
            entries = []
        case "error", "stream_error":
            errorBanner = frame.errorMessage
            statusText = nil
        case "auth_required":
            Task { await self.signOut() }
        default:
            break
        }
    }

    // MARK: US4 — conversation

    func refreshRecents() async {
        recents = Array((try? await rest.chats())?.prefix(10) ?? [])
    }

    func newConversation() {
        entries = []
        errorBanner = nil
        Task { await ws?.send(Outbound.newChat(sessionId: sessionId)) }
    }

    func openChat(_ chat: ChatSummary) {
        entries = []
        Task { await ws?.send(Outbound.loadChat(sessionId: sessionId, chatId: chat.id)) }
    }

    /// Dictated text goes through the STANDARD chat path (FR-029) after the
    /// user confirms it (edge case: garbled dictation never auto-sends).
    func sendPending() {
        let text = pendingDictation.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        pendingDictation = ""
        entries.append(.user(id: "user-\(entries.count)", text: text))
        statusText = "Sending…"
        Task { await ws?.send(Outbound.chatMessage(text, sessionId: sessionId)) }
    }
}
