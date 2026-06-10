"""Markdown pipe tables + horizontal rules in ``block_md`` (escape-by-default).

Chat responses frequently contain GFM pipe tables (e.g. weather metric/value
tables); these previously fell through to paragraph handling and rendered as
literal ``|`` text. Same structural/behavioral style as test_escaping.py.
"""
from webrender.sanitize import block_md

XSS = '<script>alert(1)</script><img src=x onerror=alert(2)>'

TABLE = (
    "| Metric | Value |\n"
    "|---|---|\n"
    "| 🌡️ **Temperature** | 83.7°F |\n"
    "| Humidity | 72% |"
)


def test_pipe_table_renders_table_markup():
    out = block_md(TABLE)
    assert "<table" in out and "<thead" in out and "<tbody>" in out
    assert "<th" in out and out.count("<tr") == 3
    assert ">Metric<" in out and ">Value<" in out
    # No literal pipes leak into the rendered output.
    assert "|" not in out


def test_pipe_table_cells_run_inline_md():
    out = block_md(TABLE)
    assert "<strong" in out and "Temperature" in out
    assert "🌡️" in out


def test_pipe_table_cells_escaped():
    out = block_md(f"| h |\n|---|\n| {XSS} |")
    assert "<script" not in out.lower() and "<img" not in out.lower()
    assert "&lt;script&gt;" in out


def test_pipe_table_alignment_classes():
    out = block_md("| a | b | c |\n|:---|:---:|---:|\n| 1 | 2 | 3 |")
    assert "text-left" in out and "text-center" in out and "text-right" in out


def test_pipe_table_ragged_rows_padded_and_truncated():
    out = block_md("| a | b |\n|---|---|\n| only-one |\n| 1 | 2 | extra |")
    assert out.count("<td") == 4  # short row padded, long row truncated
    assert "extra" not in out
    assert "only-one" in out


def test_pipe_table_without_delimiter_stays_paragraph():
    out = block_md("| a | b |\njust text")
    assert "<table" not in out
    assert "<p" in out


def test_pipe_table_column_count_mismatch_not_a_table():
    out = block_md("| a | b |\n|---|\n| 1 | 2 |")
    assert "<table" not in out


def test_pipe_table_ends_at_blank_line():
    out = block_md(TABLE + "\n\nafter text")
    assert "<table" in out
    assert "after text" in out and out.index("</table>") < out.index("after text")


def test_pipe_table_flushes_preceding_paragraph():
    out = block_md("intro line\n" + TABLE)
    assert "intro line" in out and "<table" in out
    assert out.index("intro line") < out.index("<table")


def test_horizontal_rule():
    out = block_md("above\n\n---\n\nbelow")
    assert "<hr" in out
    assert "above" in out and "below" in out


def test_table_delimiter_lookalike_without_pipes_is_hr_not_table():
    # "---" on its own (no pipe header above) renders as a rule, not a table.
    out = block_md("***")
    assert "<hr" in out and "<table" not in out


def test_existing_blocks_unaffected():
    out = block_md("# Title\n- item one\n- item two\n\npara **bold**")
    assert "<h1" in out and "<ul" in out and "<strong" in out


def test_table_body_stops_at_heading():
    out = block_md("| a | b |\n|---|---|\n| 1 | 2 |\n## Section | details")
    assert out.count("<tr") == 2  # header + one data row only
    assert "<h2" in out and "Section | details" in out


def test_table_body_stops_at_list_and_blockquote():
    out = block_md("| a | b |\n|---|---|\n| 1 | 2 |\n- item one | note\n- item two")
    assert out.count("<tr") == 2
    assert "<ul" in out and out.count("<li") == 2
    out2 = block_md("| a | b |\n|---|---|\n> quoted | text")
    assert "<blockquote" in out2 and out2.count("<tr") == 1


def test_table_body_break_loses_no_content():
    out = block_md("| a | b |\n|---|---|\n### Notes | are | important")
    assert "important" in out and "<h3" in out


def test_delimiter_row_requires_pipe():
    # A pipe-less dashes line is a rule, never a 1-column table delimiter.
    out = block_md("|wrapped|\n---\nafter")
    assert "<table" not in out
    assert "<hr" in out and "wrapped" in out and "after" in out


def test_escaped_pipe_inside_cells():
    out = block_md("| a \\| b | c |\n|---|---|\n| x \\| y | 2 |")
    assert "<table" in out and out.count("<th ") == 2
    assert "a | b" in out and "x | y" in out and ">2<" in out


def test_list_item_with_pipe_not_hijacked_as_table_header():
    out = block_md("- choose a | b\n--- | ---")
    assert "<table" not in out
    assert "<ul" in out and "choose a | b" in out
