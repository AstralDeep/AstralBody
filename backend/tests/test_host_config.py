"""033 Wave-0 (C-D2) — declarative per-target host-config + surface bounds.

The per-device rendering constraints are data (``_BASE_HOST_CONFIG`` +
``ROTE_HOST_CONFIG`` env overrides), and two of them — ``max_actions`` and
``supports_interactivity`` — bound what a surface may render. Defaults preserve
today's behavior. Pure Python.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rote import capabilities as cap  # noqa: E402
from rote.adapter import ComponentAdapter  # noqa: E402
from rote.capabilities import DeviceProfile, load_host_config  # noqa: E402


def _btn(label, action="do"):
    return {"type": "button", "label": label, "action": action, "payload": {}}


# --------------------------------------------------------------------------
# Declarative config
# --------------------------------------------------------------------------

def test_base_config_has_all_device_types_and_new_fields():
    cfg = load_host_config()
    for dt in ("browser", "tablet", "mobile", "watch", "tv", "voice"):
        assert dt in cfg
        assert "max_actions" in cfg[dt]
        assert "supports_interactivity" in cfg[dt]
    assert cfg["browser"]["supports_interactivity"] is True
    assert cfg["voice"]["supports_interactivity"] is False
    assert cfg["browser"]["max_actions"] == 0  # unlimited by default


def test_env_override_merges_partial(monkeypatch):
    monkeypatch.setenv("ROTE_HOST_CONFIG", '{"watch": {"max_actions": 2}}')
    cfg = load_host_config()
    assert cfg["watch"]["max_actions"] == 2
    # other watch fields untouched
    assert cfg["watch"]["supports_charts"] is False
    # other device types untouched
    assert cfg["browser"]["max_actions"] == 0


def test_env_override_ignores_bad_json(monkeypatch):
    monkeypatch.setenv("ROTE_HOST_CONFIG", "{not valid json")
    cfg = load_host_config()
    assert cfg == cap._BASE_HOST_CONFIG  # fell back to defaults


def test_env_override_rejects_unknown_keys_and_types(monkeypatch):
    monkeypatch.setenv(
        "ROTE_HOST_CONFIG",
        '{"watch": {"evil": 1, "max_actions": 3}, "fridge": {"max_actions": 9}}',
    )
    cfg = load_host_config()
    assert "evil" not in cfg["watch"]      # unknown field dropped
    assert cfg["watch"]["max_actions"] == 3
    assert "fridge" not in cfg             # unknown device type dropped


def test_profile_reflects_config_and_defaults():
    browser = DeviceProfile.from_dict({"device_type": "browser"})
    assert browser.max_actions == 0 and browser.supports_interactivity is True
    voice = DeviceProfile.from_dict({"device_type": "voice"})
    assert voice.supports_interactivity is False
    assert "max_actions" in browser.to_dict()


def test_env_override_flows_into_profile(monkeypatch):
    monkeypatch.setenv("ROTE_HOST_CONFIG", '{"tv": {"supports_interactivity": false}}')
    tv = DeviceProfile.from_dict({"device_type": "tv"})
    assert tv.supports_interactivity is False


# --------------------------------------------------------------------------
# Enforcement (the actual surface bound)
# --------------------------------------------------------------------------

def test_default_browser_keeps_all_actions():
    comps = [_btn("a"), _btn("b"), _btn("c")]
    out = ComponentAdapter.adapt(comps, DeviceProfile.from_dict({"device_type": "browser"}))
    assert sum(1 for c in out if c.get("type") == "button") == 3


def test_max_actions_caps_buttons(monkeypatch):
    monkeypatch.setenv("ROTE_HOST_CONFIG", '{"browser": {"max_actions": 2}}')
    comps = [_btn("a"), _btn("b"), _btn("c"), _btn("d")]
    out = ComponentAdapter.adapt(comps, DeviceProfile.from_dict({"device_type": "browser"}))
    assert sum(1 for c in out if c.get("type") == "button") == 2


def test_max_actions_counts_nested_buttons(monkeypatch):
    monkeypatch.setenv("ROTE_HOST_CONFIG", '{"browser": {"max_actions": 1}}')
    comps = [{"type": "container", "children": [_btn("a"), _btn("b")]}, _btn("c")]
    out = ComponentAdapter.adapt(comps, DeviceProfile.from_dict({"device_type": "browser"}))
    n = 0

    def count(node):
        nonlocal n
        if isinstance(node, dict):
            if node.get("type") == "button":
                n += 1
            for k in ("children", "content"):
                for ch in node.get(k, []) or []:
                    count(ch)
    for c in out:
        count(c)
    assert n == 1  # only the first action-button survives the budget


def test_read_only_surface_strips_action_buttons(monkeypatch):
    # Make a normally-interactive surface (mobile) read-only via host-config —
    # TV/voice already drop buttons in _adapt_button, so use mobile to prove the
    # host-bound is what does the stripping.
    monkeypatch.setenv("ROTE_HOST_CONFIG", '{"mobile": {"supports_interactivity": false}}')
    comps = [{"type": "text", "content": "hi", "variant": "body"}, _btn("a")]
    out = ComponentAdapter.adapt(comps, DeviceProfile.from_dict({"device_type": "mobile"}))
    assert all(c.get("type") != "button" for c in out)
    assert any(c.get("type") == "text" for c in out)  # non-interactive content kept


def test_non_action_buttons_are_not_stripped(monkeypatch):
    # A button with no action isn't an interactive action — left alone even on a
    # read-only surface.
    monkeypatch.setenv("ROTE_HOST_CONFIG", '{"mobile": {"supports_interactivity": false}}')
    comps = [{"type": "button", "label": "inert"}]
    out = ComponentAdapter.adapt(comps, DeviceProfile.from_dict({"device_type": "mobile"}))
    assert len(out) == 1
