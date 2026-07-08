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
        case user(id: String, text: String, attachments: [String])
        case status(id: String, text: String)
        case turn(id: String, components: [AstralComponent])

        var id: String {
            switch self {
            case .user(let id, _, _), .status(let id, _), .turn(let id, _): return id
            }
        }
    }

    // MARK: published state

    @Published var phase: Phase = .signedOut
    @Published var login: DeviceLoginStart?
    @Published var loginExpiresAt: Date = .distantFuture
    @Published var recents: [ChatSummary] = []
    @Published var entries: [Entry] = []
    /// The live canvas — identity-keyed workspace components. `ui_upsert` ops
    /// apply in place (replace/remove by component_id) instead of stacking
    /// duplicate transcript entries (FR-013 as it reaches the watch).
    @Published var canvas: [AstralComponent] = []
    @Published var statusText: String?
    @Published var errorBanner: String?
    @Published var connected = false
    @Published var accountName = ""
    @Published var pendingDictation = ""

    let speaker = Speaker()

    // MARK: config + session

    /// Dev default from the shared config (backend .env PUBLIC_BASE_URL);
    /// long-press the QR screen to change in a later polish task.
    var serverBase = URL(string: AstralConfig.serverBaseURL)!
    /// The server-issued chat id this session is talking to. The backend
    /// routes by `session_id` FIRST — a made-up id would send every message
    /// to a phantom chat, so this is adopted from chat_created/chat_loaded
    /// and nil until the server assigns one.
    private var activeChatId: String?
    private let store: TokenStorage = {
        #if canImport(Security)
        KeychainTokenStore(service: "com.personalailabs.astraldeep.watch")
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
            switch await refreshOutcome() {
            case .ok, .transient:
                // Offline launch keeps the stored session (sign in once per
                // device) — the home screen shows "Reconnecting…" and the WS
                // backoff loop registers when the network returns. Only a
                // definitive IdP rejection returns the watch to the QR screen.
                await enterSignedIn()
                return
            case .rejected:
                store.wipe()
                tokens = nil
            }
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

                // Rotate to a fresh code shortly before expiry (FR-023). The
                // rotation timer must be a DIRECT child of the group: the
                // group awaits every child before returning, and a child that
                // awaits an outer Task's `.value` is uncancellable — it would
                // pin an approved sign-in to the full ~10-minute timer.
                let result: DeviceLoginPoll = try await withThrowingTaskGroup(of: DeviceLoginPoll?.self) { group in
                    group.addTask { try await self.deviceLogin.waitForApproval(start: start) }
                    group.addTask { [expiresIn = start.expiresIn] in
                        // Task.sleep is cancellation-aware; cancelAll() ends it.
                        try? await Task.sleep(nanoseconds: UInt64(max(expiresIn - 10, 5) * 1_000_000_000))
                        return nil
                    }
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

    /// Ensure a live access token via the backend broker, with failures
    /// classified (rejected → QR screen; transient/offline → keep session).
    private func refreshOutcome() async -> RefreshResult {
        guard let current = tokens else { return .rejected("no session") }
        if !current.needsRefresh() { return .ok(current) }
        guard let refresh = current.refreshToken else { return .rejected("no refresh token") }
        let result = await RefreshStrategy.broker(deviceLogin).attempt(refreshToken: refresh)
        if case .ok(let set) = result {
            tokens = set
            store.save(StoredTokens(from: set))
        }
        return result
    }

    private func freshAccessToken() async -> String? {
        if case .ok(let set) = await refreshOutcome() { return set.accessToken }
        return nil
    }

    private func enterSignedIn() async {
        accountName = tokens?.displayName ?? ""
        phase = .signedIn
        connectWS()
        await refreshRecents()
    }

    func signOut() async {
        if let refresh = tokens?.refreshToken {
            _ = try? await rest.logout(clientId: AstralConfig.watchClientId, refreshToken: refresh)
        }
        wsTask?.cancel()
        await ws?.stop()
        ws = nil
        store.wipe()
        tokens = nil
        entries = []
        canvas = []
        recents = []
        activeChatId = nil
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
                    token: token, sessionId: await self.activeChatId,
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
            canvas = comps
            statusText = nil
            speaker.speak(frame.speech)
        case "ui_upsert":
            let ops = frame.upsertOps
            guard !ops.isEmpty else { return }
            canvas = Canvas.apply(canvas, ops)
            speaker.speak(frame.speech)
        case "ui_stream_data":
            if let text = frame.streamComponents.first?.textContent {
                statusText = text
            }
        case "chat_status", "chat_step":
            statusText = frame.statusText
        case "user_message_acked":
            activeChatId = frame.payload["payload"]?["chat_id"]?.stringValue
                ?? frame.payload["chat_id"]?.stringValue ?? activeChatId
            statusText = "Thinking…"
        case "chat_created":
            // Adopt the server-issued chat id; the transcript the user is
            // looking at (their just-sent bubble) must NOT be wiped.
            activeChatId = frame.payload["payload"]?["chat_id"]?.stringValue
                ?? frame.payload["chat_id"]?.stringValue ?? activeChatId
        case "chat_loaded":
            reduceChatLoaded(frame)
        case "error", "stream_error":
            errorBanner = frame.errorMessage
            statusText = nil
        case "auth_required":
            Task { await self.handleAuthRequired() }
        default:
            break
        }
    }

    /// The server refused our token. A near-expiry token refreshes anyway on
    /// the normal path, so FORCE a broker refresh here: an unchanged/refused
    /// credential means the session is dead server-side (revoked / hard cap)
    /// — wipe and return to the QR screen instead of looping reconnects.
    private func handleAuthRequired() async {
        guard let current = tokens, let refresh = current.refreshToken else {
            await signOut()
            return
        }
        switch await RefreshStrategy.broker(deviceLogin).attempt(refreshToken: refresh) {
        case .ok(let set) where set.accessToken != current.accessToken:
            tokens = set
            store.save(StoredTokens(from: set))
            // The reconnect loop re-registers with the fresh token.
        case .ok:
            await signOut()   // same token came back — the server will refuse it again
        case .rejected:
            await signOut()
        case .transient:
            break             // offline blip; keep the session and retry
        }
    }

    /// Re-hydrate a loaded transcript: user text with read-only attachment
    /// name-chips (FR-033/T049 — the watch has no upload affordance) and
    /// assistant narrative. Rich canvas content arrives right after as a
    /// speech-free `ui_render` (the server re-hydrates the workspace).
    private func reduceChatLoaded(_ frame: InboundFrame) {
        let chat = frame.payload["chat"]
        activeChatId = chat?["id"]?.stringValue ?? activeChatId
        canvas = []   // the server re-hydrates the workspace via ui_render next
        let messages = chat?["messages"]?.arrayValue ?? chat?["history"]?.arrayValue ?? []
        var loaded: [Entry] = []
        for (index, message) in messages.enumerated() {
            let role = message["role"]?.stringValue
                ?? (message["is_user"]?.boolValue == true ? "user" : "assistant")
            let text = message["content"]?.stringValue ?? message["text"]?.stringValue ?? ""
            if role == "user" {
                let names = (message["attachments"]?.arrayValue ?? [])
                    .compactMap { $0["filename"]?.stringValue }
                if !text.isEmpty || !names.isEmpty {
                    loaded.append(.user(id: "hist-\(index)", text: text, attachments: names))
                }
            } else if !text.isEmpty {
                loaded.append(.status(id: "hist-\(index)", text: text))
            }
        }
        entries = loaded
        statusText = nil
    }

    // MARK: US4 — conversation

    func refreshRecents() async {
        recents = Array((try? await rest.chats())?.prefix(10) ?? [])
    }

    func newConversation() {
        entries = []
        canvas = []
        activeChatId = nil   // the server assigns the id via chat_created
        errorBanner = nil
        Task { await ws?.send(Outbound.newChat(sessionId: nil)) }
    }

    func openChat(_ chat: ChatSummary) {
        entries = []
        canvas = []
        activeChatId = chat.id
        Task { await ws?.send(Outbound.loadChat(sessionId: chat.id, chatId: chat.id)) }
    }

    /// Dictated text goes through the STANDARD chat path (FR-029) after the
    /// user confirms it (edge case: garbled dictation never auto-sends).
    func sendPending() {
        let text = pendingDictation.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        pendingDictation = ""
        entries.append(.user(id: "user-\(entries.count)", text: text, attachments: []))
        statusText = "Sending…"
        Task { await ws?.send(Outbound.chatMessage(text, sessionId: activeChatId)) }
    }
}
