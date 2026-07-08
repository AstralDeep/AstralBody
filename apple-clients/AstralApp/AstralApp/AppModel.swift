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
final class AppModel: NSObject, ObservableObject {

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

    @AppStorage("serverBase") var serverBaseText = AstralConfig.serverBaseURL
    @AppStorage("authority") var authorityText = AstralConfig.keycloakAuthority

    #if os(macOS)
    let clientId = AstralConfig.macosClientId
    #else
    let clientId = AstralConfig.iosClientId
    #endif
    let redirectURI = AstralConfig.redirectURI

    // MARK: published state (mirrors Android UiState)

    @Published var signedIn = false
    @Published var accountName = ""
    @Published var connected = false
    @Published var everConnected = false
    @Published var screen: Screen = .chat
    @Published var activeChatId: String?

    @Published var turns: [ChatTurn] = []
    @Published var canvas: [AstralComponent] = []
    @Published var pendingCanvas: [AstralComponent] = []
    @Published var turnActive = false
    @Published var pendingReplace = false
    @Published var canvasLabel = ""
    @Published var pendingLabel = ""
    @Published var canvasHistory: [CanvasSnapshot] = []
    @Published var viewingIndex: Int?

    @Published var staged: [StagedAttachment] = []
    @Published var statusText: String?
    @Published var errorBanner: String?
    @Published var bannerIsError = true
    @Published var stepTrail: [String] = []
    @Published var asyncDetached = false

    @Published var agents: [Agent] = []
    @Published var history: [ChatSummary] = []
    @Published var audit: [AuditEvent] = []
    @Published var agentsLoading = false
    @Published var historyLoading = false
    @Published var auditLoading = false

    @Published var chromeMenu: ChromeMenuModel?
    @Published var pendingSurfaceKey = ""
    @Published var pendingSurfaceParams: JSONValue = .object([:])
    @Published var pendingSurface: SurfaceContent?
    @Published var timelineReadOnly = false

    @Published var signInError: String?

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

    // MARK: session plumbing

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
    private var seqState: [String: Int] = [:]
    private var attachSeq = 0

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
        super.init()
        let defaults = UserDefaults.standard
        if (defaults.string(forKey: "serverBase") ?? "").isEmpty {
            defaults.set(AstralConfig.serverBaseURL, forKey: "serverBase")
        }
        if (defaults.string(forKey: "authority") ?? "").isEmpty {
            defaults.set(AstralConfig.keycloakAuthority, forKey: "authority")
        }
    }

    func bootstrap() async {
        guard let stored = store.load() else { return }
        tokens = stored.tokenSet
        switch await refreshOutcome() {
        case .ok, .transient:
            // Transient (offline) keeps the stored credentials: land on the
            // signed-in shell with the reconnect strip; the WS backoff loop
            // retries and registers once the network returns. Credentials are
            // wiped ONLY on a definitive IdP rejection — never for being
            // offline at launch.
            await enterSignedIn(resumedSession: true)
        case .rejected:
            store.wipe()
            tokens = nil
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
            await enterSignedIn(resumedSession: false)
        } catch {
            signInError = error.localizedDescription
        }
    }

    /// Ensure a live access token, classifying failures so callers can tell
    /// "the IdP revoked us" (wipe + interactive sign-in) from "we're offline"
    /// (keep credentials, retry later).
    private func refreshOutcome() async -> RefreshResult {
        guard let current = tokens else { return .rejected("no session") }
        if !current.needsRefresh() { return .ok(current) }
        guard let refresh = current.refreshToken, let oidc else {
            return .rejected("no refresh token")
        }
        let result = await RefreshStrategy.direct(oidc).attempt(refreshToken: refresh)
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

    /// The server refused our token. `refreshOutcome` short-circuits when the
    /// token isn't near expiry, which would reconnect with the SAME rejected
    /// credential forever — so FORCE a real IdP refresh and only reconnect if
    /// it produced a different token; otherwise the session is dead
    /// server-side (revoked / hard cap) and we go to interactive sign-in.
    private func handleAuthRequired() async {
        guard let current = tokens, let refresh = current.refreshToken, let oidc else {
            await signOut()
            return
        }
        switch await RefreshStrategy.direct(oidc).attempt(refreshToken: refresh) {
        case .ok(let set) where set.accessToken != current.accessToken:
            tokens = set
            store.save(StoredTokens(from: set))
            connectWS(resumed: true)
        case .ok:
            await signOut()   // same token — the server will just refuse it again
        case .rejected:
            await signOut()
        case .transient:
            break             // offline blip; the WS backoff loop keeps retrying
        }
    }

    private func enterSignedIn(resumedSession: Bool) async {
        accountName = tokens?.displayName ?? ""
        signedIn = true
        connectWS(resumed: resumedSession)
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
        resetChatState()
        chromeMenu = nil
        agents = []; history = []; audit = []
    }

    // MARK: WS

    private var lastReportedViewport: (width: Int, height: Int)?

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

    private func handleFrame(_ frame: InboundFrame) {
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
            let pct = frame.payload["percentage"]?.stringValue.map { " (\($0)%)" } ?? ""
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
            if screen == .surface {
                screen = .chat
                pendingSurface = nil
                pendingSurfaceKey = ""
                pendingSurfaceParams = .object([:])
            }
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
            turnActive = false; pendingReplace = false; statusText = nil
            stepTrail = []; asyncDetached = false
            return
        }
        if !canvas.isEmpty {
            let label = canvasLabel.isEmpty ? "Canvas \(canvasHistory.count + 1)" : canvasLabel
            canvasHistory.append(CanvasSnapshot(label: label, components: canvas))
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
