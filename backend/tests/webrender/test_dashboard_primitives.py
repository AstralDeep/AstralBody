"""Feature 029 follow-up — structural render tests for the dashboard
primitives (badge, hero, keyvalue, timeline, rating).

Components are plain dicts (not astralprims instances) so the suite passes
regardless of the installed astralprims version — the renderer consumes
dicts either way, and these types ship with astralprims 0.2.0.
"""
import webrender
from webrender import render_one


def test_dashboard_types_registered():
    allowed = webrender.allowed_primitive_types()
    assert {"badge", "hero", "keyvalue", "timeline", "rating"} <= allowed


def test_badge_variant_and_escaping():
    html = render_one({"type": "badge", "label": "<b>Open</b>", "variant": "success"})
    assert "astral-badge--success" in html
    assert "&lt;b&gt;Open&lt;/b&gt;" in html and "<b>" not in html


def test_badge_unknown_variant_defaults():
    html = render_one({"type": "badge", "label": "x", "variant": 'evil" onload="x'})
    assert "astral-badge--default" in html
    assert "onload" not in html


def test_hero_full_band():
    html = render_one({"type": "hero", "title": "Paws & Bubbles", "eyebrow": "Dashboard",
                       "subtitle": "Today at a glance", "variant": "gradient",
                       "badges": ["Open", "8 bookings"]})
    assert "astral-hero--gradient" in html
    assert "Paws &amp; Bubbles" in html
    assert "Dashboard" in html and "Today at a glance" in html
    assert html.count("astral-badge") >= 2


def test_hero_unknown_variant_defaults():
    html = render_one({"type": "hero", "title": "T", "variant": "<script>"})
    assert "astral-hero--default" in html and "<script>" not in html


def test_keyvalue_items_and_columns():
    html = render_one({"type": "keyvalue", "title": "Facts", "columns": 3, "items": [
        {"label": "Owner", "value": "Sam <admin>", "hint": "since 2021"},
        {"label": "Staff", "value": 4},
    ]})
    assert "astral-kv" in html and "lg:grid-cols-3" in html
    assert "Sam &lt;admin&gt;" in html and "since 2021" in html
    assert "<dt" in html and "<dd" in html


def test_keyvalue_empty_renders_nothing():
    assert render_one({"type": "keyvalue", "items": []}) == ""


def test_timeline_items_variants_and_escaping():
    html = render_one({"type": "timeline", "title": "Today", "items": [
        {"time": "9:00 AM", "title": "Bella — Full Groom", "variant": "success",
         "description": "Golden Retriever"},
        {"title": "<img onerror=x>", "variant": "bogus"},
    ]})
    assert "astral-timeline" in html
    assert "astral-tl-item--success" in html
    assert "astral-tl-item--default" in html, "unknown item variant defaults"
    assert "9:00 AM" in html and "Golden Retriever" in html
    assert "&lt;img onerror=x&gt;" in html and "<img" not in html


def test_timeline_empty_renders_nothing():
    assert render_one({"type": "timeline", "items": []}) == ""


def test_rating_stars_clamped_and_value():
    html = render_one({"type": "rating", "value": 4.8, "label": "Satisfaction"})
    assert html.count("astral-star--filled") == 5  # 4.8 rounds to 5 of 5
    assert "4.8/5" in html and "Satisfaction" in html

    html = render_one({"type": "rating", "value": 99, "max_value": 4})
    assert html.count("astral-star--filled") == 4, "value clamps to max"
    assert html.count('class="astral-star"') == 0, "no unfilled stars remain"

    html = render_one({"type": "rating", "value": "junk", "max_value": "junk"})
    assert html.count("astral-star--filled") == 0, "garbage inputs degrade to zero"


def test_rating_hide_value():
    html = render_one({"type": "rating", "value": 3, "show_value": False})
    assert "3/5" not in html


def test_nonfinite_numbers_degrade_gracefully():
    html = render_one({"type": "keyvalue", "columns": float("nan"),
                       "items": [{"label": "a", "value": "1"}]})
    assert "astral-render-error" not in html and "astral-kv" in html

    html = render_one({"type": "rating", "value": float("nan"), "max_value": float("inf")})
    assert "astral-render-error" not in html
    assert html.count("astral-star--filled") == 0

    html = render_one({"type": "badge", "label": "x", "variant": ["not", "hashable"]})
    assert "astral-render-error" not in html and "astral-badge--default" in html


def test_dashboard_types_honor_morph_anchors():
    for comp in (
        {"type": "badge", "label": "x"},
        {"type": "hero", "title": "x"},
        {"type": "keyvalue", "items": [{"label": "a", "value": "1"}]},
        {"type": "timeline", "items": [{"title": "x"}]},
        {"type": "rating", "value": 1},
    ):
        comp = dict(comp, attributes={"data-component-id": "wc_anchor", "onclick": "alert(1)"})
        html = render_one(comp)
        assert 'data-component-id="wc_anchor"' in html, comp["type"]
        assert "onclick" not in html, comp["type"]
