// Feature 051 — the iOS/macOS app model: a faithful port of the Android
// `AppViewModel`. System-browser PKCE sign-in, WS session with the ios/macos
// device profile, and the full server-driven reduce: the "commit-on-done"
// canvas lifecycle (a replacing turn buffers ops into `pendingCanvas` and swaps
// them in on `chat_status done`, pushing the prior canvas onto the timeline),
// server-owned chrome (`chrome_menu`/`chrome_surface`), agents/audit/history
// surfaces, streaming nodes, attachments, and live theming.
import Foundation
import SwiftUI
import AuthenticationServices
import UniformTypeIdentifiers
import AstralCore
#if os(iOS)
import UIKit
#else
import AppKit
#endif

@MainActor
@Observable
final class AppModel: NSObject {

    enum Screen: Equatable { case chat, agents, history, audit, surface }

    struct ChatTurn: Identifiable, Equatable {
        let id: String
        let role: String   // "user" | "assistant" | "reasoning"
        let text: String
    }

    struct StagedAttachment: Identifiable, Equatable {
        let uid: Int
        let filename: String
        var category: String
        var attachmentId: String?
        var state: String   // "uploading" | "ready" | "failed"
        var note: String?
        var id: Int { uid }
    }

    struct CanvasSnapshot: Identifiable, Equatable {
        let id = UUID()
        let label: String
        let components: [AstralComponent]
    }

    struct SurfaceContent: Equatable {
        let surfaceKey: String
        let title: String
        let components: [AstralComponent]
    }

    // MARK: configuration

    // UserDefaults-backed (the former @AppStorage pair — property wrappers
    // aren't allowed on @Observable stored properties). Seeded in init.
    var serverBaseText: String {
        didSet {
            UserDefaults.standard.set(serverBaseText, forKey: "serverBase")
            // Feature 053 — mirror the endpoint to the paired watch. Best-effort:
            // the watch runs independently and falls back to its build-time default.
            #if os(iOS)
            WatchOverrideSync.shared.push(serverBaseText)
            #endif
        }
    }
    var authorityText: String {
        didSet { UserDefaults.standard.set(authorityText, forKey: "authority") }
    }

    #if os(macOS)
    let clientId = AstralConfig.macosClientId
    #else
    let clientId = AstralConfig.iosClientId
    #endif
    let redirectURI = AstralConfig.redirectURI

    // MARK: observable state (mirrors Android UiState)

    var signedIn = false
    var accountName = ""
    var connected = false
    var everConnected = false
    var screen: Screen = .chat
    var activeChatId: String?

    var turns: [ChatTurn] = []
    var canvas: [AstralComponent] = []
    var pendingCanvas: [AstralComponent] = []
    var turnActive = false
    var pendingReplace = false
    var canvasLabel = ""
    var pendingLabel = ""
    var canvasHistory: [CanvasSnapshot] = []
    var viewingIndex: Int?

    var staged: [StagedAttachment] = []
    var statusText: String?
    var errorBanner: String?
    var bannerIsError = true
    var stepTrail: [String] = []
    var asyncDetached = false

    var agents: [Agent] = []
    var history: [ChatSummary] = []
    var audit: [AuditEvent] = []
    var agentsLoading = false
    var historyLoading = false
    var auditLoading = false

    var chromeMenu: ChromeMenuModel?
    var pendingSurfaceKey = ""
    var pendingSurfaceParams: JSONValue = .object([:])
    var pendingSurface: SurfaceContent?
    /// 054 first-run gate: the server pinned the current surface
    /// (`chrome_surface` `mode:"mandatory"`) — navigation is suppressed until
    /// the server replaces or closes it. Sign-out stays available (FR-013).
    var mandatorySurface = false
    var timelineReadOnly = false

    var signInError: String?

    let themeStore = ThemeStore()

    // Derived
    var visibleCanvas: [AstralComponent] {
        if let idx = viewingIndex, canvasHistory.indices.contains(idx) {
            return canvasHistory[idx].components
        }
        return canvas
    }
    var isViewingHistory: Bool { viewingIndex != nil }
    var showSkeleton: Bool { pendingReplace && viewingIndex == nil }
    var mutationsLocked: Bool { timelineReadOnly }

    // MARK: session plumbing (never read by views — not observation-tracked)

