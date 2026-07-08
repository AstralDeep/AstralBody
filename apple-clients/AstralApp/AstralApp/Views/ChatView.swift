// Feature 051 — the adaptive chat shell, a 1:1 match to the Android AdaptiveShell:
// a canvas-dominant area (skeleton while a replacing turn is in flight, empty-
// state hint, live working bar, read-only timeline banner + snapshot overlay), a
// collapsible "Messages" panel with reasoning snippets, the execution step trail,
// and an input bar (mic · attachment chips · rounded field · paperclip · send).
// Compact widths stack; regular widths (iPad/landscape/macOS) split into a rail.
import SwiftUI
import UniformTypeIdentifiers
import AstralCore
#if os(iOS)
import PhotosUI
#endif

struct ChatShell: View {
    @EnvironmentObject var model: AppModel
    #if os(iOS)
    @Environment(\.horizontalSizeClass) private var hSize
    #endif
    private var isSplit: Bool {
        #if os(iOS)
        return hSize == .regular
        #else
        return true
        #endif
    }
    var body: some View {
        Group {
            if isSplit { SplitShell() } else { StackedShell() }
        }
        #if os(macOS)
        // T033/FR-017: Finder drag-and-drop stages chips exactly like the
        // file dialog (Windows-client parity).
        .dropDestination(for: URL.self) { urls, _ in
            guard !model.mutationsLocked, !urls.isEmpty else { return false }
            urls.forEach { model.stageFile(url: $0) }
            return true
        }
        #endif
    }
}

// MARK: - Layouts

private struct StackedShell: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        VStack(spacing: 0) {
            CanvasArea().frame(maxWidth: .infinity, maxHeight: .infinity)
            if model.turnActive { StepTrailView(lines: model.stepTrail) }
            MessagesPanel()
            InputBar()
        }
    }
}

private struct SplitShell: View {
    @EnvironmentObject var model: AppModel
    @EnvironmentObject var theme: ThemeStore
    var body: some View {
        HStack(spacing: 0) {
            VStack(spacing: 0) {
                PanelHeader(title: "Conversation")
                ChatList().frame(maxWidth: .infinity, maxHeight: .infinity)
                if model.turnActive { StepTrailView(lines: model.stepTrail) }
                InputBar()
            }
            .frame(width: 360)
            Divider().overlay(theme.palette.border)
            CanvasArea().frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}

// MARK: - Canvas

private struct CanvasArea: View {
    @EnvironmentObject var model: AppModel
    @EnvironmentObject var theme: ThemeStore
    @State private var showTimeline = false
    private var p: AstralPalette { theme.palette }

    private var canvasItems: [(key: String, comp: AstralComponent)] {
        model.visibleCanvas.enumerated().map { index, comp in
            (comp.componentId ?? "anon-\(index)", comp)
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            if model.isViewingHistory {
                ReadOnlyBanner(label: model.viewingIndex.flatMap { model.canvasHistory[safe: $0]?.label }) {
                    model.backToLiveCanvas()
                }
            } else if model.turnActive && !model.showSkeleton {
                ProgressView().progressViewStyle(.linear).tint(p.secondary)
            }
            ZStack(alignment: .topTrailing) {
                Group {
                    if model.showSkeleton {
                        SkeletonCanvas()
                    } else if model.visibleCanvas.isEmpty {
                        EmptyCanvasHint()
                    } else {
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 12) {
                                // Keyed by component identity so a `remove` op
                                // doesn't shift every later component onto a new
                                // SwiftUI identity (resetting tabs/collapsibles
                                // and scroll anchors — FR-013).
                                ForEach(canvasItems, id: \.key) { item in
                                    ComponentView(component: item.comp)
                                }
                            }
                            .padding(16)
                        }
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)

                if !model.canvasHistory.isEmpty && !model.isViewingHistory {
                    TimelinePill(count: model.canvasHistory.count) { showTimeline = true }
                        .padding(12)
                }
            }
        }
        .background(p.bg)
        .sheet(isPresented: $showTimeline) {
            CanvasTimelineOverlay(history: model.canvasHistory) { idx in
                model.viewCanvasSnapshot(idx)
                showTimeline = false
            }
        }
    }
}

private struct SkeletonCanvas: View {
    @EnvironmentObject var theme: ThemeStore
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(0..<4, id: \.self) { i in
                RoundedRectangle(cornerRadius: AstralRadius.md)
                    .fill(theme.palette.surface.opacity(0.5))
                    .frame(height: i == 0 ? 90 : 60)
                    .frame(maxWidth: .infinity)
                    .shimmer()
            }
            Spacer()
        }
        .padding(16)
    }
}

