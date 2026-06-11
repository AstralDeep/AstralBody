"""Server-driven welcome canvas (orchestrator/welcome.py).

The initial-load examples are ordinary astralprims components delivered over
the normal ui_render path — renderable by the registry, adaptable by ROTE,
actionable through the standard ``chat_message`` ui_event. No shell HTML, no
client-specific code (Constitution II).
"""
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from orchestrator.welcome import WELCOME_EXAMPLES, welcome_components  # noqa: E402


def _walk(nodes):
    for node in nodes:
        if not isinstance(node, dict):
            continue
        yield node
        for key in ("children", "content"):
            nested = node.get(key)
            if isinstance(nested, list):
                yield from _walk(nested)


def test_every_type_is_renderable():
    import webrender

    allowed = webrender.allowed_primitive_types()
    comps = welcome_components()
    types = {n["type"] for n in _walk(comps)}
    assert types <= allowed, f"non-renderable welcome types: {types - allowed}"


def test_structure_hero_grid_examples():
    comps = welcome_components()
    assert comps[0]["type"] == "hero"
    grid = comps[1]
    assert grid["type"] == "grid"
    assert len(grid["children"]) == len(WELCOME_EXAMPLES)
    assert json.dumps(comps), "wire-serializable"


def test_buttons_dispatch_standard_chat_message_action():
    buttons = [n for n in _walk(welcome_components()) if n["type"] == "button"]
    assert len(buttons) == len(WELCOME_EXAMPLES)
    queries = {b["payload"]["message"] for b in buttons}
    assert all(b["action"] == "chat_message" for b in buttons)
    assert queries == {q for _, _, q in WELCOME_EXAMPLES}
    assert all(q.strip() for q in queries)


def test_welcome_components_carry_no_workspace_identity():
    for node in _walk(welcome_components()):
        assert "component_id" not in node, "welcome is ephemeral — never persisted"


def test_voice_profile_gets_readable_text():
    from rote.adapter import ComponentAdapter

    text = " ".join(
        ComponentAdapter._extract_text(c) for c in welcome_components()
    )
    assert "What would you like to build?" in text
    for title, _, _ in WELCOME_EXAMPLES:
        assert title.split(" ", 1)[1] in text, f"example {title!r} unreadable on voice"
