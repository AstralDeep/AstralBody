import AstralCore
// Feature 051 — the watch app's brain: device-login lifecycle (start → QR →
// poll → tokens, auto-rotate before expiry), broker-based refresh, WS session
// with the `watch` device profile, transcript state, and speech coordination.
import Foundation
import SwiftUI

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
    var transientEntries: [Entry] = []
    var transientCanvas: [AstralComponent]?
    var statusText: String?
    var errorBanner: String?
    var connected = false
    var accountName = ""
    var pendingDictation = ""
    var operationStatuses: [String: OperationStatus] = [:]
    var agentLifecycles: [String: AgentLifecycle] = [:]
    var localOperationSubmissions: [String: LocalOperationSubmission] = [:]

    var visibleEntries: [Entry] { entries + transientEntries }
    var visibleCanvas: [AstralComponent] { transientCanvas ?? canvas }
    var pendingSurfaceRequestGenerations: Set<String> {
        Set(
            localOperationSubmissions.values.compactMap { submission in
                submission.chatId == nil ? submission.requestGeneration : nil
            })
    }
    var pendingChatRequestGenerations: Set<String> {
        Set(
            localOperationSubmissions.values.compactMap { submission in
                submission.chatId == activeChatId ? submission.requestGeneration : nil
            })
    }
    var rootStatusText: String? {
        if let statusText, !statusText.isEmpty { return statusText }
        if let operation = operationStatuses.values.max(by: {
            ($0.updatedAt, $0.sequence) < ($1.updatedAt, $1.sequence)
        }) {
            return operation.error.objectValue?["message"]?.stringValue ?? operation.label
        }
        if let lifecycle = agentLifecycles.values.max(by: {
            ($0.lifecycleGeneration, $0.stateRevision)
                < ($1.lifecycleGeneration, $1.stateRevision)
        }) {
            return "\(lifecycle.agentId): \(lifecycle.label)"
        }
        return nil
    }

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
    @ObservationIgnored var activeChatId: String?
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
    @ObservationIgnored private var conversationResumeStore: ConversationResumeStore
    @ObservationIgnored private var conversationAccount: ConversationAccount?
    @ObservationIgnored private var continuity = ConversationContinuityReducer()
    @ObservationIgnored private var pendingCommitRequestGeneration: String?
    @ObservationIgnored private var seqState: [String: Int] = [:]
    @ObservationIgnored private var statusLifecycle = StatusLifecycleReducer()

    /// Test seam: observes the exact frame before it reaches the socket.
    @ObservationIgnored var outboundTap: ((String) -> Void)?

    var deviceLogin: DeviceLoginClient {
        DeviceLoginClient(serverBase: serverBase)
    }

    var rest: RestClient {
        RestClient(serverBase: serverBase) { [weak self] in
            await self?.freshAccessToken()
        }
    }

    // MARK: lifecycle

    convenience init() {
        self.init(conversationResumeStore: ConversationResumeStore())
    }

    init(conversationResumeStore: ConversationResumeStore) {
        self.conversationResumeStore = conversationResumeStore
    }

    func bindConversationAccount(_ account: ConversationAccount) {
        if conversationAccount != account {
            continuity.clear()
            resetConversationState()
        }
        conversationAccount = account
        activeChatId = conversationResumeStore.load(for: account)?.chatId
    }

    func registrationFrame(token: String, resumed: Bool) -> String {
        let connection = UUID().uuidString.lowercased()
        guard beginConversationConnection(connection) else { return "{}" }
        var resume: ConversationResumeRegistration?
        if let account = conversationAccount,
            let chatId = conversationResumeStore.load(for: account)?.chatId
        {
            guard conversationResumeStore.save(chatId: chatId, for: account) else {
                return "{}"
            }
            activeChatId = chatId
            let request = UUID().uuidString.lowercased()
            if openConversationRequest(
                chatId: chatId,
                requestGeneration: request,
                purpose: .hydration)
            {
                resume = ConversationResumeRegistration(
                    activeChatId: chatId,
                    requestGeneration: request)
            }
        }
        let (width, height) = viewport
        return Outbound.registerUI(
            token: token,
            sessionId: activeChatId,
            device: .watch(viewportWidth: width, viewportHeight: height),
            resumed: resumed,
            connectionGeneration: connection,
            resume: resume)
    }

    @discardableResult
    func beginConversationConnection(_ generation: String) -> Bool {
        clearPendingOperationSubmissions()
        transientEntries = []
        transientCanvas = nil
        return continuity.beginConnection(generation)
    }

    @discardableResult
    func openConversationRequest(
        chatId: String,
        requestGeneration: String,
        purpose: ConversationGenerationPurpose
    ) -> Bool {
        let resetRevision =
            continuity.activeChatId != nil
            && continuity.activeChatId != chatId
        guard continuity.selectChat(chatId, resetRevision: resetRevision),
            continuity.openRequest(
                chatId: chatId,
                requestGeneration: requestGeneration,
                purpose: purpose)
        else { return false }
        activeChatId = chatId
        transientEntries = []
        transientCanvas = nil
        return true
    }

    var lastCommittedRenderRevision: UInt64 {
        continuity.lastCommittedRenderRevision
    }

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
                await signOut(revokeRemote: false)  // ends at the QR screen
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
                        return .expired  // rotation fired first
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
                    phase = .loginFailed(
                        reason == "denied_no_access"
                            ? "This account doesn't have access."
                            : "Sign-in was declined.")
                    return
                case .expired:
                    continue  // auto-rotate: fetch a fresh QR
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
        if let account = tokens?.conversationAccount {
            bindConversationAccount(account)
        } else {
            conversationAccount = nil
            continuity.clear()
            resetConversationState()
        }
        phase = .signedIn
        connectWS()
        // Recents load via WatchHomeView's `.task` the moment home appears
        // (it appears on every path into `.signedIn`) — no eager fetch here.
    }

    /// `revokeRemote: false` skips the server-side revocation round trip —
    /// used when the IdP has ALREADY refused the credential (nothing to
    /// revoke, and the call would only delay returning to the QR screen).
    func signOut(revokeRemote: Bool = true) async {
        // Snapshot remote-revocation inputs, then wipe the local session before
        // the first await. A suspended or killed watch app must never relaunch
        // into the account that was just signed out.
        let access = tokens?.accessToken
        let refresh = tokens?.refreshToken
        let logoutClient = RestClient(serverBase: serverBase) { access }
        let socket = ws
        if let account = conversationAccount {
            _ = conversationResumeStore.clear(.signOut, for: account)
        }
        sessionGeneration += 1
        refreshTask?.cancel()
        refreshTask = nil
        wsTask?.cancel()
        wsTask = nil
        ws = nil
        store.wipe()
        tokens = nil
        conversationAccount = nil
        continuity.clear()
        resetConversationState()
        clearPendingOperationSubmissions()
        statusLifecycle.clear()
        operationStatuses = [:]
        agentLifecycles = [:]
        recents = []
        speaker.stop()
        beginDeviceLogin()

        // The local account is already gone; these network operations cannot
        // make the prior Keychain session durable again.
        await socket?.stop()
        if revokeRemote, let refresh {
            _ = try? await logoutClient.logout(
                clientId: AstralConfig.watchClientId, refreshToken: refresh)
        }
    }

    func clearConversationForAccountRemoval() {
        if let account = conversationAccount {
            _ = conversationResumeStore.clear(.accountRemoval, for: account)
        }
        conversationAccount = nil
        continuity.clear()
        resetConversationState()
        clearPendingOperationSubmissions()
        statusLifecycle.clear()
        operationStatuses = [:]
        agentLifecycles = [:]
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
        let resumeState = WatchRegistrationResumeState()
        wsTask = Task {
            let events = await client.events()
            await client.start(
                onConnect: { [weak self] in
                    guard let self else { return nil }
                    guard let token = await self.freshAccessToken() else { return nil }
                    let resumed = await resumeState.consume()
                    return await self.registrationFrame(token: token, resumed: resumed)
                },
                onReplay: { [weak self] replay in
                    guard let self else { return false }
                    return await self.replayQueuedOperation(replay)
                })
            for await event in events {
                await self.handle(event)
            }
        }
    }

    func handle(_ event: WSEvent) async {
        switch event {
        case .connected:
            connected = true
        case .disconnected:
            connected = false
            clearPendingOperationSubmissions()
            transientEntries = []
            transientCanvas = nil
        case .sendDropped:
            errorBanner = "Connection is behind; some input was dropped."
        case .queuedOperationDropped(let replay, let reason):
            localOperationSubmissions.removeValue(forKey: replay.identity.submissionId)
            if localOperationSubmissions.isEmpty && statusText == "Submitting…" {
                statusText = nil
            }
            errorBanner = "Not sent: \(replay.action) (\(reason))"
        case .sendRejected(let action):
            clearPendingOperationSubmissions()
            errorBanner = "Not sent: \(action) (invalid queued identity)"
        case .frame(let frame):
            handleFrame(frame)
        }
    }

    func handleFrame(_ frame: InboundFrame) {
        // Dispositions: ClientDispositions.watch — unlisted/ignored frames
        // fall through the default silently (FR-003).
        if continuity.connectionGeneration != nil,
            ["ui_render", "ui_update", "ui_upsert", "ui_append", "ui_stream_data"]
                .contains(frame.name)
        {
            reduceTransient(frame)
            return
        }
        switch frame.name {
        case "conversation_snapshot":
            reduceConversationSnapshot(frame)
        case "conversation_commit_ready":
            if let ready = ConversationCommitReady(frame: frame), continuity.accept(ready) {
                transientEntries = []
                transientCanvas = nil
            }
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
        case "operation_status":
            reduceOperationStatus(frame)
        case "agent_lifecycle":
            reduceAgentLifecycle(frame)
        case "user_message_acked":
            if let chatId = nestedChatId(frame) { adoptChat(chatId) }
            statusText = "Thinking…"
        case "chat_created":
            // Adopt the server-issued chat id; the transcript the user is
            // looking at (their just-sent bubble) must NOT be wiped.
            if let chatId = nestedChatId(frame) { adoptChat(chatId) }
        case "chat_loaded":
            if continuity.connectionGeneration == nil {
                reduceChatLoaded(frame)
            }
        case "chat_deleted":
            if let chatId = nestedChatId(frame) { clearConfirmedDeletion(chatId) }
        case "error":
            if reduceAdmissionRefusal(frame) { return }
            fallthrough
        case "stream_error":
            errorBanner = frame.errorMessage
            statusText = nil
            transientEntries = []
            transientCanvas = nil
            let code = frame.payload["code"]?.stringValue
            if code == "chat_not_found" || code == "conversation_not_found" {
                if let chatId = nestedChatId(frame) ?? activeChatId {
                    clearConfirmedDeletion(chatId)
                    errorBanner = frame.errorMessage
                }
            }
        case "notification":
            // 055 background-task continuity (audit item 7): a completion that
            // happened elsewhere reaches the wrist as a brief status line and
            // is spoken through the same TTS path as delivery speech.
            let titled = [frame.payload["title"]?.stringValue, frame.payload["body"]?.stringValue]
                .compactMap { $0?.isEmpty == false ? $0 : nil }.joined(separator: ": ")
            let message = titled.isEmpty ? (frame.payload["message"]?.stringValue ?? "") : titled
            guard !message.isEmpty else { return }
            statusText = message
            speaker.speak(AstralSpeech(ssml: "", text: message))
            Task { [weak self] in
                try? await Task.sleep(nanoseconds: 8_000_000_000)
                guard let self, self.statusText == message else { return }
                self.statusText = nil  // brief: clear unless something replaced it
            }
        case "auth_required":
            Task { await self.handleAuthRequired() }
        default:
            break
        }
    }

    private func reduceOperationStatus(_ frame: InboundFrame) {
        guard let status = OperationStatus(frame: frame),
            statusLifecycle.accept(
                operation: status,
                connectionGeneration: continuity.connectionGeneration,
                conversationRequestGeneration: continuity.requestGeneration,
                activeChatId: activeChatId,
                pendingChatRequestGenerations: pendingChatRequestGenerations,
                pendingSurfaceRequestGenerations: pendingSurfaceRequestGenerations)
        else { return }
        operationStatuses = statusLifecycle.operations
        statusText = status.error.objectValue?["message"]?.stringValue ?? status.label
        if status.terminal {
            clearLocalOperationSubmission(requestGeneration: status.requestGeneration)
        }
        if status.terminal && ["failed", "cancelled", "retryable"].contains(status.state) {
            transientEntries = []
            transientCanvas = nil
        }
    }

    private func reduceAgentLifecycle(_ frame: InboundFrame) {
        guard let lifecycle = AgentLifecycle(frame: frame),
            statusLifecycle.accept(lifecycle: lifecycle)
        else { return }
        agentLifecycles = statusLifecycle.agents
        let message = "\(lifecycle.agentId): \(lifecycle.label)"
        statusText = message
        if lifecycle.state == "failed" {
            errorBanner = message
        }
    }

    @discardableResult
    private func reduceAdmissionRefusal(_ frame: InboundFrame) -> Bool {
        guard let refusal = AdmissionRefusal(frame: frame),
            localOperationSubmissions.removeValue(forKey: refusal.submissionId) != nil
        else { return false }
        statusText = refusal.message
        errorBanner = refusal.message
        return true
    }

    private func reduceConversationSnapshot(_ frame: InboundFrame) {
        guard let snapshot = ConversationSnapshot(frame: frame),
            continuity.apply(snapshot) == .applied
        else { return }
        if let account = conversationAccount {
            _ = conversationResumeStore.save(chatId: snapshot.chatId, for: account)
        }

        var restored: [Entry] = []
        for message in snapshot.messages {
            if message.role == "user" {
                restored.append(
                    .user(
                        id: message.messageId,
                        text: message.visibleText,
                        attachments: message.attachmentNames))
                continue
            }
            let narrative = message.visibleText
            if !narrative.isEmpty {
                restored.append(.status(id: message.messageId, text: narrative))
            }
            if !message.components.isEmpty {
                restored.append(
                    .turn(
                        id: "\(message.messageId)-components",
                        components: message.components))
            }
        }

        activeChatId = snapshot.chatId
        entries = restored
        canvas = snapshot.canvasComponents
        transientEntries = []
        transientCanvas = nil
        statusText = nil
        pendingCommitRequestGeneration = nil
    }

    private func reduceTransient(_ frame: InboundFrame) {
        guard continuity.acceptTransient(frame) else { return }
        switch frame.name {
        case "ui_render", "ui_update":
            let components = frame.renderComponents
            if frame.renderTarget == "chat" {
                let pendingUsers = transientEntries.filter {
                    if case .user = $0 { return true }
                    return false
                }
                let response: [Entry] =
                    components.isEmpty
                    ? []
                    : [
                        .turn(
                            id: "preview-\(frame.payload["frame_sequence"]?.numberValue ?? 0)",
                            components: components)
                    ]
                transientEntries = pendingUsers + response
            } else {
                transientCanvas = components
            }
            speaker.speak(frame.speech)
        case "ui_append":
            let components = frame.renderComponents
            if frame.renderTarget == "chat" {
                if !components.isEmpty {
                    transientEntries.append(
                        .turn(
                            id: "preview-\(frame.payload["frame_sequence"]?.numberValue ?? 0)",
                            components: components))
                }
            } else {
                transientCanvas = (transientCanvas ?? canvas) + components
            }
            speaker.speak(frame.speech)
        case "ui_upsert":
            transientCanvas = Canvas.apply(transientCanvas ?? canvas, frame.upsertOps)
            speaker.speak(frame.speech)
        case "ui_stream_data":
            transientCanvas = Canvas.apply(
                transientCanvas ?? canvas,
                streamFrameToOps(frame, activeChat: activeChatId, seqState: &seqState))
        default:
            break
        }
    }

    private func nestedChatId(_ frame: InboundFrame) -> String? {
        frame.payload["payload"]?["chat_id"]?.stringValue
            ?? frame.payload["chat_id"]?.stringValue
    }

    private func adoptChat(_ chatId: String) {
        if let account = conversationAccount {
            _ = conversationResumeStore.save(chatId: chatId, for: account)
        }
        activeChatId = chatId
        guard let request = pendingCommitRequestGeneration else { return }
        if openConversationRequest(
            chatId: chatId,
            requestGeneration: request,
            purpose: .commit)
        {
            pendingCommitRequestGeneration = nil
        }
    }

    private func clearConfirmedDeletion(_ chatId: String) {
        if let account = conversationAccount {
            _ = conversationResumeStore.clear(
                .confirmedDeletion,
                for: account,
                chatId: chatId)
        }
        guard activeChatId == chatId else { return }
        clearContinuityChatKeepingConnection()
        resetConversationState()
    }

    private func clearContinuityChatKeepingConnection() {
        let connection = continuity.connectionGeneration
        continuity.clear()
        if let connection {
            _ = continuity.beginConnection(connection)
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
            break  // the reconnect loop re-registers with the fresh token
        case .ok, .rejected:
            await signOut()  // same/refused token — the session is dead server-side
        case .transient:
            break  // offline blip; keep the session and retry
        }
    }

    /// Re-hydrate a loaded transcript: user text with read-only attachment
    /// name-chips (FR-033/T049 — the watch has no upload affordance) and
    /// assistant narrative. Rich canvas content arrives right after as a
    /// speech-free `ui_render` (the server re-hydrates the workspace).
    private func reduceChatLoaded(_ frame: InboundFrame) {
        let chat = frame.payload["chat"]
        activeChatId = chat?["id"]?.stringValue ?? activeChatId
        if let account = conversationAccount, let activeChatId {
            _ = conversationResumeStore.save(chatId: activeChatId, for: account)
        }
        canvas = []  // the server re-hydrates the workspace via ui_render next
        let messages = chat?["messages"]?.arrayValue ?? chat?["history"]?.arrayValue ?? []
        var loaded: [Entry] = []
        for (index, message) in messages.enumerated() {
            let role =
                message["role"]?.stringValue
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

    private func resetConversationState() {
        entries = []
        canvas = []
        transientEntries = []
        transientCanvas = nil
        activeChatId = nil
        statusText = nil
        errorBanner = nil
        pendingCommitRequestGeneration = nil
        seqState.removeAll()
    }

    private func beginLocalOperationSubmission(
        identity: ClientOperationIdentity,
        action: String,
        surface: String,
        chatId: String?
    ) {
        guard let connectionGeneration = continuity.connectionGeneration,
            let submission = LocalOperationSubmission(
                identity: identity,
                action: action,
                surface: surface,
                chatId: chatId,
                connectionGeneration: connectionGeneration)
        else { return }
        localOperationSubmissions[submission.submissionId] = submission
        statusText = submission.label
    }

    /// Restore the exact client identity and current connection fence before
    /// shared transport replays retained bytes.
    @discardableResult
    func replayQueuedOperation(_ replay: QueuedOperationReplay) -> Bool {
        guard let connectionGeneration = continuity.connectionGeneration else { return false }
        if let purpose = replay.conversationPurpose {
            if let chatId = replay.chatId {
                guard
                    openConversationRequest(
                        chatId: chatId,
                        requestGeneration: replay.identity.requestGeneration,
                        purpose: purpose)
                else { return false }
            } else if purpose == .commit {
                pendingCommitRequestGeneration = replay.identity.requestGeneration
            } else {
                return false
            }
        }
        guard
            let submission = LocalOperationSubmission(
                identity: replay.identity,
                action: replay.action,
                surface: replay.surface,
                chatId: replay.chatId,
                connectionGeneration: connectionGeneration)
        else { return false }
        localOperationSubmissions[submission.submissionId] = submission
        statusText = submission.label
        return true
    }

    private func clearLocalOperationSubmission(requestGeneration: String) {
        localOperationSubmissions = localOperationSubmissions.filter {
            $0.value.requestGeneration != requestGeneration
        }
    }

    private func clearPendingOperationSubmissions() {
        let wasSubmitting = statusText == "Submitting…"
        localOperationSubmissions.removeAll()
        if wasSubmitting { statusText = nil }
    }

    private func rawSend(_ frame: String) {
        outboundTap?(frame)
        Task { await ws?.send(frame) }
    }

    func newConversation() {
        if let account = conversationAccount {
            _ = conversationResumeStore.clear(.newChat, for: account)
        }
        clearContinuityChatKeepingConnection()
        resetConversationState()
        let identity = ClientOperationIdentity.fresh()
        beginLocalOperationSubmission(
            identity: identity,
            action: "new_chat",
            surface: "operation",
            chatId: nil)
        rawSend(
            Outbound.newChat(
                sessionId: nil,
                submissionId: identity.submissionId,
                requestGeneration: identity.requestGeneration))
    }

    func openChat(_ chat: ChatSummary) {
        if let account = conversationAccount {
            guard conversationResumeStore.save(chatId: chat.id, for: account) else { return }
        }
        activeChatId = chat.id
        let identity = ClientOperationIdentity.fresh()
        let request = identity.requestGeneration
        if continuity.connectionGeneration != nil {
            guard
                openConversationRequest(
                    chatId: chat.id,
                    requestGeneration: request,
                    purpose: .hydration)
            else { return }
        }
        beginLocalOperationSubmission(
            identity: identity,
            action: "load_chat",
            surface: "chat",
            chatId: chat.id)
        rawSend(
            Outbound.loadChat(
                sessionId: chat.id,
                chatId: chat.id,
                submissionId: identity.submissionId,
                requestGeneration: request))
    }

    /// Dictated text goes through the STANDARD chat path (FR-029) after the
    /// user confirms it (edge case: garbled dictation never auto-sends).
    func sendPending() {
        let text = pendingDictation.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        let identity = ClientOperationIdentity.fresh()
        let request = identity.requestGeneration
        if continuity.connectionGeneration != nil {
            if let chatId = activeChatId {
                guard
                    openConversationRequest(
                        chatId: chatId,
                        requestGeneration: request,
                        purpose: .commit)
                else { return }
            } else {
                pendingCommitRequestGeneration = request
            }
        }
        pendingDictation = ""
        let entry = Entry.user(
            id: "pending-user-\(UUID().uuidString.lowercased())",
            text: text,
            attachments: [])
        if continuity.connectionGeneration == nil {
            entries.append(entry)
        } else {
            transientEntries.append(entry)
        }
        beginLocalOperationSubmission(
            identity: identity,
            action: "chat_message",
            surface: "chat",
            chatId: activeChatId)
        rawSend(
            Outbound.chatMessage(
                text,
                sessionId: activeChatId,
                submissionId: identity.submissionId,
                requestGeneration: request))
    }
}

private actor WatchRegistrationResumeState {
    private var next = false

    func consume() -> Bool {
        let value = next
        next = true
        return value
    }
}
