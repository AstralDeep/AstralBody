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
@Observable
final class WatchModel {

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

    // MARK: observable state

    var phase: Phase = .signedOut
    var login: DeviceLoginStart?
    var loginExpiresAt: Date = .distantFuture
    var recents: [ChatSummary] = []
    var entries: [Entry] = []
    /// The live canvas — identity-keyed workspace components. `ui_upsert` ops
    /// apply in place (replace/remove by component_id) instead of stacking
    /// duplicate transcript entries (FR-013 as it reaches the watch).
    var canvas: [AstralComponent] = []
    var statusText: String?
    var errorBanner: String?
    var connected = false
    var accountName = ""
    var pendingDictation = ""

    let speaker = Speaker()

    // MARK: config + session

    /// The backend this watch talks to: a validated override pushed by the iPhone
    /// companion if one has ever arrived, else the build-time endpoint from
    /// Config/*.xcconfig (feature 053, FR-011). A watch with no companion — which
    /// is a fully supported state — simply keeps the build-time value.
    var serverBase = WatchOverrideSync.resolvedServerBase()
    /// The server-issued chat id this session is talking to. The backend
    /// routes by `session_id` FIRST — a made-up id would send every message
    /// to a phantom chat, so this is adopted from chat_created/chat_loaded
    /// and nil until the server assigns one.
    @ObservationIgnored private var activeChatId: String?
    private let store: TokenStorage = {
        #if canImport(Security)
        KeychainTokenStore(service: "com.personalailabs.astraldeep.watch")
        #else
        InMemoryTokenStore()
        #endif
    }()

    /// Retained so the companion-override observer outlives `bootstrap()`.
    @ObservationIgnored private var overrideObserver: NSObjectProtocol?

    @ObservationIgnored private var tokens: TokenSet?
    @ObservationIgnored private var loginTask: Task<Void, Never>?
    @ObservationIgnored private var wsTask: Task<Void, Never>?
    @ObservationIgnored private var ws: WSClient?
    /// Single-flight refresh (see `refreshOutcome`) + a session generation so
    /// a refresh resolving after sign-out can never resurrect wiped
    /// credentials or be joined by the next account's session.
    @ObservationIgnored private var refreshTask: Task<RefreshResult, Never>?
    @ObservationIgnored private var refreshTaskGeneration = -1
    @ObservationIgnored private var sessionGeneration = 0

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
        // Feature 053 — listen for an endpoint override from the iPhone companion.
        // Opportunistic: activate() no-ops without a companion, and the observer
        // simply never fires. `deviceLogin`/`rest` are computed from `serverBase`,
        // so adopting a new endpoint rebuilds them on the next use.
        WatchOverrideSync.shared.activate()
        overrideObserver = NotificationCenter.default.addObserver(
            forName: WatchOverrideSync.didChangeNotification,
            object: nil, queue: .main
        ) { [weak self] _ in
            // Delivered on `queue: .main`, and WatchModel is MainActor-isolated,
            // so we are already where we need to be — no hop, no captured-var
            // concurrency warning.
            MainActor.assumeIsolated {
                self?.serverBase = WatchOverrideSync.resolvedServerBase()
            }
        }

