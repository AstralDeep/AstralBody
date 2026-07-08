package com.personalailabs.astraldeep.app.render

import androidx.compose.ui.text.LinkAnnotation
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Feature 044 T029 — inline `[label](url)` markdown links become URL annotations. */
class MarkdownTest {
    @Test
    fun link_produces_a_url_annotation_and_inlines_the_label() {
        val a = inlineMarkdown("see [Google](https://google.com) now")
        assertEquals("see Google now", a.text)
        val links = a.getLinkAnnotations(0, a.length)
        assertEquals(1, links.size)
        assertEquals("https://google.com", (links.first().item as LinkAnnotation.Url).url)
    }

    @Test
    fun plain_text_is_unchanged_and_has_no_links() {
        val a = inlineMarkdown("just plain text")
        assertEquals("just plain text", a.text)
        assertTrue(a.getLinkAnnotations(0, a.length).isEmpty())
    }

    @Test
    fun bold_and_code_still_work_alongside_a_link() {
        val a = inlineMarkdown("**bold** `x` and [docs](http://d)")
        assertEquals("bold x and docs", a.text)
        assertEquals(1, a.getLinkAnnotations(0, a.length).size)
    }

    @Test
    fun a_malformed_link_stays_literal() {
        val a = inlineMarkdown("[no paren] here")
        assertEquals("[no paren] here", a.text)
        assertTrue(a.getLinkAnnotations(0, a.length).isEmpty())
    }
}
