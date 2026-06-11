"""Feature 026 — T018: the UI render protocol carries server-rendered `html`
alongside the structured `components`, and round-trips over the wire.
"""
import json

import astralprims as ap
import webrender
from shared.protocol import Message, UIRender, UIUpdate


def test_uirender_carries_html_and_components():
    comps = [ap.Text(content="hi").to_dict(), ap.Alert(message="m").to_dict()]
    html = webrender.render_for_target("web", comps, None)
    msg = UIRender(components=comps, target="canvas", html=html)
    wire = msg.to_json()
    data = json.loads(wire)
    assert data["type"] == "ui_render"
    assert data["target"] == "canvas"
    assert data["components"] == comps          # structured form preserved (FR-018)
    assert data["html"].startswith("<div class=\"dynamic-renderer")
    # round-trips back into a UIRender via the protocol parser
    parsed = Message.from_json(wire)
    assert isinstance(parsed, UIRender) and parsed.html == html


def test_uiupdate_carries_html():
    comps = [ap.MetricCard(title="t", value="1").to_dict()]
    msg = UIUpdate(components=comps, html=webrender.render_for_target("web", comps, None))
    data = json.loads(msg.to_json())
    assert data["type"] == "ui_update" and data["html"] and data["components"] == comps


def test_stream_chunk_wire_shape():
    # mirrors stream_manager._send_chunk_to_subscribers wire_msg
    comps = [ap.Text(content="chunk").to_dict()]
    wire = {
        "type": "ui_stream_data", "stream_id": "s1", "session_id": "c1", "seq": 3,
        "components": comps, "html": webrender.render_for_target("web", comps, None),
        "raw": None, "terminal": False, "error": None,
    }
    blob = json.dumps(wire)
    back = json.loads(blob)
    assert back["html"] and back["components"] == comps and back["seq"] == 3


def test_html_absent_consumer_still_has_components():
    # a programmatic/non-web consumer ignores html and reads components (FR-018)
    comps = [ap.Table(headers=["A"], rows=[["1"]]).to_dict()]
    msg = UIRender(components=comps)  # no html
    data = json.loads(msg.to_json())
    assert data["html"] is None and data["components"] == comps
