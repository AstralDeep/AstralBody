"""Feature 026 — T017 / SC-008: escape-by-default output safety (FR-017).

Untrusted text content rendered to web HTML must be inert: no executable script,
no injected elements. The only path that emits markup from text is the narrow,
sanitized markdown opt-in (alert message / detailed-list description / text
'markdown' variant), which must strip scripts/handlers.
"""
import astralprims as ap
import webrender
from webrender.sanitize import inline_md, block_md

XSS = '<script>alert(1)</script><img src=x onerror=alert(2)>'


def _no_live_markup(html):
    low = html.lower()
    # The dangerous payload's angle brackets must be escaped — so no UNescaped
    # <script>/<img> tag can exist. (Escaped text like "&lt;img ... onerror=...&gt;"
    # is inert; the literal substring "onerror=" inside escaped text is harmless.)
    assert "<script" not in low, f"unescaped <script tag in: {html}"
    assert "<img" not in low, f"unescaped <img tag in: {html}"
    assert "&lt;script&gt;" in html  # confirms the payload was escaped, not dropped


def test_text_content_escaped():
    html = webrender.render_one(ap.Text(content=XSS).to_dict())
    _no_live_markup(html)


def test_table_cells_escaped():
    html = webrender.render_one(ap.Table(headers=[XSS], rows=[[XSS]]).to_dict())
    _no_live_markup(html)


def test_button_label_and_payload_escaped():
    html = webrender.render_one(ap.Button(label=XSS, action="x", payload={"k": XSS}).to_dict())
    assert "<script" not in html.lower()
    # payload serialized into an attribute must be attribute-escaped (no raw quotes/brackets)
    assert "&lt;script&gt;" in html


def test_code_block_escaped():
    html = webrender.render_one(ap.CodeBlock(code=XSS).to_dict())
    _no_live_markup(html)


def test_alert_message_markdown_is_sanitized():
    # block markdown is allowed for alert messages, but script/handlers are inert
    html = webrender.render_one(ap.Alert(message=XSS + " and **bold**").to_dict())
    assert "<script" not in html.lower() and "<img" not in html.lower()
    assert "&lt;script&gt;" in html
    assert "<strong" in html  # legitimate markdown still works


def test_inline_md_allows_safe_only():
    out = inline_md("**b** `c` [x](https://ok.co) " + XSS)
    assert "<strong" in out and "<code" in out and 'href="https://ok.co"' in out
    assert "<script" not in out.lower() and "<img" not in out.lower()
    assert "&lt;script&gt;" in out  # payload escaped, not executed


def test_inline_md_blocks_javascript_url():
    out = inline_md("[click](javascript:alert(1))")
    assert "javascript:" not in out  # unsafe scheme replaced with '#'
    assert 'href="#"' in out


def test_block_md_fenced_code_escaped():
    out = block_md("```\n<script>evil()</script>\n```")
    assert "<script" not in out.lower() and "&lt;script&gt;" in out


def test_audio_src_sanitized():
    html = webrender.render_one(ap.Audio(src="javascript:alert(1)").to_dict())
    assert "javascript:alert" not in html  # safe_url collapses to '#'