    private let store: TokenStorage = {
        #if canImport(Security)
        KeychainTokenStore()
        #else
        InMemoryTokenStore()
        #endif
    }()
    @ObservationIgnored private var tokens: TokenSet?
    @ObservationIgnored private var ws: WSClient?
    @ObservationIgnored private var wsTask: Task<Void, Never>?
    @ObservationIgnored private var authSession: ASWebAuthenticationSession?
    @ObservationIgnored private var seqState: [String: Int] = [:]
    @ObservationIgnored private var attachSeq = 0
    /// Single-flight refresh (see `refreshOutcome`) + a session generation so
    /// a refresh resolving after sign-out can never resurrect wiped
    /// credentials or be joined by the next account's session.
    @ObservationIgnored private var refreshTask: Task<RefreshResult, Never>?
    @ObservationIgnored private var refreshTaskGeneration = -1
    @ObservationIgnored private var sessionGeneration = 0

    private let docMarker = "full write-up is on the canvas"
    private let maxTrail = 20
    private let timelineMutations: Set<String> = ["chat_message", "component_action", "table_paginate", "save_theme"]

    var serverBase: URL {
        URL(string: serverBaseText) ?? URL(string: AstralConfig.serverBaseURL)!
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

    // MARK: lifecycle

    override init() {
        let defaults = UserDefaults.standard
        var storedBase = defaults.string(forKey: "serverBase") ?? ""
        var storedAuthority = defaults.string(forKey: "authority") ?? ""
        // The override keys hold USER edits only. Earlier builds seeded the
        // build-time DEFAULT into them on first launch, freezing the endpoint
        // for the whole install base — a stored value equal to the current
        // default is that seed (or a no-op edit), not an override: clear it so
        // a future xcconfig repoint reaches existing installs and their
        // paired watches.
        if storedBase == AstralConfig.serverBaseURL {
            defaults.removeObject(forKey: "serverBase")
            storedBase = ""
        }
        if storedAuthority == AstralConfig.keycloakAuthority {
            defaults.removeObject(forKey: "authority")
            storedAuthority = ""
        }
        serverBaseText = storedBase.isEmpty ? AstralConfig.serverBaseURL : storedBase
        authorityText = storedAuthority.isEmpty ? AstralConfig.keycloakAuthority : storedAuthority
        super.init()
        #if os(iOS)
        WatchOverrideSync.shared.activate()
        if !storedBase.isEmpty { WatchOverrideSync.shared.push(serverBaseText) }
        #endif
    }

    func bootstrap() async {
        guard let stored = store.load() else { return }
        tokens = stored.tokenSet
        // Enter the signed-in shell IMMEDIATELY: the WS dial starts now, and
        // the register frame waits on the (single-flight) token refresh
        // inside onConnect — so the IdP round trip and the socket handshake
        // run concurrently instead of back-to-back behind a blank sign-in
        // screen. Transient (offline) keeps the stored credentials: the
        // reconnect strip shows and the WS backoff loop registers once the
        // network returns. Credentials are wiped ONLY on a definitive IdP
        // rejection — never for being offline at launch.
        enterSignedIn(resumedSession: true)
        if case .rejected = await refreshOutcome() {
            await signOut(revokeRemote: false)   // the IdP already refused the credential
        }
    }

    // MARK: sign-in

    func signIn() {
        guard let oidc else {
            signInError = "Set the Keycloak realm URL first."
            return
        }
        signInError = nil
        let verifier = PKCE.makeVerifier()
        let state = PKCE.makeVerifier()
        let url = oidc.authorizeURL(state: state, challenge: PKCE.challenge(for: verifier))

        let session = ASWebAuthenticationSession(url: url, callbackURLScheme: AstralConfig.redirectScheme) {
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
            enterSignedIn(resumedSession: false)
        } catch {
            signInError = error.localizedDescription
        }
    }

    /// Ensure a live access token, classifying failures so callers can tell
    /// "the IdP revoked us" (wipe + interactive sign-in) from "we're offline"
    /// (keep credentials, retry later). SINGLE-FLIGHT: concurrent callers
    /// (the WS onConnect, REST tokenProvider, bootstrap validation) join one
    /// in-flight IdP round trip — two parallel grants with the same rotating
    /// refresh token can revoke the whole session at the IdP.
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
        guard let refresh = tokens?.refreshToken, let oidc else {
            return .rejected("no refresh token")
        }
        let generation = sessionGeneration
        let attempt = Task { await RefreshStrategy.direct(oidc).attempt(refreshToken: refresh) }
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

    /// The server refused our token. `refreshOutcome` short-circuits when the
    /// token isn't near expiry, which would reconnect with the SAME rejected
    /// credential forever — so join the in-flight refresh if one is running,
    /// otherwise FORCE a real IdP refresh; reconnect only if it produced a
    /// different token, else the session is dead server-side (revoked / hard
    /// cap) and we go to interactive sign-in.
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
            connectWS(resumed: true)
        case .ok, .rejected:
            await signOut()   // same token — the server will just refuse it again
        case .transient:
            break             // offline blip; the WS backoff loop keeps retrying
        }
    }

    private func enterSignedIn(resumedSession: Bool) {
        accountName = tokens?.displayName ?? ""
        signedIn = true
        connectWS(resumed: resumedSession)
    }

    /// `revokeRemote: false` skips the server-side revocation round trip —
    /// used when the IdP has ALREADY refused the credential (nothing to
    /// revoke, and the call would only delay landing on the sign-in screen).
    func signOut(revokeRemote: Bool = true) async {
        if revokeRemote, let refresh = tokens?.refreshToken {
            _ = try? await rest.logout(clientId: clientId, refreshToken: refresh)
        }
        sessionGeneration += 1
        refreshTask = nil
        wsTask?.cancel()
        await ws?.stop()
        ws = nil
        store.wipe()
        tokens = nil
        signedIn = false
        resetChatState()
        chromeMenu = nil
        mandatorySurface = false   // the next session re-gates server-side
        agents = []; history = []; audit = []
    }

    // MARK: WS

    @ObservationIgnored private var lastReportedViewport: (width: Int, height: Int)?

    private var device: DeviceDescriptor {
        #if os(macOS)
        let (w, h) = lastReportedViewport ?? (1280, 800)
        return .macos(viewportWidth: w, viewportHeight: h)
        #else
        let size = UIScreen.main.bounds.size
        let (w, h) = lastReportedViewport ?? (Int(size.width), Int(size.height))
        return .ios(viewportWidth: w, viewportHeight: h)
        #endif
    }

    /// FR-002/T030: report viewport changes (rotation, iPad Split View /
    /// Slide Over, macOS window resize) through the existing `update_device`
    /// action so ROTE re-derives the layout — the Android fold/rotation twin.
    func viewportChanged(width: Int, height: Int) {
        guard width > 0, height > 0 else { return }
        if let last = lastReportedViewport, last == (width, height) { return }
        let isFirst = lastReportedViewport == nil
        lastReportedViewport = (width, height)
        // The initial size rides on register_ui; only CHANGES re-report.
        guard signedIn, !isFirst else { return }
        rawSend(Outbound.updateDevice(sessionId: activeChatId ?? "", device: device))
    }

    private func connectWS(resumed initialResumed: Bool) {
        wsTask?.cancel()
        if let previous = ws {
            Task { await previous.stop() }   // never leak a live socket loop
        }
        let client = WSClient(url: rest.webSocketURL)
        ws = client
        var resumed = initialResumed
        wsTask = Task {
            let events = await client.events()
            await client.start(onConnect: { [weak self] in
                guard let self else { return nil }
                guard let token = await self.freshAccessToken() else { return nil }
                let frame = Outbound.registerUI(
                    token: token, sessionId: await self.activeChatId,
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
        case .connected:
            connected = true
            everConnected = true
        case .disconnected:
            connected = false
            turnActive = false
            pendingReplace = false
            pendingCanvas = []
            agentsLoading = false; historyLoading = false; auditLoading = false
        case .sendDropped(let total):
            bannerIsError = true
            errorBanner = "Not sent while offline (queue full: \(total) dropped)"
        case .frame(let frame):
            handleFrame(frame)
        }
    }

    // MARK: reduce (port of AppViewModel.reduce)

    /// Internal (not private) so XCTests can drive frames through the reducer.
    func handleFrame(_ frame: InboundFrame) {
        switch frame.name {
        case "ui_render":
            reduceUiRender(frame)
        case "ui_upsert":
            reduceUiUpsert(frame)
        case "chat_created":
            activeChatId = nestedChatId(frame) ?? activeChatId
        case "user_message_acked":
            activeChatId = nestedChatId(frame) ?? activeChatId
            turnActive = true
            pendingReplace = true
            pendingCanvas = []
        case "chat_loaded":
            reduceChatLoaded(frame)
        case "chat_status":
            reduceStatus(frame)
        case "agent_list":
            agents = Agent.list(from: frame.payload["agents"])
            agentsLoading = false
        case "history_list":
            history = (frame.payload["chats"]?.arrayValue ?? []).compactMap { ChatSummary(json: $0) }
            historyLoading = false
        case "ui_stream_data", "stream_data":
            applyCanvasOps(streamFrameToOps(frame, activeChat: activeChatId, seqState: &seqState))
        case "stream_subscribed":
            applyCanvasOps(subscribeAckOps(frame))
        case "stream_error":
            applyCanvasOps(streamErrorOps(frame))
        case "chrome_menu":
            chromeMenu = ChromeMenuModel.fromJSON(frame.payload["model"])
        case "chrome_surface":
            reduceChromeSurface(frame)
        case "user_preferences":
            themeStore.applyPreferences(frame.payload)
        case "workspace_timeline_mode":
            timelineReadOnly = frame.payload["active"]?.boolValue ?? frame.payload["on"]?.boolValue ?? false
        case "error":
            reduceError(frame)
        case "chat_step":
            let step = frame.payload["step"]
            let name = step?["name"]?.stringValue ?? step?["kind"]?.stringValue
            stepTrail = trailUpsert(stepTrail, stepLine(name: name, status: step?["status"]?.stringValue))
        case "tool_progress":
            let head = [frame.payload["tool_name"]?.stringValue, frame.payload["message"]?.stringValue]
                .compactMap { $0 }.joined(separator: ": ")
            // The wire `percentage` is a JSON number (Optional[int] server-side).
            // Bounds-checked: Int(Double) traps on out-of-range values, and no
            // inbound frame may crash the client (FR-003).
            let pct = frame.payload["percentage"]
                .flatMap { value -> String? in
                    if let s = value.stringValue { return s }
                    guard let n = value.numberValue, n.isFinite, n >= 0, n <= 999
                    else { return nil }
                    return String(Int(n))
                }
                .map { " (\($0)%)" } ?? ""
            let label = (head + pct).isEmpty ? "Working…" : head + pct
            stepTrail = trailUpsert(stepTrail, "• \(label)")
        case "task_started":
            statusText = "Working in the background…"
            asyncDetached = true
        case "task_completed":
            commitTurn()
            bannerIsError = false
            errorBanner = "Background task finished"
        case "notification":
            let text = [frame.payload["title"]?.stringValue, frame.payload["body"]?.stringValue]
                .compactMap { $0?.isEmpty == false ? $0 : nil }.joined(separator: ": ")
            if !text.isEmpty {
                bannerIsError = frame.payload["level"]?.stringValue == "error"
                errorBanner = text
            }
        // 055 (US3): the eight workspace verb acks, promoted ignored → handled
        // (wire-contract §4). The server's follow-up ui_upsert/ui_render
        // fan-outs stay authoritative; these give the issuing socket immediate
        // feedback without waiting on them.
        case "component_saved":
            let title = frame.payload["component"]?["title"]?.stringValue ?? ""
            bannerIsError = false
            errorBanner = title.isEmpty ? "Component saved" : "Saved \(title)"
        case "component_save_error":
            bannerIsError = true
            errorBanner = frame.payload["error"]?.stringValue ?? "Couldn't save component"
        case "component_deleted":
            if let cid = frame.payload["component_id"]?.stringValue, !cid.isEmpty {
                applyCanvasOps([UpsertOp(op: "remove", componentId: cid, component: nil)])
            }
        case "combine_status":
            statusText = frame.payload["message"]?.stringValue ?? frame.payload["status"]?.stringValue
        case "combine_error":
            statusText = nil
            bannerIsError = true
            errorBanner = frame.payload["error"]?.stringValue ?? "Couldn't combine components"
        case "components_combined", "components_condensed":
            statusText = nil
            applyCanvasOps(replacementOps(frame))
        case "saved_components_list":
            // Accepted ack; there is no native saved-components surface to
            // refresh (browsing rides the server-driven chrome surface) — a
            // future surface would consume `payload["components"]` here.
            break
        case "auth_required":
            Task { await self.handleAuthRequired() }
        default:
            break
        }
    }

    private func nestedChatId(_ frame: InboundFrame) -> String? {
        frame.payload["payload"]?["chat_id"]?.stringValue ?? frame.payload["chat_id"]?.stringValue
    }

    private func reduceUiRender(_ frame: InboundFrame) {
        let comps = frame.renderComponents
        if frame.renderTarget == "chat" {
            let text = flattenText(comps)
            if text.isEmpty || text.range(of: docMarker, options: .caseInsensitive) != nil { return }
            appendTurn(role: "assistant", text: text)
            return
        }
        let reasoning = comps.filter { isReasoning($0) }
        let canvasComps = comps.filter { !isReasoning($0) && !isDocCard($0.componentId) && !isSkeleton($0) }
        for r in reasoning {
            let text = flattenText(r.children).isEmpty ? flattenText([r]) : flattenText(r.children)
            if !text.isEmpty { appendTurn(role: "reasoning", text: text) }
        }
        if pendingReplace {
            if canvasComps.isEmpty { return }
            pendingCanvas = Canvas.apply(pendingCanvas, renderToOps(canvasComps))
        } else {
            canvas = canvasComps
            pendingCanvas = []
        }
    }

    private func reduceUiUpsert(_ frame: InboundFrame) {
        if let chatId = frame.chatId, let active = activeChatId, chatId != active { return }
        let ops = frame.upsertOps
        for op in ops where op.op != "remove" && isDocCard(op.componentId) {
            if let comp = op.component {
                let text = flattenText([comp])
                if !text.isEmpty { appendTurn(role: "assistant", text: text) }
            }
        }
        let canvasOps = ops.filter { !isDocCard($0.componentId) && !isSkeleton($0.component) }
        if canvasOps.isEmpty { return }
        if pendingReplace {
            pendingCanvas = Canvas.apply(pendingCanvas, canvasOps)
        } else {
            canvas = Canvas.apply(canvas, canvasOps)
        }
    }

    private func reduceChatLoaded(_ frame: InboundFrame) {
        let chat = frame.payload["chat"]
        activeChatId = chat?["id"]?.stringValue ?? activeChatId
        let messages = chat?["messages"]?.arrayValue ?? chat?["history"]?.arrayValue ?? []
        turns = messages.enumerated().map { index, m in
            let content = m["content"]?.stringValue ?? m["text"]?.stringValue ?? ""
            let role = m["role"]?.stringValue ?? (m["is_user"]?.boolValue == true ? "user" : "assistant")
            // Index-keyed ids: identical repeated messages must not collide
            // (duplicate Identifiable ids are undefined behavior in ForEach).
            return ChatTurn(id: "hist-\(index)", role: role, text: content)
        }
        canvas = []; pendingCanvas = []; canvasHistory = []; viewingIndex = nil
        turnActive = false; pendingReplace = false; canvasLabel = ""; pendingLabel = ""
        statusText = nil; stepTrail = []; asyncDetached = false
    }

    private func reduceChromeSurface(_ frame: InboundFrame) {
        let surfaceKey = frame.payload["surface_key"]?.stringValue ?? ""
        let title = frame.payload["title"]?.stringValue ?? ""
        let components = AstralComponent.list(from: frame.payload["components"])
        if surfaceKey.isEmpty && components.isEmpty {
            // The server's blank close instruction also lifts the 054
            // mandatory pin (save success → close, then welcome ui_render).
            mandatorySurface = false
            if screen == .surface {
                screen = .chat
                pendingSurface = nil
                pendingSurfaceKey = ""
                pendingSurfaceParams = .object([:])
            }
            return
        }
        if frame.surfaceMode == "mandatory" {
            // 054 first-run gate: accept the surface even though unsolicited
            // and pin it — goTo/newChat/openSurface and the top bar suppress
            // navigation until the server closes it; sign-out stays (FR-013).
            mandatorySurface = true
            screen = .surface
            pendingSurfaceKey = surfaceKey
            pendingSurfaceParams = .object([:])
            pendingSurface = SurfaceContent(surfaceKey: surfaceKey, title: title, components: components)
            return
        }
        if screen == .surface && pendingSurfaceKey == surfaceKey {
            pendingSurface = SurfaceContent(surfaceKey: surfaceKey, title: title, components: components)
            return
        }
        let text = [title, noticeText(components)].filter { !$0.isEmpty }.joined(separator: ": ")
        if !text.isEmpty {
            bannerIsError = true
            errorBanner = text
        }
    }

    private func reduceError(_ frame: InboundFrame) {
        let code = frame.payload["code"]?.stringValue
        let message = frame.payload["message"]?.stringValue
            ?? frame.payload["payload"]?["message"]?.stringValue ?? "Something went wrong."
        errorBanner = (code != nil && code != "internal") ? "\(message) (\(code!))" : message
        bannerIsError = true
        turnActive = false
        pendingReplace = false
        pendingCanvas = []
        agentsLoading = false; historyLoading = false; auditLoading = false
        statusText = nil
        asyncDetached = false
    }

    private func reduceStatus(_ frame: InboundFrame) {
        let status = frame.payload["status"]?.stringValue
        let message = frame.payload["message"]?.stringValue
        let label = (message?.isEmpty == false) ? message : status
        switch status {
        case "done":
            commitTurn()
        case "thinking", "executing", "fixing", "processing_async":
            turnActive = true
            statusText = label
        default:
            statusText = label
        }
    }

    private func commitTurn() {
        if !pendingReplace {
            turnActive = false; statusText = nil; stepTrail = []; asyncDetached = false
            return
        }
        if pendingCanvas.isEmpty {
            // Text-only turn keeps the canvas — minus any welcome that
            // resurrected mid-turn (055: `wel_` never survives a turn).
            canvas = canvas.dropWelcome()
            turnActive = false; pendingReplace = false; statusText = nil
            stepTrail = []; asyncDetached = false
            return
        }
        // 055: `wel_` identities never enter the timeline; a welcome-only
        // canvas archives nothing.
        let archived = canvas.dropWelcome()
        if !archived.isEmpty {
            let label = canvasLabel.isEmpty ? "Canvas \(canvasHistory.count + 1)" : canvasLabel
            canvasHistory.append(CanvasSnapshot(label: label, components: archived))
        }
        canvas = pendingCanvas
        pendingCanvas = []
        canvasLabel = pendingLabel
        pendingLabel = ""
        turnActive = false; pendingReplace = false; statusText = nil
        stepTrail = []; asyncDetached = false
    }

    private func applyCanvasOps(_ ops: [UpsertOp]) {
        if ops.isEmpty { return }
        if pendingReplace {
            pendingCanvas = Canvas.apply(pendingCanvas, ops)
        } else {
            canvas = Canvas.apply(canvas, ops)
        }
    }

    // MARK: reduce helpers

    private func appendTurn(role: String, text: String) {
        turns.append(ChatTurn(id: "\(role)-\(turns.count)", role: role, text: text))
    }

    private func renderToOps(_ components: [AstralComponent]) -> [UpsertOp] {
        components.enumerated().map { i, c in
            let id = c.componentId ?? "xr-\(c.type)-\(i)"
            return UpsertOp(op: "upsert", componentId: id,
                            component: c.componentId == nil ? c.withComponentId(id) : c)
        }
    }

    /// components_combined / components_condensed → canvas ops: remove the
    /// consumed ids, upsert each carried result. Results are saved-row shapes
    /// (`{id, component_data, …}`); the component dict rides in
    /// `component_data` and may not carry a workspace identity yet (the
    /// server stamps it in the reconcile ui_render that follows), so identity
    /// falls back to the fresh row id.
    private func replacementOps(_ frame: InboundFrame) -> [UpsertOp] {
        let removed = frame.payload["removed_ids"]?.arrayValue?.compactMap { $0.stringValue } ?? []
        var ops: [UpsertOp] = removed.map { UpsertOp(op: "remove", componentId: $0, component: nil) }
        for row in frame.payload["new_components"]?.arrayValue ?? [] {
            guard let comp = row["component_data"].flatMap({ AstralComponent(json: $0) }) else { continue }
            let cid = comp.componentId ?? row["id"]?.stringValue ?? "combined-\(ops.count)"
            ops.append(UpsertOp(op: "upsert", componentId: cid,
                                component: comp.componentId == nil ? comp.withComponentId(cid) : comp))
        }
        return ops
    }

    private func stepLine(name: String?, status: String?) -> String {
        let icon: String
        switch status {
        case "completed": icon = "✓"
        case "errored": icon = "✗"
        default: icon = "•"
        }
        return "\(icon) \(name ?? "step")"
    }

    private func trailKey(_ line: String) -> String {
        let afterSpace = line.contains(" ") ? String(line[line.index(after: line.firstIndex(of: " ")!)...]) : line
        return afterSpace.replacingOccurrences(of: #"\s*\(\d+(\.\d+)?%\)$"#, with: "", options: .regularExpression)
    }

    private func trailUpsert(_ trail: [String], _ line: String) -> [String] {
        let key = trailKey(line)
        var next = trail
        if let idx = trail.lastIndex(where: { trailKey($0) == key }) {
            next[idx] = line
        } else {
            next.append(line)
        }
        return Array(next.suffix(maxTrail))
    }

    private func isReasoning(_ c: AstralComponent) -> Bool {
        c.type.lowercased() == "collapsible" &&
            (c.raw["title"]?.stringValue ?? "").lowercased() == "reasoning"
    }

    private func isDocCard(_ id: String?) -> Bool { id?.hasPrefix("doc_") ?? false }

    private func isSkeleton(_ c: AstralComponent?) -> Bool { c?.type.lowercased() == "skeleton" }

    private func flattenText(_ components: [AstralComponent]) -> String {
        components.map { c in
            let own = c.raw["content"]?.stringValue ?? c.raw["text"]?.stringValue ?? ""
            return (own + "\n" + flattenText(c.children)).trimmingCharacters(in: .whitespacesAndNewlines)
        }.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func noticeText(_ components: [AstralComponent]) -> String {
        components.map { c in
            let own = c.raw["message"]?.stringValue ?? c.raw["content"]?.stringValue
                ?? c.raw["text"]?.stringValue ?? ""
            return (own + "\n" + noticeText(c.children)).trimmingCharacters(in: .whitespacesAndNewlines)
        }.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func parserNote(_ status: String?) -> String? {
        switch status {
        case "preparing": return "preparing reader…"
        case "pending_admin_approval": return "reader pending admin"
        case "unavailable": return "no reader yet"
        default: return nil
        }
    }

    private func resetChatState() {
        activeChatId = nil
        turns = []; canvas = []; pendingCanvas = []; canvasHistory = []
        viewingIndex = nil; turnActive = false; pendingReplace = false
        canvasLabel = ""; pendingLabel = ""; staged = []
        statusText = nil; errorBanner = nil; stepTrail = []; asyncDetached = false
    }

    // MARK: actions

    func dismissBanner() { errorBanner = nil }

    func sendChat(_ text: String) {
        if timelineReadOnly { return }
        let ready = staged.filter { $0.state == "ready" && $0.attachmentId != nil }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty && ready.isEmpty { return }
        let bubble = ready.isEmpty ? text :
            (text + "\n📎 " + ready.map(\.filename).joined(separator: ", ")).trimmingCharacters(in: .whitespaces)
        appendTurn(role: "user", text: bubble)
        turnActive = true
        pendingReplace = true
        pendingCanvas = []
        // 055 uniform rule: purge the ephemeral welcome (`wel_` identities)
        // from the committed canvas at turn start — the server no longer
        // sends the blanking `ui_render []` (wire-contract §1).
        canvas = canvas.dropWelcome()
        pendingLabel = String((text.isEmpty ? (ready.first?.filename ?? "") : text).prefix(80))
        staged = []
        viewingIndex = nil
        statusText = nil
        errorBanner = nil
        stepTrail = []
        asyncDetached = false

        var payload: [String: JSONValue] = ["message": .string(text)]
        if let cid = activeChatId { payload["chat_id"] = .string(cid) }
        if !ready.isEmpty {
            payload["attachments"] = .array(ready.map { att in
                .object(["attachment_id": .string(att.attachmentId!),
                         "filename": .string(att.filename),
                         "category": .string(att.category)])
            })
        }
        rawSend(Outbound.uiEvent(action: "chat_message", sessionId: activeChatId, payload: .object(payload)))
    }

    func sendEvent(_ action: String, _ payload: JSONValue = .object([:])) {
        if action == "attach_existing" {
            if stageExistingAttachment(payload) {
                let filename = payload["filename"]?.stringValue ?? "file"
                screen = .chat
                bannerIsError = false
                errorBanner = "Attached \(filename) — it will be sent with your next message"
            }
            return
        }
        if timelineReadOnly && timelineMutations.contains(action) { return }
        if action == "chat_message" {
            turnActive = true
            pendingReplace = true
            pendingCanvas = []
            canvas = canvas.dropWelcome()   // 055: same turn-start purge as sendChat
            viewingIndex = nil
            errorBanner = nil
            stepTrail = []
            asyncDetached = false
        }
        rawSend(Outbound.uiEvent(action: action, sessionId: activeChatId, payload: payload))
    }

    /// Bridge for the component renderer's `emit(action, payload)` callback.
    func emit(_ action: String, payload: [String: JSONValue] = [:]) {
        sendEvent(action, .object(payload))
    }

    private func rawSend(_ text: String) {
        Task { await ws?.send(text) }
    }

    func newChat() {
        if mandatorySurface { return }   // 054: navigation pinned (sign-out only)
        seqState.removeAll()
        resetChatState()
        screen = .chat
        sendEvent("new_chat")
    }

    func openChat(_ chatId: String) {
        sendEvent("load_chat", .object(["chat_id": .string(chatId)]))
        screen = .chat
        viewingIndex = nil
    }

    /// FR-011: history offers open AND delete (server-side via REST, like the
    /// Android/Windows twins), then refreshes the list.
    func deleteChat(_ chatId: String) {
        history.removeAll { $0.id == chatId }
        if activeChatId == chatId { resetChatState() }
        Task {
            _ = try? await rest.deleteChat(id: chatId)
            sendEvent("get_history")
        }
    }

    func goTo(_ target: Screen) {
        if mandatorySurface { return }   // 054: navigation pinned (sign-out only)
        screen = target
        agentsLoading = target == .agents || agentsLoading
        historyLoading = target == .history || historyLoading
        auditLoading = target == .audit || auditLoading
        switch target {
        case .agents: sendEvent("discover_agents")
        case .history: sendEvent("get_history")
        case .audit: loadAudit()
        case .chat, .surface: break
        }
    }

    func openMenuItem(_ item: ChromeMenuItem) { openSurface(item.surface, params: item.params) }

    func openSurface(_ surface: String, params: JSONValue = .object([:])) {
        if mandatorySurface { return }   // 054: the pinned surface can't be replaced client-side
        switch surface {
        case "agents": goTo(.agents)
        case "audit": goTo(.audit)
        default:
            sendEvent("chrome_open", .object(["surface": .string(surface), "params": params]))
            screen = .surface
            pendingSurfaceKey = surface
            pendingSurfaceParams = params
            pendingSurface = nil
        }
    }

    func retryPendingSurface() {
        guard !pendingSurfaceKey.isEmpty else { return }
        sendEvent("chrome_open", .object(["surface": .string(pendingSurfaceKey), "params": pendingSurfaceParams]))
    }

    func setToolEnabled(_ agent: Agent, tool: String, enabled: Bool) {
        patchAgent(agent.id) { a in
            var perms = a.permissions; perms[tool] = enabled
            var copy = a; copy.permissions = perms; return copy
        }
        let kind = agent.toolScopeMap[tool] ?? "tools:read"
        Task {
            _ = await rest.setToolPermission(agentId: agent.id, tool: tool, kind: kind, enabled: enabled)
            sendEvent("discover_agents")
        }
    }

    func setAgentEnabled(_ agent: Agent, enabled: Bool) {
        patchAgent(agent.id) { a in
            var copy = a
            copy.permissions = Dictionary(uniqueKeysWithValues: a.tools.map { ($0, enabled) })
            return copy
        }
        let kinds = agent.toolScopeMap.values.isEmpty ? Array(agent.scopes.keys) : Array(Set(agent.toolScopeMap.values))
        var scopes: [String: JSONValue] = [:]
        for k in kinds { scopes[k] = .bool(enabled) }
        var overrides: [String: JSONValue] = [:]
        for t in agent.tools { overrides[t] = .bool(enabled) }
        sendEvent("set_agent_permissions", .object([
            "agent_id": .string(agent.id),
            "scopes": .object(scopes),
            "tool_overrides": .object(overrides),
        ]))
        sendEvent("discover_agents")
    }

    private func patchAgent(_ agentId: String, _ transform: (Agent) -> Agent) {
        agents = agents.map { $0.id == agentId ? transform($0) : $0 }
    }

    func enableRecommended() {
        sendEvent("enable_recommended_agents")
        sendEvent("discover_agents")
    }

    private func loadAudit() {
        Task {
            let events = await rest.audit()
            audit = events
            auditLoading = false
        }
    }

    func viewCanvasSnapshot(_ index: Int) {
        if canvasHistory.indices.contains(index) { viewingIndex = index }
    }

    func backToLiveCanvas() { viewingIndex = nil }

    // MARK: attachments

    func stageAttachment(filename: String, mimeType: String?, data: Data) {
        attachSeq += 1
        let uid = attachSeq
        staged.append(StagedAttachment(uid: uid, filename: filename, category: "file",
                                       attachmentId: nil, state: "uploading", note: nil))
        Task {
            let up = await rest.uploadAttachment(filename: filename, mimeType: mimeType, data: data)
            staged = staged.map { a in
                guard a.uid == uid else { return a }
                var copy = a
                if let up {
                    copy.attachmentId = up.attachmentId
                    copy.category = up.category
                    copy.state = "ready"
                    copy.note = parserNote(up.parserStatus)
                } else {
                    copy.state = "failed"
                    copy.note = "upload failed"
                }
                return copy
            }
        }
    }

    /// Stage a picked or dropped file URL (file importer, macOS drag-and-drop).
    func stageFile(url: URL) {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        guard let data = try? Data(contentsOf: url) else {
            bannerIsError = true
            errorBanner = "Couldn't read \(url.lastPathComponent)"
            return
        }
        let mime = UTType(filenameExtension: url.pathExtension)?.preferredMIMEType
        stageAttachment(filename: url.lastPathComponent, mimeType: mime, data: data)
    }

    func removeAttachment(_ uid: Int) {
        staged.removeAll { $0.uid == uid }
    }

    private func stageExistingAttachment(_ payload: JSONValue) -> Bool {
        guard let id = payload["attachment_id"]?.stringValue, !id.isEmpty else { return false }
        if staged.contains(where: { $0.attachmentId == id }) { return true }
        attachSeq += 1
        staged.append(StagedAttachment(
            uid: attachSeq,
            filename: payload["filename"]?.stringValue ?? "attachment",
            category: payload["category"]?.stringValue ?? "file",
            attachmentId: id, state: "ready", note: nil))
        return true
    }

    // MARK: connection label (parity with Android connectionStripLabel)

    var connectionStripLabel: String? {
        if !everConnected || connected { return nil }
        return "Reconnecting…"
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
