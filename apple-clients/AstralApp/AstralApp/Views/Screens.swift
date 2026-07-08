// Feature 051 — the native settings surfaces reached from the top-bar gear /
// server chrome, 1:1 with the Android Screens.kt: Agents (per-agent + per-tool
// permission toggles, "Enable recommended"), Audit (the hash-chained event log),
// and the SDUI Surface screen (chrome_surface rendered natively, with a load
// timeout + Retry). Plus the shared skeleton list.
import SwiftUI
import AstralCore

// MARK: - Agents

struct AgentsView: View {
    @EnvironmentObject var model: AppModel
    @EnvironmentObject var theme: ThemeStore
    private var p: AstralPalette { theme.palette }

    var body: some View {
        Group {
            if model.agentsLoading && model.agents.isEmpty {
                SkeletonList()
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text("Agents").font(.title2.bold()).foregroundStyle(p.text)
                            Spacer()
                            Button("Enable recommended") { model.enableRecommended() }
                                .buttonStyle(AstralButtonStyle(palette: p, variant: "secondary"))
                        }
                        if model.agents.isEmpty {
                            Text("No agents loaded yet.").foregroundStyle(p.muted)
                        }
                        ForEach(model.agents) { agent in
                            AgentCard(agent: agent)
                        }
                    }
                    .padding(16)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(p.bg)
    }
}

private struct AgentCard: View {
    @EnvironmentObject var model: AppModel
    @EnvironmentObject var theme: ThemeStore
    let agent: Agent
    @State private var expanded = false
    private var p: AstralPalette { theme.palette }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 8) {
                Button { withAnimation { expanded.toggle() } } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text((expanded ? "▼ " : "▶ ") + agent.name)
                            .font(.headline).foregroundStyle(p.text)
                        if !agent.description.isEmpty {
                            Text(agent.description).font(.caption).foregroundStyle(p.muted)
                        }
                        Text("\(agent.enabledCount) / \(agent.tools.count) tools enabled")
                            .font(.caption2).foregroundStyle(p.muted)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                Toggle("", isOn: Binding(
                    get: { agent.anyEnabled },
                    set: { model.setAgentEnabled(agent, enabled: $0) }))
                    .labelsHidden().tint(p.primary)
                    .accessibilityLabel("Enable \(agent.name)")
            }
            if expanded {
                if agent.tools.isEmpty {
                    Text("This agent exposes no tools.").font(.caption).foregroundStyle(p.muted)
                }
                ForEach(agent.tools, id: \.self) { tool in
                    HStack(alignment: .top, spacing: 8) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text(tool).font(.subheadline).foregroundStyle(p.text)
                            if let desc = agent.toolDescriptions[tool], !desc.isEmpty {
                                Text(desc).font(.caption).foregroundStyle(p.muted)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        Toggle("", isOn: Binding(
                            get: { agent.permissions[tool] ?? false },
                            set: { model.setToolEnabled(agent, tool: tool, enabled: $0) }))
                            .labelsHidden().tint(p.primary)
                            .accessibilityLabel("Enable \(tool) for \(agent.name)")
                    }
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(p.surface.opacity(0.55), in: RoundedRectangle(cornerRadius: AstralRadius.lg))
        .overlay(RoundedRectangle(cornerRadius: AstralRadius.lg).stroke(p.border))
    }
}

// MARK: - Audit

struct AuditView: View {
    @EnvironmentObject var model: AppModel
    @EnvironmentObject var theme: ThemeStore
    private var p: AstralPalette { theme.palette }

    var body: some View {
        Group {
            if model.auditLoading && model.audit.isEmpty {
                SkeletonList()
            } else if model.audit.isEmpty {
                Text("No audit events.").foregroundStyle(p.muted)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(model.audit, id: \.identity) { event in
                            AuditCard(event: event)
                        }
                    }
                    .padding(16)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(p.bg)
    }
}

private struct AuditCard: View {
    @EnvironmentObject var theme: ThemeStore
    let event: AuditEvent
    @State private var expanded = false
    private var p: AstralPalette { theme.palette }

    var body: some View {
        Button { withAnimation { expanded.toggle() } } label: {
            VStack(alignment: .leading, spacing: 4) {
                Text([event.eventClass, event.action].compactMap { $0 }.joined(separator: " · "))
                    .font(.subheadline.weight(.semibold)).foregroundStyle(p.text)
                Text([event.outcome, event.recordedAt].compactMap { $0 }.joined(separator: "  "))
                    .font(.caption).foregroundStyle(p.muted)
                if expanded {
                    if let od = event.outcomeDetail { Text(od).font(.caption).foregroundStyle(p.text) }
                    if let d = event.detail { Text(d).font(.caption.monospaced()).foregroundStyle(p.text) }
                    if let id = event.id {
                        Text("id: \(id)").font(.caption2).foregroundStyle(p.muted)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(p.surface2, in: RoundedRectangle(cornerRadius: AstralRadius.md))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - SDUI Surface (chrome_surface rendered natively, T039 timeout+retry)

struct SurfaceView: View {
    @EnvironmentObject var model: AppModel
    @EnvironmentObject var theme: ThemeStore
    @State private var timedOut = false
    private var p: AstralPalette { theme.palette }

    var body: some View {
        Group {
            if let surface = model.pendingSurface {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        Text(surface.title.isEmpty ? "Settings" : surface.title)
                            .font(.title2.bold()).foregroundStyle(p.text)
                        ForEach(Array(surface.components.enumerated()), id: \.offset) { _, comp in
                            ComponentView(component: comp)
                        }
                    }
                    .padding(16)
                }
            } else if timedOut {
                VStack(spacing: 12) {
                    Text("Couldn't load this settings screen")
                        .font(.headline).foregroundStyle(p.text).multilineTextAlignment(.center)
                    Text("The server didn't send it in time. Check your connection and try again.")
                        .font(.subheadline).foregroundStyle(p.muted).multilineTextAlignment(.center)
                    Button("Retry") {
                        timedOut = false
                        model.retryPendingSurface()
                    }
                    .buttonStyle(AstralButtonStyle(palette: p, variant: "primary"))
                }
                .padding(28)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                SkeletonList()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(p.bg)
        // Re-arm the 10 s load timer whenever the awaited surface key changes or
        // a surface arrives (parity with Android's LaunchedEffect, T039).
        .task(id: surfaceTaskKey) {
            timedOut = false
            if model.pendingSurface != nil { return }
            try? await Task.sleep(nanoseconds: 10_000_000_000)
            if model.pendingSurface == nil { timedOut = true }
        }
    }

    private var surfaceTaskKey: String {
        "\(model.pendingSurfaceKey)-\(model.pendingSurface == nil ? 0 : 1)"
    }
}

// MARK: - Skeleton list (loading placeholder)

struct SkeletonList: View {
    @EnvironmentObject var theme: ThemeStore
    var body: some View {
        VStack(spacing: 10) {
            ForEach(0..<6, id: \.self) { _ in
                RoundedRectangle(cornerRadius: AstralRadius.md)
                    .fill(theme.palette.surface.opacity(0.5))
                    .frame(height: 56)
                    .frame(maxWidth: .infinity)
            }
            Spacer()
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
