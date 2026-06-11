"""Feature 026 — T016: golden/structural render tests for all primitive types.

Asserts each of the 25 astralprims primitive types renders to the expected web
HTML structure (tag + key Astral classes) and that children recurse. Structural
invariants (not byte-exact fixtures) so the suite is robust to incidental markup
tweaks while still proving parity-relevant structure.
"""
import astralprims as ap
import webrender


def r(primitive):
    return webrender.render_one(primitive.to_dict())


def test_container_emits_children_no_wrapper():
    html = r(ap.Container(children=[ap.Text(content="inner")]))
    assert "inner" in html and "text-astral-text" in html


def test_text_variants():
    assert '<h1 class="text-2xl font-bold text-astral-text">Hi</h1>' == r(ap.Text(content="Hi", variant="h1"))
    assert "<p class=\"text-sm text-astral-text leading-relaxed\">body</p>" == r(ap.Text(content="body"))
    assert '<span class="text-xs text-astral-muted">' in r(ap.Text(content="c", variant="caption")) or \
        "text-astral-muted" in r(ap.Text(content="c", variant="caption"))


def test_button_carries_action_payload():
    html = r(ap.Button(label="Go", action="chat_message", payload={"x": 1}, variant="primary"))
    assert 'class="astral-action' in html and 'data-action="chat_message"' in html
    assert "bg-astral-primary" in html and "Go" in html
    assert "&quot;x&quot;" in html  # payload JSON escaped into the attribute


def test_card_title_accent_and_children():
    html = r(ap.Card(title="T", content=[ap.Text(content="body")]))
    assert "bg-astral-primary inline-block" in html  # accent pill
    assert 'class="space-y-3"' in html and "body" in html


def test_table_headers_rows_and_pagination():
    t = ap.Table(headers=["A", "B"], rows=[["1", "2"]], total_rows=100, page_size=25,
                 page_offset=0, source_tool="tool", source_agent="agent")
    html = r(t)
    assert "<table" in html and "<thead" in html and "<tbody" in html
    assert ">A<" in html and ">1<" in html
    assert "astral-pagination" in html and "astral-page-next" in html and "1–25 of 100" in html


def test_table_cell_severity_badges_and_links():
    html = r(ap.Table(headers=["S"], rows=[["Critical"], ["https://x.com"]]))
    assert "bg-red-500/20" in html  # Critical badge
    assert 'target="_blank"' in html and "https://x.com" in html


def test_list_default_and_detailed():
    assert "<ul" in r(ap.List_(items=["a", "b"]))
    assert "<ol" in r(ap.List_(items=["a"], ordered=True))
    det = r(ap.List_(variant="detailed", items=[{"title": "T", "subtitle": "S", "description": "D", "url": "https://u.co"}]))
    assert "T" in det and "S" in det and 'href="https://u.co"' in det


def test_alert_variants_icon_and_block_message():
    html = r(ap.Alert(message="msg **b**", variant="warning", title="Title"))
    assert "bg-yellow-500/10" in html and "<svg" in html
    assert "<strong" in html  # block markdown bolded


def test_progress_fill_and_label():
    html = r(ap.ProgressBar(value=0.5, label="L"))
    assert "from-astral-primary to-astral-secondary" in html and "width:50" in html and "50%" in html


def test_metric_variant_gradient_and_progress_threshold():
    assert "from-red-500/20" in r(ap.MetricCard(title="x", value="1", variant="error"))
    assert "bg-red-500" in r(ap.MetricCard(title="x", value="1", progress=0.95))  # >0.9 red


def test_code_block_escaped_green():
    html = r(ap.CodeBlock(code="print('<x>')", language="python"))
    assert "text-green-400" in html and "&lt;x&gt;" in html and "python" in html


def test_image_and_input_basic():
    assert "<img" in r(ap.Image(url="https://i.co/a.png", alt="a"))
    assert "<input" in r(ap.Input(name="n", value="v"))


def test_grid_responsive_columns():
    html = r(ap.Grids(columns=3, children=[ap.Text(content="a")]))
    assert "lg:grid-cols-3" in html and "gap:20px" in html


def test_tabs_and_divider_and_collapsible():
    assert "<details" in r(ap.Tabs(tabs=[ap.TabItem(label="T1", content=[ap.Text(content="x")])]))
    assert r(ap.Divider()) == '<hr class="border-white/10 my-3"/>'
    coll = r(ap.Collapsible(title="More", content=[ap.Text(content="hidden")], default_open=True))
    assert "<details" in coll and " open" in coll and "hidden" in coll


def test_charts_emit_plotly_placeholders():
    bar = r(ap.BarChart(title="B", labels=["x"], datasets=[{"label": "d", "data": [1]}]))
    assert 'data-chart-type="bar"' in bar and "astral-chart" in bar
    assert 'data-chart-type="line"' in r(ap.LineChart(labels=["x"], datasets=[{"data": [1]}]))
    assert 'data-chart-type="pie"' in r(ap.PieChart(labels=["x"], data=[1]))
    assert 'data-chart-type="plotly"' in r(ap.PlotlyChart(data=[{"x": [1], "y": [1]}]))


def test_color_picker_and_theme_apply():
    cp = r(ap.ColorPicker(label="Primary", color_key="primary", value="#112233"))
    assert 'type="color"' in cp and 'data-color-key="primary"' in cp and "#112233" in cp
    ta = r(ap.ThemeApply(preset="ocean", message="done"))
    assert "astral-theme-apply" in ta and "data-theme=" in ta and "done" in ta


def test_file_upload_download_and_audio():
    assert "astral-file-upload" in r(ap.FileUpload(label="Up"))
    valid = r(ap.FileDownload(label="Get", url="https://f.co/x.csv", filename="x.csv"))
    assert 'href="https://f.co/x.csv"' in valid and "bg-astral-secondary/20" in valid
    invalid = r(ap.FileDownload(label="Get", url=""))
    assert "disabled" in invalid and "cursor-not-allowed" in invalid
    aud = r(ap.Audio(src="https://a.co/s.mp3", contentType="audio/mpeg", label="L"))
    assert "<audio" in aud and 'type="audio/mpeg"' in aud and "controls" in aud
    assert "No audio source provided" in r(ap.Audio(src=""))


def test_render_wraps_list_in_dynamic_renderer():
    html = webrender.render([ap.Text(content="a").to_dict(), ap.Alert(message="b").to_dict()])
    assert html.startswith('<div class="dynamic-renderer space-y-3">') and html.endswith("</div>")
