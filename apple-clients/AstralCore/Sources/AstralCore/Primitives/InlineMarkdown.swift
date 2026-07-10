// Feature 053 — the ONE inline-markdown parse shared by every Apple surface.
// The wire carries raw markdown in narrative text, alert messages and list
// items (the web renderer converts server-side; native clients parse locally).
// Inline-only, whitespace-preserving: block syntax stays literal and newlines
// survive, matching the established iOS/macOS treatment — and the watch must
// match it too, or the wrist shows literal asterisks (FR-004 parity).
import Foundation

public enum InlineMarkdown {
    /// `**bold**`/`*italic*`/`` `code` ``/links → styled runs; anything the
    /// parser rejects is returned verbatim (never blank, never thrown).
    public static func attributed(_ string: String) -> AttributedString {
        (try? AttributedString(
            markdown: string,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
            ?? AttributedString(string)
    }
}
