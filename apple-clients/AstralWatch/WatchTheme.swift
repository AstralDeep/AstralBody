// Feature 051 — the watch's slice of the AstralDeep design system. The wrist
// is server-degraded and system-styled (no live theming channel — recorded in
// the parity matrix), but its brand hues must still be the shared tokens, not
// Apple system colors.
import SwiftUI

enum WatchBrand {
    /// AstralDeep indigo — the app tint (matches web --color-primary #6366F1).
    static let primary = Color(red: 0x63 / 255, green: 0x66 / 255, blue: 0xF1 / 255)
    /// Shared semantic tokens (astral.css --color-warning / --color-error).
    static let warning = Color(red: 0xEA / 255, green: 0xB3 / 255, blue: 0x08 / 255)
    static let error = Color(red: 0xEF / 255, green: 0x44 / 255, blue: 0x44 / 255)
}
