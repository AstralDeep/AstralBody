"""Feature 028 — workspace fragment rendering + ui_upsert/auth_required protocol.

Covers the renderer side of partial workspace updates (research D12): every
top-level workspace component renders inside a ``data-component-id`` identity
wrapper (the morph target for ``ui_upsert``), legacy components without an
identity render unwrapped, and the identity attribute is escape-by-default
(026 FR-017). Protocol layer: ``UIUpsert``/``AuthRequired`` round-trip through
``Message.from_json`` and the pre-028 ``UIRender``/``UIUpdate`` shapes still
parse (additive contract — 028 FR-024 / 026 FR-018).
"""
import json

from shared.protocol import (
    AuthRequired,
    Message,
    UIRender,
    UIUpdate,
    UIUpsert,
)
from webrender import render, render_component_fragment, render_one, render_workspace


def _card(title: str, body: str, **extra):
    comp = {
        "type": "card",
        "title": title,
        "content": [{"type": "text", "variant": "body", "content": body}],
    }
    comp.update(extra)
    return comp


# ---------------------------------------------------------------------------
# render_component_fragment — identity wrapper (research D12, 028 FR-019)
# ---------------------------------------------------------------------------

def test_fragment_with_component_id_wraps_card_markup(monkeypatch):
    """028 FR-019: a component bearing an identity renders inside its
    data-component-id anchor with the unchanged card markup inside. (The 033
    C-U6 provenance footer is a separate, flag-gated addition covered in
    tests/webrender/test_provenance.py; disabled here to assert wrapper parity.)"""
    monkeypatch.setenv("FF_PROVENANCE_SURFACING", "false")
    comp = _card("Vitals", "all good", component_id="wc_x")
    out = render_component_fragment(comp)
    assert out.startswith('<div class="astral-component" data-component-id="wc_x">')
    assert out.endswith("</div>")
    inner = render_one(comp)
    assert inner  # the card actually rendered
    # the wrapper contains exactly the legacy card markup
    assert out == f'<div class="astral-component" data-component-id="wc_x">{inner}</div>'


def test_fragment_without_component_id_is_legacy_parity(monkeypatch):
    """028 FR-019 (legacy parity): no identity -> no wrapper; output equals
    render_one exactly (with the C-U6 provenance footer off)."""
    monkeypatch.setenv("FF_PROVENANCE_SURFACING", "false")
    comp = _card("Vitals", "all good")
    out = render_component_fragment(comp)
    assert out == render_one(comp)
    assert "astral-component" not in out
    assert "data-component-id" not in out


def test_fragment_non_dict_renders_empty():
    """028 FR-019: defensive — non-dict input yields an empty fragment."""
    assert render_component_fragment(None) == ""
    assert render_component_fragment("text") == ""


def test_component_id_attribute_is_escaped():
    """026 FR-017 escape preservation: a hostile component_id cannot break out
    of the data-component-id attribute or inject a raw <script> tag."""
    hostile = '"x"><script>alert(1)</script>'
    comp = _card("T", "b", component_id=hostile)
    out = render_component_fragment(comp)
    assert "<script" not in out
    assert "</script>" not in out
    # the value is fully entity-escaped inside the attribute
    assert 'data-component-id="&quot;x&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;"' in out
    # the raw unescaped quote+bracket sequence never appears
    assert '"x">' not in out


def test_unknown_type_in_fragment_emits_placeholder_never_raises():
    """026 FR-014: an unknown component type inside an identity fragment still
    emits the astral-unsupported placeholder instead of raising."""
    comp = {"type": "flux_capacitor", "component_id": "wc_u"}
    out = render_component_fragment(comp)  # must not raise
    assert 'data-component-id="wc_u"' in out
    assert "astral-unsupported" in out
    assert "flux_capacitor" in out


# ---------------------------------------------------------------------------
# render_workspace — full-workspace identity render (028 FR-021/FR-025)
# ---------------------------------------------------------------------------

