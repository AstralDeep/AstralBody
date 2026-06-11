"""Feature 026 — T034 / FR-018: the astralprims structured representation is the
canonical intermediate; ROTE adapts it, the orchestrator renders it, and the
structured form stays readable by programmatic/non-web consumers.
"""
import astralprims as ap
import webrender
from rote.rote import ROTE
from rote.capabilities import DeviceType


def test_adapt_then_render_ordering_on_a_watch_profile():
    """ROTE adapts the dict tree first (e.g. charts->metric on a watch), THEN the
    renderer renders the already-adapted tree."""
    rote = ROTE()

    class _WS:  # ROTE keys profiles by the ws object
        pass
    ws = _WS()
    rote.register_device(ws, {"device_type": "watch", "viewport_width": 180})
    profile = rote.get_profile(ws)
    assert profile.device_type == DeviceType.WATCH and profile.supports_charts is False

    components = [ap.BarChart(title="B", labels=["a", "b"], datasets=[{"data": [1, 2]}]).to_dict()]
    adapted = rote.adapt(ws, components)
    # ROTE degraded the chart for the watch (no chart type survives)
    assert all(c.get("type") != "bar_chart" for c in adapted)
    # the renderer renders whatever ROTE produced — no chart placeholder on the watch
    html = webrender.render_for_target("web", adapted, profile)
    assert isinstance(html, str)
    assert 'data-chart-type="bar"' not in html


def test_browser_profile_is_passthrough_and_renders_chart():
    rote = ROTE()

    class _WS:
        pass
    ws = _WS()
    rote.register_device(ws, {"device_type": "browser", "viewport_width": 1920})
    components = [ap.BarChart(labels=["a"], datasets=[{"data": [1]}]).to_dict()]
    adapted = rote.adapt(ws, components)
    assert adapted == components  # browser fast-path: no mutation
    html = webrender.render_for_target("web", adapted, rote.get_profile(ws))
    assert 'data-chart-type="bar"' in html


def test_structured_components_are_plain_serializable_dicts():
    # programmatic consumers read the dict tree directly (no rendering needed)
    tree = ap.Card(title="t", content=[ap.Text(content="x"), ap.Table(headers=["A"], rows=[["1"]])]).to_dict()
    import json
    assert json.loads(json.dumps(tree)) == tree  # round-trips as plain JSON
    assert tree["type"] == "card" and tree["content"][1]["type"] == "table"
