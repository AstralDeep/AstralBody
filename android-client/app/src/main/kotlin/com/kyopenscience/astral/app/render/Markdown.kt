package com.kyopenscience.astral.app.render

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withLink
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.kyopenscience.astral.app.ui.theme.AstralColors

/**
 * A small, dependency-free Markdown renderer for Compose — the Android analogue of
 * the rendered markdown the web/Windows clients show. Handles the common subset
 * the LLM emits: headings, bullet/numbered lists, fenced code blocks, and inline
 * **bold**, *italic*, and `code`. Anything else falls through as plain text.
 */
@Composable
fun MarkdownText(
    text: String,
    modifier: Modifier = Modifier,
) {
    val lines = text.trim('\n').split("\n")
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        var i = 0
        while (i < lines.size) {
            val line = lines[i]
            val trimmed = line.trimStart()
            when {
                trimmed.startsWith("```") -> {
                    val buf = StringBuilder()
                    i++
                    while (i < lines.size && !lines[i].trimStart().startsWith("```")) {
                        buf.append(lines[i]).append('\n')
                        i++
                    }
                    CodeBlock(buf.toString().trimEnd('\n'))
                }
                trimmed.startsWith("### ") -> HeadingLine(trimmed.removePrefix("### "), MaterialTheme.typography.titleSmall)
                trimmed.startsWith("## ") -> HeadingLine(trimmed.removePrefix("## "), MaterialTheme.typography.titleMedium)
                trimmed.startsWith("# ") -> HeadingLine(trimmed.removePrefix("# "), MaterialTheme.typography.titleLarge)
                trimmed.startsWith("- ") || trimmed.startsWith("* ") -> BulletLine("•", trimmed.drop(2))
                trimmed.matchesOrderedItem() -> BulletLine(trimmed.substringBefore('.') + ".", trimmed.substringAfter(". "))
                trimmed.isBlank() -> Text(" ", style = MaterialTheme.typography.bodySmall)
                else -> Text(inlineMarkdown(line), style = MaterialTheme.typography.bodyMedium)
            }
            i++
        }
    }
}

private fun String.matchesOrderedItem(): Boolean {
    val dot = indexOf(". ")
    return dot in 1..3 && substring(0, dot).all { it.isDigit() }
}

@Composable
private fun HeadingLine(
    text: String,
    style: androidx.compose.ui.text.TextStyle,
) {
    Text(inlineMarkdown(text), style = style)
}

@Composable
private fun BulletLine(
    marker: String,
    content: String,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(marker, style = MaterialTheme.typography.bodyMedium)
        Text(inlineMarkdown(content), style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun CodeBlock(code: String) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(6.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            text = code,
            fontFamily = FontFamily.Monospace,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(10.dp),
        )
    }
}

/** Parse inline **bold**, *italic*, _italic_, `code`, and [links](url) into an AnnotatedString. */
fun inlineMarkdown(text: String): AnnotatedString =
    buildAnnotatedString {
        var i = 0
        while (i < text.length) {
            when {
                // A `[label](url)` link → a clickable, underlined accent span (T029).
                // A Text rendering this AnnotatedString handles the tap automatically.
                text[i] == '[' -> {
                    val close = text.indexOf(']', i + 1)
                    val open = close + 1
                    val paren = if (close > i && open < text.length && text[open] == '(') text.indexOf(')', open + 1) else -1
                    if (paren > open) {
                        val label = text.substring(i + 1, close)
                        val url = text.substring(open + 1, paren)
                        withLink(LinkAnnotation.Url(url)) {
                            withStyle(SpanStyle(color = AstralColors.Cyan, textDecoration = TextDecoration.Underline)) {
                                append(label)
                            }
                        }
                        i = paren + 1
                    } else {
                        append(text[i])
                        i++
                    }
                }
                text.startsWith("**", i) -> {
                    val end = text.indexOf("**", i + 2)
                    if (end >= 0) {
                        withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(text.substring(i + 2, end)) }
                        i = end + 2
                    } else {
                        append(text[i])
                        i++
                    }
                }
                text[i] == '`' -> {
                    val end = text.indexOf('`', i + 1)
                    if (end >= 0) {
                        withStyle(SpanStyle(fontFamily = FontFamily.Monospace)) { append(text.substring(i + 1, end)) }
                        i = end + 1
                    } else {
                        append(text[i])
                        i++
                    }
                }
                (text[i] == '*' || text[i] == '_') && i + 1 < text.length && text[i + 1] != ' ' -> {
                    val marker = text[i]
                    val end = text.indexOf(marker, i + 1)
                    if (end >= 0) {
                        withStyle(SpanStyle(fontStyle = FontStyle.Italic)) { append(text.substring(i + 1, end)) }
                        i = end + 1
                    } else {
                        append(text[i])
                        i++
                    }
                }
                else -> {
                    append(text[i])
                    i++
                }
            }
        }
    }