def test_render_workspace_wraps_each_component_in_order():
    """028 FR-019/FR-021: a workspace render carries one identity wrapper per
    component, in component order, inside the dynamic-renderer root."""
    comps = [
        _card("First", "one", component_id="wc_a"),
        _card("Second", "two", component_id="wc_b"),
    ]
    out = render_workspace(comps)
    assert out.startswith('<div class="dynamic-renderer space-y-3">')
    assert out.endswith("</div>")
    pos_a = out.find('data-component-id="wc_a"')
    pos_b = out.find('data-component-id="wc_b"')
    assert pos_a != -1 and pos_b != -1
    assert pos_a < pos_b  # order preserved
    # the inner card markup is byte-identical to the legacy render path
    plain = render(comps)
    for comp in comps:
        inner = render_one(comp)
        assert inner in out
        assert inner in plain


def test_render_workspace_without_ids_equals_render(monkeypatch):
    """028 FR-019 (legacy parity): with no identities present, render_workspace
    output is byte-identical to render(). (With the 033 C-U6 provenance footer
    off — that footer is a canvas-only addition, tested separately.)"""
    monkeypatch.setenv("FF_PROVENANCE_SURFACING", "false")
    comps = [_card("Plain", "no id"), {"type": "text", "content": "hello"}]
    assert render_workspace(comps) == render(comps)


def test_render_workspace_empty_and_none():
    """028 FR-021: empty/None workspaces render the bare root container."""
    assert render_workspace([]) == '<div class="dynamic-renderer space-y-3"></div>'
    assert render_workspace(None) == '<div class="dynamic-renderer space-y-3"></div>'


# ---------------------------------------------------------------------------
# Protocol — UIUpsert / AuthRequired round-trip; additive contract
# ---------------------------------------------------------------------------

def test_ui_upsert_round_trips_through_message_from_json():
    """028 FR-024: ui_upsert carries chat_id + ops (structured component AND
    html projection per op) and round-trips through Message.from_json."""
    ops = [
        {
            "op": "upsert",
            "component_id": "wc_1",
            "component": _card("Live", "v2", component_id="wc_1"),
            "html": render_component_fragment(_card("Live", "v2", component_id="wc_1")),
        },
        {"op": "remove", "component_id": "wc_2"},
    ]
    msg = UIUpsert(chat_id="c", ops=ops)
    wire = msg.to_json()
    data = json.loads(wire)
    assert data["type"] == "ui_upsert"
    assert data["chat_id"] == "c"
    assert data["ops"] == ops  # structured layer intact on the wire (026 FR-018)
    parsed = Message.from_json(wire)
    assert isinstance(parsed, UIUpsert)
    assert parsed.chat_id == "c"
    assert parsed.ops == ops


def test_auth_required_round_trips():
    """028 FR-009: auth_required (the dead-end-alert replacement) round-trips
    with its reason intact."""
    wire = AuthRequired(reason="expired").to_json()
    parsed = Message.from_json(wire)
    assert isinstance(parsed, AuthRequired)
    assert parsed.type == "auth_required"
    assert parsed.reason == "expired"
    # default reason
    parsed_default = Message.from_json(AuthRequired().to_json())
    assert isinstance(parsed_default, AuthRequired)
    assert parsed_default.reason == "invalid"


def test_legacy_ui_render_and_ui_update_shapes_still_parse():
    """026 FR-018 / 028 FR-024 (additive contract): pre-028 UIRender/UIUpdate
    wire shapes — including the pre-026 shape without `html` — still parse."""
    comps = [{"type": "text", "content": "hi"}]
    # pre-026 shape: no html key at all
    old_render = json.dumps({"type": "ui_render", "components": comps, "target": "canvas"})
    parsed = Message.from_json(old_render)
    assert isinstance(parsed, UIRender)
    assert parsed.components == comps and parsed.target == "canvas" and parsed.html is None

    old_update = json.dumps({"type": "ui_update", "components": comps})
    parsed_u = Message.from_json(old_update)
    assert isinstance(parsed_u, UIUpdate)
    assert parsed_u.components == comps and parsed_u.html is None

    # current 026 shape (with html) is unchanged by 028
    cur = UIRender(components=comps, target="chat", html="<div></div>")
    back = Message.from_json(cur.to_json())
    assert isinstance(back, UIRender)
    assert back.html == "<div></div>" and back.target == "chat" and back.components == comps
