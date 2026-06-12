"""ATX headings h1-h6 in ``block_md`` (escape-by-default).

Chat narratives frequently use deep headings (e.g. ``#### 1. Differences in
Methodology``); levels 4-6 previously fell through to paragraph handling and
rendered as literal ``#### `` text. Same structural/behavioral style as
test_markdown_blocks.py.
"""
from webrender.sanitize import block_md

XSS = '<script>alert(1)</script><img src=x onerror=alert(2)>'


def test_h4_renders_heading_element_with_classes():
    out = block_md("#### 1. Differences in Methodology")
    assert "<h4" in out and "</h4>" in out
    assert 'class="text-base font-semibold text-astral-text mb-2"' in out
    assert "1. Differences in Methodology" in out
    assert "####" not in out and "<p" not in out


def test_h5_renders_heading_element_with_classes():
    out = block_md("##### Details")
    assert "<h5" in out and "</h5>" in out
    assert 'class="text-sm font-semibold text-astral-text mb-2"' in out
    assert "#" not in out


def test_h6_renders_heading_element_with_classes():
    out = block_md("###### Fine print")
    assert "<h6" in out and "</h6>" in out
    assert 'class="text-sm font-medium text-astral-muted mb-2"' in out
    assert "#" not in out


def test_h1_to_h3_unchanged():
    out = block_md("# One\n## Two\n### Three")
    assert '<h1 class="text-2xl font-bold text-astral-text mb-2">One</h1>' in out
    assert '<h2 class="text-xl font-semibold text-astral-text mb-2">Two</h2>' in out
    assert '<h3 class="text-lg font-medium text-astral-text mb-2">Three</h3>' in out


def test_deep_heading_content_escaped():
    out = block_md(f"#### {XSS}")
    low = out.lower()
    assert "<script" not in low and "<img" not in low
    assert "&lt;script&gt;" in out
    assert out.startswith("<h4")


def test_deep_heading_content_runs_inline_md():
    out = block_md("##### **bold** and `code`")
    assert "<h5" in out and "<strong" in out and "<code" in out


def test_seven_hashes_is_not_a_heading():
    # CommonMark: ATX headings stop at six #'s; more stays plain text.
    out = block_md("####### nope")
    assert "<h" not in out.replace("<hr", "")  # no heading element
    assert "<p" in out and "####### nope" in out


def test_hashes_without_space_stay_paragraph():
    out = block_md("####NoSpace")
    assert "<h4" not in out
    assert "<p" in out and "####NoSpace" in out


def test_deep_heading_flushes_preceding_paragraph():
    out = block_md("intro line\n#### Section")
    assert "intro line" in out and "<h4" in out
    assert out.index("intro line") < out.index("<h4")


def test_table_body_stops_at_deep_heading():
    out = block_md("| a | b |\n|---|---|\n| 1 | 2 |\n#### Section | details")
    assert out.count("<tr") == 2  # header + one data row only
    assert "<h4" in out and "Section | details" in out
