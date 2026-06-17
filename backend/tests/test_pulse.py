"""Feature 033 (C-U8) — proactive Pulse digest + conversational scheduling."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dreaming import pulse  # noqa: E402


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("FF_PULSE_DIGEST", raising=False)
    assert pulse.pulse_enabled() is False
    monkeypatch.setenv("FF_PULSE_DIGEST", "on")
    assert pulse.pulse_enabled() is True


# ───────────────────────── digest ────────────────────────────────────────────

def test_build_digest_groups_by_category():
    items = [
        {"category": "goal", "title": "Ship 033", "salience": 0.9},
        {"category": "goal", "title": "Write tests", "salience": 0.5},
        {"category": "preference", "value": "dark mode", "salience": 0.3},
    ]
    cards = pulse.build_digest(items)
    titles = [c["title"] for c in cards]
    assert "Goal" in titles and "Preference" in titles
    goal_card = next(c for c in cards if c["title"] == "Goal")
    # both goal lines present, highest salience first
    assert goal_card["content"][0]["content"] == "• Ship 033"


def test_build_digest_dedups_and_bounds():
    items = [{"category": "goal", "title": "X", "salience": 0.5} for _ in range(4)]
    cards = pulse.build_digest(items)
    goal = next(c for c in cards if c["title"] == "Goal")
    assert len(goal["content"]) == 1  # deduped


def test_build_digest_max_cards():
    items = [{"category": f"c{i}", "title": f"t{i}", "salience": 0.5} for i in range(10)]
    assert len(pulse.build_digest(items, max_cards=3)) == 3


def test_build_digest_empty_and_junk():
    assert pulse.build_digest([]) == []
    assert pulse.build_digest([None, "x", {"category": "g"}]) == []  # no title/value → skipped


def test_digest_cards_are_astralprims_shaped():
    cards = pulse.build_digest([{"category": "goal", "title": "Y", "salience": 0.5}])
    c = cards[0]
    assert c["type"] == "card" and isinstance(c["content"], list)
    assert c["content"][0]["type"] == "text"


# ───────────────────────── scheduling ────────────────────────────────────────

@pytest.mark.parametrize("req,cadence", [
    ("remind me every morning", "daily"),
    ("send me a summary daily", "daily"),
    ("every week on monday", "weekly"),
    ("weekly digest please", "weekly"),
    ("every weekday at 9:00", "weekday"),
    ("every hour", "hourly"),
    ("in 2 hours", "once"),
    ("just do the thing", "unknown"),
])
def test_propose_schedule_cadence(req, cadence):
    assert pulse.propose_schedule(req).cadence == cadence


def test_propose_schedule_extracts_time():
    assert pulse.propose_schedule("every weekday at 09:30").at == "09:30"
    assert pulse.propose_schedule("every morning").at == "morning"
    assert pulse.propose_schedule("every week on friday").at == "friday"


def test_propose_schedule_relative():
    p = pulse.propose_schedule("in 30 minutes")
    assert p.cadence == "once" and p.at == "+30m"
    assert pulse.propose_schedule("in 3 days").at == "+3d"


def test_proposal_needs_confirmation_and_schedulability():
    assert pulse.propose_schedule("daily").confirm_needed is True
    assert pulse.is_schedulable(pulse.propose_schedule("daily")) is True
    assert pulse.is_schedulable(pulse.propose_schedule("do the thing")) is False
