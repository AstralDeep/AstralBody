"""Feature 026 — T031/T032: graceful handling of unknown targets and
unsupported primitive types (FR-013 / FR-014). A bad component must never crash
a whole response.
"""
import astralprims as ap
import webrender
from webrender import render_for_target


def test_unsupported_primitive_renders_placeholder_not_crash():
    html = webrender.render_one({"type": "totally-unknown", "foo": "bar"})
    assert "astral-unsupported" in html and "totally-unknown" in html
    assert "<script" not in html.lower()


def test_unsupported_primitive_does_not_break_siblings():
    comps = [ap.Text(content="before").to_dict(), {"type": "mystery"}, ap.Text(content="after").to_dict()]
    html = webrender.render(comps)
    assert "before" in html and "after" in html and "astral-unsupported" in html


def test_renderer_swallows_malformed_component():
    # a component whose fields are the wrong shape must degrade, not raise
    html = webrender.render_one({"type": "table", "rows": "not-a-list"})
    assert isinstance(html, str)  # no exception escaped


def test_unknown_target_falls_back_to_web():
    comps = [ap.Text(content="x").to_dict()]
    out = render_for_target("nonexistent-device", comps, None)
    assert isinstance(out, str) and "dynamic-renderer" in out  # defined fallback = web


def test_known_web_target():
    out = render_for_target("web", [ap.Text(content="x").to_dict()], None)
    assert "dynamic-renderer" in out