private struct EmptyCanvasHint: View {
    @EnvironmentObject var theme: ThemeStore
    private var p: AstralPalette { theme.palette }
    var body: some View {
        VStack(spacing: 8) {
            Text("✨").font(.system(size: 40))
            Text("Your generated interface appears here")
                .font(.headline).foregroundStyle(p.text).multilineTextAlignment(.center)
            Text("Ask something below and AstralDeep will build a live interface for it.")
                .font(.subheadline).foregroundStyle(p.muted).multilineTextAlignment(.center)
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct ReadOnlyBanner: View {
    @EnvironmentObject var theme: ThemeStore
    let label: String?
    let onBackToLive: () -> Void
    private var p: AstralPalette { theme.palette }
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "clock.arrow.circlepath").foregroundStyle(p.primary)
            VStack(alignment: .leading, spacing: 1) {
                Text("Viewing a previous canvas").font(.footnote.weight(.semibold)).foregroundStyle(p.text)
                if let label, !label.isEmpty {
                    Text(label).font(.caption).foregroundStyle(p.muted).lineLimit(1)
                }
            }
            Spacer(minLength: 8)
            Button("Back to live", action: onBackToLive)
                .font(.caption.weight(.medium))
                .foregroundStyle(.white)
                .padding(.horizontal, 12).padding(.vertical, 6)
                .background(p.primary, in: Capsule())
                .buttonStyle(.plain)
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .background(p.primary.opacity(0.16))
    }
}

private struct TimelinePill: View {
    @EnvironmentObject var theme: ThemeStore
    let count: Int
    let onClick: () -> Void
    private var p: AstralPalette { theme.palette }
    var body: some View {
        Button(action: onClick) {
            HStack(spacing: 6) {
                Image(systemName: "clock.arrow.circlepath").font(.caption2)
                Text("History (\(count))").font(.caption.weight(.medium))
            }
            .foregroundStyle(p.text)
            .padding(.horizontal, 12).padding(.vertical, 7)
            .background(p.surface.opacity(0.92), in: Capsule())
            .overlay(Capsule().stroke(p.border))
        }
        .buttonStyle(.plain)
    }
}

private struct CanvasTimelineOverlay: View {
    @EnvironmentObject var theme: ThemeStore
    let history: [AppModel.CanvasSnapshot]
    let onSelect: (Int) -> Void
    private var p: AstralPalette { theme.palette }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Previous canvases").font(.headline).foregroundStyle(p.text)
            Text("Read-only snapshots from earlier turns in this chat.")
                .font(.caption).foregroundStyle(p.muted)
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(Array(history.enumerated()).reversed(), id: \.offset) { idx, snap in
                        Button { onSelect(idx) } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(snap.label.isEmpty ? "Canvas \(idx + 1)" : snap.label)
                                        .foregroundStyle(p.text).lineLimit(1)
                                    Text("\(snap.components.count) component\(snap.components.count == 1 ? "" : "s")")
                                        .font(.caption).foregroundStyle(p.muted)
                                }
                                Spacer()
                                Text("›").foregroundStyle(p.muted)
                            }
                            .padding(14)
                            .background(p.surface2, in: RoundedRectangle(cornerRadius: AstralRadius.md))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .padding(16)
        .background(p.bg.ignoresSafeArea())
        .presentationDetents([.medium, .large])
    }
}

// MARK: - Messages / rail

private struct StepTrailView: View {
    @EnvironmentObject var theme: ThemeStore
    let lines: [String]
    var body: some View {
        if lines.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 1) {
                ForEach(lines.suffix(4), id: \.self) { line in
                    Text(line).font(.caption2).foregroundStyle(theme.palette.muted).lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16).padding(.vertical, 4)
        }
    }
}

