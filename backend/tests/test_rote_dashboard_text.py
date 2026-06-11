"""ROTE voice-profile text extraction for the dashboard primitives
(badge, hero, keyvalue, timeline, rating) — feature 029 follow-up.

Without these branches the VOICE profile silently drops the new types.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rote.adapter import ComponentAdapter  # noqa: E402


def _t(comp):
    return ComponentAdapter._extract_text(comp)


def test_badge_text():
    assert _t({"type": "badge", "label": "Confirmed"}) == "Confirmed"


def test_hero_text():
    out = _t({"type": "hero", "title": "Paws & Bubbles", "eyebrow": "Dashboard",
              "subtitle": "Today at a glance", "badges": ["Open", "8 bookings"]})
    assert "Paws & Bubbles" in out and "Dashboard" in out
    assert "Today at a glance" in out and "Open, 8 bookings" in out


def test_keyvalue_text():
    out = _t({"type": "keyvalue", "title": "Facts",
              "items": [{"label": "Owner", "value": "Sam"}]})
    assert "Facts" in out and "Owner: Sam" in out


def test_timeline_text():
    out = _t({"type": "timeline", "title": "Today", "items": [
        {"time": "9:00", "title": "Bella", "description": "Full groom"},
        {"title": "Walk-in"},
    ]})
    assert "Today" in out
    assert "9:00 — Bella: Full groom" in out
    assert "Walk-in" in out


def test_rating_text():
    out = _t({"type": "rating", "label": "Satisfaction", "value": 4.8, "max_value": 5})
    assert out == "Satisfaction: 4.8 out of 5 stars"
