"""Feature 026 — T033 / SC-005 / FR-011: prove the multi-target seam.

Adding a new client target requires only registering a renderer — no change to
astralprims primitive definitions or agent code. The stub target renders the SAME
structured representation the web renderer consumes.
"""
import astralprims as ap
import webrender
from webrender import register_target, render_for_target, TARGET_RENDERERS


def test_stub_target_installs_and_renders_same_structured_form():
    from webrender.targets import stub_renderer
    stub_renderer.install()
    assert "stubtext" in TARGET_RENDERERS

    comps = [ap.Text(content="hello").to_dict(), ap.Card(title="ignored", content=[]).to_dict()]
    out = render_for_target("stubtext", comps, None)
    # stub renders only text primitives, from the same dicts the web renderer uses
    assert out == "hello"
    # the web target renders the full structure from the identical input
    web = render_for_target("web", comps, None)
    assert "hello" in web and "dynamic-renderer" in web


def test_registering_target_does_not_touch_primitive_definitions():
    before = ap.Text(content="x").to_dict()
    register_target("ephemeral", lambda comps, profile: "ok")
    after = ap.Text(content="x").to_dict()
    assert before == after  # astralprims definitions untouched
    assert render_for_target("ephemeral", [], None) == "ok"


def test_primitive_renderer_lookup():
    assert webrender.get_renderer("text") is not None
    assert webrender.get_renderer("does-not-exist") is None