private struct MessagesPanel: View {
    @EnvironmentObject var model: AppModel
    @EnvironmentObject var theme: ThemeStore
    @State private var expanded = true
    private var p: AstralPalette { theme.palette }
    private var visible: [AppModel.ChatTurn] { model.turns.filter { !$0.text.isEmpty } }

    var body: some View {
        if visible.isEmpty {
            EmptyView()
        } else {
            VStack(spacing: 0) {
                if expanded {
                    Divider().overlay(p.border)
                    ChatList().frame(maxHeight: 320).background(p.bg)
                }
                Button {
                    withAnimation { expanded.toggle() }
                } label: {
                    HStack(spacing: 8) {
                        Text(expanded ? "▼" : "▲").font(.caption2).foregroundStyle(p.muted)
                        Text("Messages").font(.subheadline.weight(.medium)).foregroundStyle(p.text)
                        Text("(\(visible.count))").font(.caption).foregroundStyle(p.muted)
                        Spacer()
                        if !expanded, let status = model.statusText {
                            Text(status).font(.caption).foregroundStyle(p.muted).lineLimit(1)
                        }
                    }
                    .padding(.horizontal, 16).padding(.vertical, 10)
                    .background(p.surface)
                }
                .buttonStyle(.plain)
            }
        }
    }
}

private struct PanelHeader: View {
    @EnvironmentObject var theme: ThemeStore
    let title: String
    var body: some View {
        Text(title.uppercased())
            .font(.caption2.bold()).foregroundStyle(theme.palette.muted)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 14).padding(.vertical, 8)
            .background(theme.palette.surface)
    }
}

private struct ChatList: View {
    @EnvironmentObject var model: AppModel
    private var visible: [AppModel.ChatTurn] { model.turns.filter { !$0.text.isEmpty } }
    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(visible) { turn in ChatBubble(turn: turn).id(turn.id) }
                    if let status = model.statusText { StatusLine(text: status).id("status") }
                }
                .padding(.horizontal, 12).padding(.vertical, 8)
            }
            .onChange(of: visible.count) { _, _ in
                if let last = visible.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
            }
        }
    }
}

private struct StatusLine: View {
    @EnvironmentObject var theme: ThemeStore
    let text: String
    var body: some View {
        HStack(spacing: 6) {
            ProgressView().controlSize(.small)
            Text(text).font(.caption).foregroundStyle(theme.palette.muted)
        }
    }
}

private struct ChatBubble: View {
    @EnvironmentObject var theme: ThemeStore
    let turn: AppModel.ChatTurn
    private var p: AstralPalette { theme.palette }
    var body: some View {
        if turn.role == "reasoning" {
            ReasoningSnippet(text: turn.text)
        } else {
            let isUser = turn.role == "user"
            HStack {
                if isUser { Spacer(minLength: 40) }
                Group {
                    if isUser { Text(turn.text).foregroundStyle(p.text) }
                    else { markdown(turn.text).foregroundStyle(p.text) }
                }
                .font(.subheadline)
                .padding(.horizontal, 14).padding(.vertical, 10)
                // User turns are the web's 20% primary tint + 30% border —
                // not a saturated pill (cross-client bubble convention).
                .background(isUser ? AnyShapeStyle(p.primary.opacity(0.20)) : AnyShapeStyle(p.surface2),
                            in: RoundedRectangle(cornerRadius: AstralRadius.md))
                .overlay(RoundedRectangle(cornerRadius: AstralRadius.md)
                    .stroke(isUser ? p.primary.opacity(0.30) : .clear))
                .frame(maxWidth: isUser ? 300 : .infinity, alignment: isUser ? .trailing : .leading)
                if !isUser { Spacer(minLength: 20) }
            }
            .frame(maxWidth: .infinity, alignment: isUser ? .trailing : .leading)
        }
    }
    private func markdown(_ s: String) -> Text {
        if let a = try? AttributedString(markdown: s,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) { return Text(a) }
        return Text(s)
    }
}

