"""Feature 027 — T011: chrome_render wire shape + FR-018 non-regression."""
import json

from shared.protocol import ChromeRender, UIRender


def test_chrome_render_wire_shape():
    msg = ChromeRender(region="modal", html="<div>x</div>")
    data = json.loads(msg.to_json())
    assert data["type"] == "chrome_render"
    assert data["region"] == "modal"
    assert data["html"] == "<div>x</div>"
    assert data["mode"] == "replace"


def test_chrome_render_topbar_region():
    data = json.loads(ChromeRender(region="topbar", html="<nav/>").to_json())
    assert data["region"] == "topbar"


def test_chrome_render_empty_html_means_close():
    data = json.loads(ChromeRender(region="modal", html="").to_json())
    assert data["html"] == ""


def test_fr018_ui_render_still_carries_components_and_html():
    """The 026 wire contract is untouched by the chrome addition (FR-018)."""
    msg = UIRender(components=[{"type": "text", "content": "hi"}], html="<p>hi</p>")
    data = json.loads(msg.to_json())
    assert data["type"] == "ui_render"
    assert data["components"] == [{"type": "text", "content": "hi"}]
    assert data["html"] == "<p>hi</p>"
    assert data["target"] == "canvas"
