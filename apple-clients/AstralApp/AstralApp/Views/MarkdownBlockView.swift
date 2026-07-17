import AstralCore
// Feature 053 — native rendering for block markdown (FR-004 parity with the
// web's block_md): text components with variant="markdown" and assistant
// narrative doc cards carry headings, fenced code, lists and pipe tables that
// an inline-only parse would show as literal syntax. AstralCore segments the
// source; this view styles each block and runs the shared inline parse on the
// text-bearing ones.
import SwiftUI

struct MarkdownBlockView: View {
    let source: String
    @Environment(ThemeStore.self) var theme
    private var p: AstralPalette { theme.palette }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(MarkdownBlocks.parse(source).enumerated()), id: \.offset) { _, block in
                blockView(block)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func blockView(_ block: MarkdownBlock) -> some View {
        switch block {
        case .heading(let level, let text):
            Text(InlineMarkdown.attributed(text))
                .font(headingFont(level))
                .foregroundStyle(p.text)
        case .paragraph(let text):
            Text(InlineMarkdown.attributed(text))
                .fixedSize(horizontal: false, vertical: true)
        case .code(let text):
            ScrollView(.horizontal, showsIndicators: false) {
                Text(text)
                    .font(.callout.monospaced())
                    .textSelection(.enabled)
                    .padding(10)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.black.opacity(0.35), in: RoundedRectangle(cornerRadius: AstralRadius.sm))
        case .bullets(let items, let ordered, let start):
            VStack(alignment: .leading, spacing: 3) {
                ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                    HStack(alignment: .top, spacing: 6) {
                        Text(ordered ? "\(start + index)." : "•").foregroundStyle(p.muted)
                        Text(InlineMarkdown.attributed(item))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        case .table(let rows, let hasHeader):
            ScrollView(.horizontal, showsIndicators: false) {
                Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 4) {
                    ForEach(Array(rows.enumerated()), id: \.offset) { rowIndex, row in
                        GridRow {
                            ForEach(Array(row.enumerated()), id: \.offset) { _, cell in
                                Text(InlineMarkdown.attributed(cell))
                                    .font(hasHeader && rowIndex == 0 ? .caption.bold() : .callout)
                                    .foregroundStyle(hasHeader && rowIndex == 0 ? p.muted : p.text)
                            }
                        }
                        if hasHeader && rowIndex == 0 { Divider().overlay(p.border) }
                    }
                }
            }
        case .divider:
            Divider().overlay(p.border)
        }
    }

    private func headingFont(_ level: Int) -> Font {
        switch level {
        case 1: return .title2.bold()
        case 2: return .title3.bold()
        case 3: return .headline
        default: return .subheadline.bold()
        }
    }
}