private struct ReasoningSnippet: View {
    @EnvironmentObject var theme: ThemeStore
    let text: String
    @State private var expanded = false
    private var p: AstralPalette { theme.palette }
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button { withAnimation { expanded.toggle() } } label: {
                HStack(spacing: 6) {
                    Text(expanded ? "▼" : "▶").font(.caption2).foregroundStyle(p.muted)
                    Text("Reasoning").font(.caption.weight(.medium)).foregroundStyle(p.muted)
                    Spacer(minLength: 0)
                }
            }
            .buttonStyle(.plain)
            if expanded {
                Text(text).font(.caption).foregroundStyle(p.text)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(p.surface2.opacity(0.5), in: RoundedRectangle(cornerRadius: 12))
    }
}

// MARK: - Input bar

private struct InputBar: View {
    @EnvironmentObject var model: AppModel
    @EnvironmentObject var theme: ThemeStore
    @State private var input = ""
    @State private var showImporter = false
    #if os(iOS)
    @State private var showPhotoPicker = false
    @State private var photoItem: PhotosPickerItem?
    #endif
    @FocusState private var focused: Bool
    private var p: AstralPalette { theme.palette }
    private let slashCommands = ["/help", "/agents", "/summarize", "/research", "/weather"]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if model.mutationsLocked {
                Text("Viewing history — messaging is paused. Return to the live view to continue.")
                    .font(.caption).foregroundStyle(p.muted)
                    .padding(.horizontal, 6)
            }
            if !model.staged.isEmpty {
                AttachmentChips(staged: model.staged) { model.removeAttachment($0) }
            }
            if input.hasPrefix("/") && !input.contains(" ") {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(slashCommands.filter { $0.hasPrefix(input) }, id: \.self) { cmd in
                            Button(cmd) { input = cmd + " " }
                                .font(.caption.monospaced()).foregroundStyle(p.primary)
                        }
                    }
                }
            }
            HStack(spacing: 6) {
                GlyphButton(system: "mic.fill", enabled: !model.mutationsLocked) { focused = true }
                    .accessibilityLabel("Dictate a message")
                TextField("Message AstralDeep…", text: $input, axis: .vertical)
                    .textFieldStyle(.plain)
                    .lineLimit(1...4)
                    .disabled(model.mutationsLocked)
                    .focused($focused)
                    .padding(.horizontal, 14).padding(.vertical, 9)
                    .background(p.surface2, in: RoundedRectangle(cornerRadius: 22))
                    .overlay(RoundedRectangle(cornerRadius: 22).stroke(p.border))
                    .onSubmit(send)
                Menu {
                    Button("Upload a file") { showImporter = true }
                    #if os(iOS)
                    Button("Choose a photo") { showPhotoPicker = true }
                    #endif
                    Button("Choose from your files") { model.openSurface("attachments") }
                } label: {
                    Image(systemName: "paperclip").font(.system(size: 18)).foregroundStyle(p.muted)
                }
                .disabled(model.mutationsLocked)
                .accessibilityLabel("Attach a file")
                SendButton(enabled: canSend) { send() }
            }
        }
        .padding(.horizontal, 8).padding(.vertical, 8)
        .background(p.surface)
        .fileImporter(isPresented: $showImporter, allowedContentTypes: [.item],
                      allowsMultipleSelection: true) { result in
            guard case .success(let urls) = result else { return }
            urls.forEach { model.stageFile(url: $0) }
        }
        #if os(iOS)
        .photosPicker(isPresented: $showPhotoPicker, selection: $photoItem, matching: .images)
        .onChange(of: photoItem) { _, item in
            guard let item else { return }
            Task {
                if let data = try? await item.loadTransferable(type: Data.self) {
                    let ext = item.supportedContentTypes.first?.preferredFilenameExtension ?? "jpg"
                    let mime = item.supportedContentTypes.first?.preferredMIMEType
                    model.stageAttachment(filename: "photo-\(UUID().uuidString.prefix(8)).\(ext)",
                                          mimeType: mime, data: data)
                }
                photoItem = nil
            }
        }
        #endif
    }

    private var canSend: Bool {
        !model.mutationsLocked &&
            (!input.trimmingCharacters(in: .whitespaces).isEmpty ||
                model.staged.contains { $0.state == "ready" })
    }

    private func send() {
        guard canSend else { return }
        model.sendChat(input)
        input = ""
        focused = true
    }
}

