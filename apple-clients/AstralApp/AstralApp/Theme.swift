// Feature 051 — the AstralDeep design system, shared 1:1 with the web,
// Android, and Windows clients (same palette, radii, spacing). Dark-first.
// The server can restyle live via `user_preferences` / `theme_apply`
// (channel colors or a named preset) exactly like the other clients.
import SwiftUI
import AstralCore

/// Canonical palette. Hex values match backend/webrender/static/astral.css
/// and the Windows/Android defaults (the "midnight" preset).
struct AstralPalette: Equatable {
    var bg = Color(hex: 0x0F1221)
    var surface = Color(hex: 0x1A1E2E)
    var surface2 = Color(hex: 0x1E2338)
    var border = Color.white.opacity(0.08)
    var primary = Color(hex: 0x6366F1)
    var secondary = Color(hex: 0x8B5CF6)
    var accent = Color(hex: 0x06B6D4)
    var text = Color(hex: 0xF3F4F6)
    var muted = Color(hex: 0x9CA3AF)
    var success = Color(hex: 0x22C55E)
    var warning = Color(hex: 0xEAB308)
    var error = Color(hex: 0xEF4444)
    var info = Color(hex: 0x3B82F6)

    static let midnight = AstralPalette()

    /// Gradient used for hero bands and primary buttons (primary → secondary,
    /// 135° diagonal — matches the web `--accent-grad` and Windows GRAD).
    var gradient: LinearGradient {
        LinearGradient(colors: [primary, secondary],
                       startPoint: .topLeading, endPoint: .bottomTrailing)
    }

    /// Semantic accent color for a component `variant`.
    func variant(_ v: String?) -> Color {
        switch v {
        case "error", "danger": return error
        case "warning": return warning
        case "success": return success
        case "info": return info
        case "accent": return accent
        default: return primary
        }
    }
}

/// Radii + spacing tokens (parity with the web `--radius-*` / `--space-*`).
enum AstralRadius {
    static let sm: CGFloat = 6
    static let md: CGFloat = 10
    static let lg: CGFloat = 14
}

/// Holds the live palette so the server can restyle without a relaunch
/// (feature 044 US5 parity). Observed by the renderer and chrome.
@MainActor
final class ThemeStore: ObservableObject {
    @Published var palette = AstralPalette.midnight

    /// A `user_preferences` frame payload (`{preferences:{theme:…}}` or a bare
    /// theme spec). Fail-open: unknown shapes are ignored.
    func applyPreferences(_ json: JSONValue?) {
        let theme = json?["preferences"]?["theme"] ?? json?["theme"] ?? json
        apply(spec: theme)
    }

    /// A theme spec: `{preset}`, `{colors:{channel:hex}}`,
    /// `{color_key,color_value}`, or a flat `{channel:hex}` map.
    func apply(spec: JSONValue?) {
        guard let spec else { return }
        if let preset = spec["preset"]?.stringValue { apply(preset: preset) }
        if let colors = spec["colors"]?.objectValue { apply(colors: colors) }
        if let key = spec["color_key"]?.stringValue,
           let val = spec["color_value"]?.stringValue,
           let color = Color(cssHex: val) {
            set(channel: key, color)
        }
        if spec["preset"] == nil, spec["colors"] == nil, spec["color_key"] == nil,
           let flat = spec.objectValue {
            apply(colors: flat)
        }
    }

    private func apply(colors: [String: JSONValue]) {
        for (key, value) in colors {
            if let hex = value.stringValue, let color = Color(cssHex: hex) {
                set(channel: key, color)
            }
        }
    }

    private func set(channel: String, _ color: Color) {
        switch channel {
        case "bg", "background": palette.bg = color
        case "surface": palette.surface = color
        case "surface2", "surface_2": palette.surface2 = color
        case "primary": palette.primary = color
        case "secondary": palette.secondary = color
        case "accent": palette.accent = color
        case "text": palette.text = color
        case "muted": palette.muted = color
        default: break
        }
    }

    /// Named presets — channel-for-channel copies of the canonical tables in
    /// backend webrender / Windows theme.py / Android Theme.kt. A preset name
    /// arrives alone in `user_preferences`, so EVERY themed channel must be
    /// set here (not just the accents) or the client drifts from its twins.
    func apply(preset: String) {
        switch preset {
        case "daylight":
            palette = AstralPalette(bg: Color(hex: 0xF8FAFC), surface: Color(hex: 0xFFFFFF),
                                    surface2: Color(hex: 0xEEF0F5), border: Color.black.opacity(0.08),
                                    primary: Color(hex: 0x4F46E5), secondary: Color(hex: 0x7C3AED),
                                    accent: Color(hex: 0x0891B2), text: Color(hex: 0x1E293B),
                                    muted: Color(hex: 0x64748B))
        case "ocean":
            palette = AstralPalette(bg: Color(hex: 0x0C1222), surface: Color(hex: 0x132038),
                                    primary: Color(hex: 0x0EA5E9), secondary: Color(hex: 0x06B6D4),
                                    accent: Color(hex: 0x2DD4BF), text: Color(hex: 0xE2E8F0),
                                    muted: Color(hex: 0x94A3B8))
        case "sunset":
            palette = AstralPalette(bg: Color(hex: 0x1C1017), surface: Color(hex: 0x2D1B24),
                                    primary: Color(hex: 0xF97316), secondary: Color(hex: 0xEF4444),
                                    accent: Color(hex: 0xFBBF24), text: Color(hex: 0xFEF2F2),
                                    muted: Color(hex: 0xA8A29E))
        case "forest":
            palette = AstralPalette(bg: Color(hex: 0x0F1A14), surface: Color(hex: 0x1A2E22),
                                    primary: Color(hex: 0x22C55E), secondary: Color(hex: 0x10B981),
                                    accent: Color(hex: 0xA3E635), text: Color(hex: 0xECFDF5),
                                    muted: Color(hex: 0x86EFAC))
        default:
            palette = .midnight
        }
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255,
                  opacity: 1)
    }

    /// Parse `#rrggbb` / `rrggbb` (the wire format used by the theme spec).
    init?(cssHex raw: String) {
        var s = raw.trimmingCharacters(in: .whitespaces)
        if s.hasPrefix("#") { s.removeFirst() }
        guard s.count == 6, let value = UInt32(s, radix: 16) else { return nil }
        self.init(hex: value)
    }
}