        if let stored = store.load() {
            tokens = stored.tokenSet
            // Enter the signed-in home IMMEDIATELY: the WS dial starts now
            // and the register frame waits on the (single-flight) broker
            // refresh inside onConnect, so the two round trips overlap
            // instead of running back-to-back behind the QR spinner. An
            // offline launch keeps the stored session (sign in once per
            // device) — the home screen shows "Reconnecting…" and the WS
            // backoff loop registers when the network returns. Only a
            // definitive IdP rejection returns the watch to the QR screen.
            enterSignedIn()
            if case .rejected = await refreshOutcome() {
                await signOut(revokeRemote: false)   // ends at the QR screen
            }
            return
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
                    enterSignedIn()
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
    /// SINGLE-FLIGHT: concurrent callers (the WS onConnect and the recents /
    /// audit REST tokenProvider) join one in-flight broker round trip — two
    /// parallel grants with the same rotating refresh token can revoke the
    /// whole session at the IdP.
    private func refreshOutcome() async -> RefreshResult {
        if let inFlight = refreshTask, refreshTaskGeneration == sessionGeneration {
            return await inFlight.value
        }
        guard let current = tokens else { return .rejected("no session") }
        if !current.needsRefresh() { return .ok(current) }
        return await runRefresh()
    }

    /// Start (and register) a refresh attempt unconditionally —
    /// `refreshOutcome` gates it behind expiry, `handleAuthRequired` forces it.
    private func runRefresh() async -> RefreshResult {
        guard let refresh = tokens?.refreshToken else { return .rejected("no refresh token") }
        let generation = sessionGeneration
        let broker = deviceLogin
        let attempt = Task { await RefreshStrategy.broker(broker).attempt(refreshToken: refresh) }
        refreshTask = attempt
        refreshTaskGeneration = generation
        let result = await attempt.value
        if refreshTaskGeneration == generation { refreshTask = nil }
        // A sign-out while the request was in flight ended this session —
        // never resurrect wiped credentials.
        if case .ok(let set) = result, generation == sessionGeneration {
            tokens = set
            store.save(StoredTokens(from: set))
        }
        return result
    }

    private func freshAccessToken() async -> String? {
        if case .ok(let set) = await refreshOutcome() { return set.accessToken }
        return nil
    }

    private func enterSignedIn() {
        accountName = tokens?.displayName ?? ""
        phase = .signedIn
        connectWS()
        // Recents load via WatchHomeView's `.task` the moment home appears
        // (it appears on every path into `.signedIn`) — no eager fetch here.
    }

    /// `revokeRemote: false` skips the server-side revocation round trip —
    /// used when the IdP has ALREADY refused the credential (nothing to
    /// revoke, and the call would only delay returning to the QR screen).
    func signOut(revokeRemote: Bool = true) async {
        if revokeRemote, let refresh = tokens?.refreshToken {
            _ = try? await rest.logout(clientId: AstralConfig.watchClientId, refreshToken: refresh)
        }
        sessionGeneration += 1
        refreshTask = nil
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
            if frame.renderTarget == "chat" {
                // End-of-turn narrative — a transcript entry, NOT a canvas
                // replacement: clobbering here wiped the components the
                // ui_upsert just delivered (iOS diverts the same way).
                entries.append(.turn(id: "turn-\(entries.count)", components: comps))
            } else {
                canvas = comps
            }
            statusText = nil
            speaker.speak(frame.speech)
        case "ui_upsert":
            let ops = frame.upsertOps
            guard !ops.isEmpty else { return }
            // 055 uniform rule: the watch has no turn state, so the ephemeral
            // welcome (`wel_` identities) is purged whenever ops land — turn
            // content must never render under a retained welcome (the empty
            // blanking render was always dropped by the guard above).
            canvas = Canvas.apply(canvas.dropWelcome(), ops)
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
    /// the normal path, so join the in-flight refresh if one is running,
    /// otherwise FORCE a broker refresh: an unchanged/refused credential
    /// means the session is dead server-side (revoked / hard cap) — wipe and
    /// return to the QR screen instead of looping reconnects.
    private func handleAuthRequired() async {
        guard let refused = tokens?.accessToken else {
            await signOut()
            return
        }
        let result: RefreshResult
        if let inFlight = refreshTask, refreshTaskGeneration == sessionGeneration {
            result = await inFlight.value
        } else {
            result = await runRefresh()
        }
        switch result {
        case .ok(let set) where set.accessToken != refused:
            break             // the reconnect loop re-registers with the fresh token
        case .ok, .rejected:
            await signOut()   // same/refused token — the session is dead server-side
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