private struct AttachmentChips: View {
    @EnvironmentObject var theme: ThemeStore
    let staged: [AppModel.StagedAttachment]
    let onRemove: (Int) -> Void
    private var p: AstralPalette { theme.palette }
    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(staged) { att in
                    HStack(spacing: 6) {
                        Text(marker(att.state)).font(.caption2)
                        VStack(alignment: .leading, spacing: 0) {
                            Text(att.filename).font(.caption).foregroundStyle(p.text)
                                .lineLimit(1).frame(maxWidth: 160, alignment: .leading)
                            if let note = att.note, !note.isEmpty {
                                Text(note).font(.caption2).foregroundStyle(p.muted).lineLimit(1)
                            }
                        }
                        Button { onRemove(att.uid) } label: {
                            Image(systemName: "xmark").font(.caption2).foregroundStyle(p.muted)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Remove \(att.filename)")
                    }
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background(p.surface2, in: RoundedRectangle(cornerRadius: 14))
                }
            }
        }
    }
    private func marker(_ state: String) -> String {
        switch state { case "uploading": return "…"; case "failed": return "⚠"; default: return "📄" }
    }
}

private struct GlyphButton: View {
    @EnvironmentObject var theme: ThemeStore
    let system: String
    var enabled: Bool = true
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Image(systemName: system).font(.system(size: 18))
                .foregroundStyle(theme.palette.muted.opacity(enabled ? 1 : 0.4))
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }
}

private struct SendButton: View {
    @EnvironmentObject var theme: ThemeStore
    let enabled: Bool
    let action: () -> Void
    private var p: AstralPalette { theme.palette }
    var body: some View {
        Button(action: action) {
            Image(systemName: "arrow.up").font(.system(size: 18, weight: .bold)).foregroundStyle(.white)
                .frame(width: 44, height: 44)
                .background(enabled ? AnyShapeStyle(p.primary) : AnyShapeStyle(p.surface2), in: Circle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .accessibilityLabel("Send message")
    }
}

// MARK: - shimmer + safe index

extension View {
    func shimmer() -> some View { modifier(ShimmerModifier()) }
}

private struct ShimmerModifier: ViewModifier {
    @State private var phase: CGFloat = -1
    func body(content: Content) -> some View {
        content.overlay(
            GeometryReader { geo in
                LinearGradient(colors: [.clear, .white.opacity(0.18), .clear],
                               startPoint: .leading, endPoint: .trailing)
                    .frame(width: geo.size.width * 0.6)
                    .offset(x: geo.size.width * phase)
            }
            .allowsHitTesting(false)
        )
        .clipped()
        .onAppear {
            withAnimation(.linear(duration: 1.3).repeatForever(autoreverses: false)) { phase = 1.6 }
        }
    }
}

extension Array {
    subscript(safe index: Int) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}

#Preview("Chat shell") {
    let model = AppModel()
    model.turns = [
        .init(id: "u0", role: "user", text: "Show me Q3 sales"),
        .init(id: "a0", role: "assistant", text: "Here's a **live summary** of Q3."),
    ]
    // Authored with AstralPrims (the Swift astralprims mirror) — the same
    // wire dicts a Python agent would produce.
    model.canvas = [
        AstralPrims.Hero(title: "Q3 Sales",
                         subtitle: "Revenue up 12% quarter over quarter",
                         variant: "gradient"),
        AstralPrims.Grid(columns: 2).add(
            AstralPrims.MetricCard(title: "Revenue", value: "$1.2M", subtitle: "+12%"),
            AstralPrims.MetricCard(title: "New users", value: "3,401", variant: "success")),
    ].compactMap { AstralComponent(json: $0.toDict()) }
    return ChatShell()
        .environmentObject(model)
        .environmentObject(model.themeStore)
        .preferredColorScheme(.dark)
}
