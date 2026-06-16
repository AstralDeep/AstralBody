"""Feature 037 — server-driven, cross-device loading skeleton tests.

Covers the webrender ``skeleton`` primitive (renderer + builder + registry) and
its ROTE adaptation across device targets (voice collapses to speech; watch /
mobile cap the row count; browser/tv pass through). Pure Python — no DB, no
network.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rote.adapter import ComponentAdapter  # noqa: E402
from rote.capabilities import DeviceProfile  # noqa: E402
from webrender.renderer import (  # noqa: E402
    allowed_primitive_types,
    render_one,
    render_skeleton,
    skeleton_component,
)


def _profile(device_type: str) -> DeviceProfile:
    return DeviceProfile.from_dict({"device_type": device_type})


# ───────────────────────── renderer ──────────────────────────────────────────

def test_skeleton_is_a_recognized_primitive():
    assert "skeleton" in allowed_primitive_types()


def test_render_skeleton_structure_and_a11y():
    html = render_skeleton({"type": "skeleton", "variant": "chat-history",
                            "count": 3, "label": "Loading chats…"})
    assert 'role="status"' in html and 'aria-busy="true"' in html
    assert 'aria-live="polite"' in html
    assert "Loading chats…" in html              # sr-only accessible label
    # a chat-history/list row carries 3 shimmer lines (avatar + title + subtitle)
    assert html.count("astral-skeleton-line") == 9


def test_render_skeleton_count_is_bounded():
    many = render_skeleton({"type": "skeleton", "variant": "lines", "count": 100})
    assert many.count("astral-skeleton-line") == 12   # capped at _SKELETON_MAX_ROWS
    one = render_skeleton({"type": "skeleton", "variant": "lines", "count": 0})
    assert one.count("astral-skeleton-line") == 1     # floored at 1


def test_render_skeleton_bad_count_defaults():
    html = render_skeleton({"type": "skeleton", "variant": "lines", "count": "nope"})
    assert html.count("astral-skeleton-line") == 4    # default


def test_render_skeleton_escapes_label():
    html = render_skeleton({"type": "skeleton", "label": "<script>x</script>"})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_one_dispatches_skeleton():
    html = render_one({"type": "skeleton", "count": 2})
    assert "astral-skeleton" in html
    assert "unsupported" not in html


def test_skeleton_component_builder():
    assert skeleton_component(variant="chat-history", count=6, label="Loading…") == {
        "type": "skeleton", "variant": "chat-history", "count": 6, "label": "Loading…"}
    assert skeleton_component(count="bad")["count"] == 4   # builder coerces


# ───────────────────────── ROTE adaptation ───────────────────────────────────

def test_rote_voice_speaks_the_loading_state():
    out = ComponentAdapter.adapt(
        [skeleton_component("chat-history", 5, "Loading chats…")], _profile("voice"))
    assert len(out) == 1
    assert out[0]["type"] == "text"
    assert "Loading chats" in out[0]["content"]


def test_rote_watch_caps_row_count():
    out = ComponentAdapter.adapt([skeleton_component("list", 8)], _profile("watch"))
    assert out[0]["type"] == "skeleton"
    assert out[0]["count"] == 3


def test_rote_mobile_caps_row_count():
    out = ComponentAdapter.adapt([skeleton_component("list", 9)], _profile("mobile"))
    assert out[0]["count"] == 5


def test_rote_browser_passes_through_unchanged():
    out = ComponentAdapter.adapt([skeleton_component("list", 7)], _profile("browser"))
    assert out[0]["type"] == "skeleton"
    assert out[0]["count"] == 7


def test_rote_tv_passes_through_unchanged():
    out = ComponentAdapter.adapt([skeleton_component("list", 10)], _profile("tv"))
    assert out[0]["count"] == 10
