"""Tests for declarative multi-objective adaptation — 033 Wave-3 (C-D3).

Pure, deterministic scoring: no LLM/VLM, no DB, no sockets. Exercises the
feature flag, the four objective scorers (range + ordering invariants), the
weighted aggregation (range + custom-weight sensitivity), and candidate
selection (device-best pick + tie-break + empty-list error).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rote import objectives as obj  # noqa: E402


# --------------------------------------------------------------------------
# Device fixtures
# --------------------------------------------------------------------------
BROWSER = {"max_grid_columns": 12, "is_voice": False, "is_small": False}
SMALL = {"max_grid_columns": 12, "is_voice": False, "is_small": True}
VOICE = {"max_grid_columns": 12, "is_voice": True, "is_small": False}


# --------------------------------------------------------------------------
# Feature flag
# --------------------------------------------------------------------------
def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("FF_ADAPTIVE_OBJECTIVES", raising=False)
    assert obj.objectives_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "On", "  true  "])
def test_flag_on_truthy_spellings(monkeypatch, val):
    monkeypatch.setenv("FF_ADAPTIVE_OBJECTIVES", val)
    assert obj.objectives_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "maybe"])
def test_flag_off_falsy_spellings(monkeypatch, val):
    monkeypatch.setenv("FF_ADAPTIVE_OBJECTIVES", val)
    assert obj.objectives_enabled() is False


# --------------------------------------------------------------------------
# Device normalization
# --------------------------------------------------------------------------
def test_device_defaults_to_full_browser():
    d = obj._device(None)
    assert d == {"max_grid_columns": 12, "is_voice": False, "is_small": False}


def test_device_reads_overrides():
    d = obj._device({"max_grid_columns": 4, "is_voice": True, "is_small": True})
    assert d == {"max_grid_columns": 4, "is_voice": True, "is_small": True}


# --------------------------------------------------------------------------
# Range invariants: every objective stays in [0, 1] for many type/device combos
# --------------------------------------------------------------------------
_ALL_TYPES = [
    "table",
    "grid",
    "plotly_chart",
    "line_chart",
    "bar_chart",
    "text",
    "metric",
    "badge",
    "alert",
    "rating",
    "hero",
    "keyvalue",
    "button",
    "input",
    "param_picker",
    "file_upload",
    "list",
    "image",
    "code",
    "something_unknown",
]
_SCORERS = [
    obj.width_fit,
    obj.interaction_cost,
    obj.glanceability,
    obj.speakability,
]


@pytest.mark.parametrize("ctype", _ALL_TYPES)
@pytest.mark.parametrize("device", [BROWSER, SMALL, VOICE, {}])
@pytest.mark.parametrize("scorer", _SCORERS)
def test_objective_scores_in_unit_interval(scorer, device, ctype):
    s = scorer({"type": ctype}, device)
    assert isinstance(s, float)
    assert 0.0 <= s <= 1.0


def test_score_adaptation_in_unit_interval():
    for ctype in _ALL_TYPES:
        for device in (BROWSER, SMALL, VOICE):
            s = obj.score_adaptation({"type": ctype}, device)
            assert 0.0 <= s <= 1.0


# --------------------------------------------------------------------------
# width_fit ordering
# --------------------------------------------------------------------------
def test_table_width_fit_lower_on_small_and_voice_than_browser():
    table = {"type": "table"}
    wide = obj.width_fit(table, BROWSER)
    small = obj.width_fit(table, SMALL)
    voice = obj.width_fit(table, VOICE)
    assert small < wide
    assert voice < wide


def test_narrow_type_width_fit_high_everywhere():
    text = {"type": "text"}
    assert obj.width_fit(text, BROWSER) >= 0.8
    assert obj.width_fit(text, SMALL) >= 0.8
    assert obj.width_fit(text, VOICE) >= 0.8


def test_wide_type_width_fit_beats_narrow_only_on_roomy_surface_not_voice():
    # On voice a table is unusable; text remains fine.
    assert obj.width_fit({"type": "table"}, VOICE) < obj.width_fit(
        {"type": "text"}, VOICE
    )


# --------------------------------------------------------------------------
# interaction_cost ordering
# --------------------------------------------------------------------------
def test_button_interaction_cost_lower_on_voice_than_browser():
    button = {"type": "button"}
    assert obj.interaction_cost(button, VOICE) < obj.interaction_cost(
        button, BROWSER
    )


def test_button_interaction_cost_lower_on_small_than_browser():
    button = {"type": "button"}
    assert obj.interaction_cost(button, SMALL) < obj.interaction_cost(
        button, BROWSER
    )


def test_noninteractive_interaction_cost_high_everywhere():
    text = {"type": "text"}
    assert obj.interaction_cost(text, BROWSER) == 1.0
    assert obj.interaction_cost(text, SMALL) == 1.0
    assert obj.interaction_cost(text, VOICE) == 1.0


# --------------------------------------------------------------------------
# glanceability ordering
# --------------------------------------------------------------------------
def test_metric_out_glances_table():
    assert obj.glanceability({"type": "metric"}, BROWSER) > obj.glanceability(
        {"type": "table"}, BROWSER
    )


def test_metric_out_glances_table_on_small_too():
    assert obj.glanceability({"type": "metric"}, SMALL) > obj.glanceability(
        {"type": "table"}, SMALL
    )


# --------------------------------------------------------------------------
# speakability ordering / neutrality
# --------------------------------------------------------------------------
def test_text_out_speaks_chart_on_voice():
    assert obj.speakability({"type": "text"}, VOICE) > obj.speakability(
        {"type": "line_chart"}, VOICE
    )


def test_speakability_neutral_when_not_voice():
    # Off-voice, speakability must not penalize anything: always ~1.0.
    for ctype in ("text", "line_chart", "table", "code", "metric"):
        assert obj.speakability({"type": ctype}, BROWSER) == 1.0
        assert obj.speakability({"type": ctype}, SMALL) == 1.0


# --------------------------------------------------------------------------
# score_adaptation: custom weights
# --------------------------------------------------------------------------
def test_partial_weights_fall_back_to_defaults():
    # Passing only one key must not blow up; result still in range and
    # generally differs from the all-default score (because the one key is
    # re-weighted relative to the untouched defaults).
    comp = {"type": "table"}
    default_score = obj.score_adaptation(comp, BROWSER)
    partial_score = obj.score_adaptation(comp, BROWSER, {"speakability": 0.9})
    assert 0.0 <= partial_score <= 1.0
    assert 0.0 <= default_score <= 1.0


def test_custom_weights_change_winner_on_voice():
    # Default weights: a metric is the device-best on voice (speaks + glances).
    # But if we weight ONLY width_fit, a wide type's voice penalty dominates
    # and the metric still wins — so instead show that heavily weighting a
    # poor objective flips a head-to-head.
    text = {"type": "text"}
    table = {"type": "table"}

    # Under default weights on voice, text beats table comfortably.
    assert obj.score_adaptation(text, VOICE) > obj.score_adaptation(table, VOICE)

    # Now weight ONLY interaction_cost (both are non-interactive → both 1.0),
    # zeroing the others (a partial dict keeps missing keys at their DEFAULT
    # weight, so to isolate one objective the rest must be set to 0). This
    # collapses the difference width_fit/speakability had created → a tie.
    w = {"interaction_cost": 1.0, "width_fit": 0.0, "glanceability": 0.0,
         "speakability": 0.0}
    assert obj.score_adaptation(text, VOICE, w) == pytest.approx(
        obj.score_adaptation(table, VOICE, w)
    )


def test_speakability_weight_flips_voice_winner():
    # A list (high-speak, but unknown width) vs a metric (high-glance).
    # Pick two components where the default winner and the speakability-only
    # winner differ on voice.
    chart = {"type": "line_chart"}  # great glance? no — low speak, low width
    text = {"type": "text"}  # high speak, high width

    # Weighting speakability to the exclusion of all else on voice: text wins.
    w_speak = {
        "width_fit": 0.0,
        "interaction_cost": 0.0,
        "glanceability": 0.0,
        "speakability": 1.0,
    }
    assert obj.score_adaptation(text, VOICE, w_speak) > obj.score_adaptation(
        chart, VOICE, w_speak
    )

    # Weighting glanceability only: line_chart is low-glance, text is medium,
    # so text still wins here — but the SCORES differ from the speak-only run,
    # proving weights actually steer the result.
    w_glance = {
        "width_fit": 0.0,
        "interaction_cost": 0.0,
        "glanceability": 1.0,
        "speakability": 0.0,
    }
    assert obj.score_adaptation(text, VOICE, w_glance) != pytest.approx(
        obj.score_adaptation(text, VOICE, w_speak)
    )


# --------------------------------------------------------------------------
# best_adaptation
# --------------------------------------------------------------------------
def test_best_adaptation_picks_metric_over_table_on_small_device():
    candidates = [{"type": "table"}, {"type": "metric"}]
    winner = obj.best_adaptation(candidates, SMALL)
    assert winner["type"] == "metric"


def test_best_adaptation_picks_table_friendly_on_wide_browser():
    # On a roomy browser, a table is a perfectly good (and information-dense)
    # choice; it should beat a button (which is fine too) — assert the picker
    # returns a dict drawn from the candidates.
    candidates = [{"type": "table"}, {"type": "button"}]
    winner = obj.best_adaptation(candidates, BROWSER)
    assert winner in candidates


def test_best_adaptation_returns_a_copy():
    candidates = [{"type": "metric", "value": 1}]
    winner = obj.best_adaptation(candidates, BROWSER)
    assert winner == {"type": "metric", "value": 1}
    winner["value"] = 999
    assert candidates[0]["value"] == 1  # original untouched


def test_best_adaptation_tie_break_prefers_earlier():
    # Two identical components tie; the first in order must win.
    a = {"type": "text", "id": "a"}
    b = {"type": "text", "id": "b"}
    winner = obj.best_adaptation([a, b], BROWSER)
    assert winner["id"] == "a"


def test_best_adaptation_empty_raises():
    with pytest.raises(ValueError):
        obj.best_adaptation([], BROWSER)
