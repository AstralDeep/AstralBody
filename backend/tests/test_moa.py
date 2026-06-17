from __future__ import annotations
import sys
from pathlib import Path
import pytest
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
from orchestrator import moa  # noqa: E402
from orchestrator.moa import Proposal  # noqa: E402


# --------------------------------------------------------------------------- #
# Feature flag                                                                 #
# --------------------------------------------------------------------------- #
def test_moa_enabled_default_off(monkeypatch):
    monkeypatch.delenv("FF_MOA_DEBATE", raising=False)
    assert moa.moa_enabled() is False


def test_moa_enabled_truthy_values(monkeypatch):
    for value in ("1", "true", "TRUE", "Yes", " on ", "On"):
        monkeypatch.setenv("FF_MOA_DEBATE", value)
        assert moa.moa_enabled() is True, value


def test_moa_enabled_falsy_values(monkeypatch):
    for value in ("0", "false", "no", "off", "", "maybe"):
        monkeypatch.setenv("FF_MOA_DEBATE", value)
        assert moa.moa_enabled() is False, value


# --------------------------------------------------------------------------- #
# should_invoke gating                                                         #
# --------------------------------------------------------------------------- #
def test_should_invoke_high_difficulty_triggers():
    # Hard turn, but confident: difficulty branch alone must trigger.
    assert moa.should_invoke(difficulty=0.9, confidence=0.95) is True


def test_should_invoke_low_confidence_triggers():
    # Easy turn, but unsure: confidence branch alone must trigger.
    assert moa.should_invoke(difficulty=0.1, confidence=0.2) is True


def test_should_invoke_easy_and_confident_does_not():
    assert moa.should_invoke(difficulty=0.1, confidence=0.95) is False


def test_should_invoke_difficulty_boundary():
    # difficulty == threshold triggers (>=); just-below does not.
    assert moa.should_invoke(difficulty=0.6, confidence=0.95) is True
    assert moa.should_invoke(difficulty=0.5999, confidence=0.95) is False


def test_should_invoke_confidence_boundary():
    # confidence == threshold triggers (<=); just-above does not.
    assert moa.should_invoke(difficulty=0.1, confidence=0.5) is True
    assert moa.should_invoke(difficulty=0.1, confidence=0.5001) is False


def test_should_invoke_custom_thresholds():
    # With a stricter difficulty gate, the same hard-ish turn no longer fires
    # on difficulty, and a tighter confidence gate keeps it from firing there.
    assert (
        moa.should_invoke(
            difficulty=0.7,
            confidence=0.6,
            difficulty_threshold=0.8,
            confidence_threshold=0.4,
        )
        is False
    )
    assert (
        moa.should_invoke(
            difficulty=0.85,
            confidence=0.6,
            difficulty_threshold=0.8,
            confidence_threshold=0.4,
        )
        is True
    )


# --------------------------------------------------------------------------- #
# aggregate                                                                    #
# --------------------------------------------------------------------------- #
def test_aggregate_picks_top_score():
    proposals = [
        Proposal(agent="a", text="low", score=0.1),
        Proposal(agent="b", text="high", score=0.9),
        Proposal(agent="c", text="mid", score=0.5),
    ]
    winner = moa.aggregate(proposals)
    assert winner.agent == "b"
    assert winner.text == "high"


def test_aggregate_tie_break_is_earliest():
    proposals = [
        Proposal(agent="first", text="x", score=0.8),
        Proposal(agent="second", text="y", score=0.8),
    ]
    assert moa.aggregate(proposals).agent == "first"


def test_aggregate_empty_raises():
    with pytest.raises(ValueError):
        moa.aggregate([])


# --------------------------------------------------------------------------- #
# majority_answer                                                              #
# --------------------------------------------------------------------------- #
def test_majority_answer_counts_normalized_text():
    proposals = [
        Proposal(agent="a", text="Yes"),
        Proposal(agent="b", text="  yes "),
        Proposal(agent="c", text="no"),
    ]
    # "Yes" and "  yes " normalize to the same "yes" -> majority.
    assert moa.majority_answer(proposals) == "yes"


def test_majority_answer_tie_break_earliest():
    proposals = [
        Proposal(agent="a", text="alpha"),
        Proposal(agent="b", text="beta"),
    ]
    # 1-1 tie; earliest normalized text wins.
    assert moa.majority_answer(proposals) == "alpha"


def test_majority_answer_custom_key():
    proposals = [
        Proposal(agent="a", text="ANSWER-1"),
        Proposal(agent="b", text="answer-2"),
        Proposal(agent="c", text="answer-3"),
    ]
    # Normalizer collapses everything to the part before the dash, so all
    # three share the same bucket "answer".
    result = moa.majority_answer(proposals, key=lambda t: t.split("-")[0].lower())
    assert result == "answer"


def test_majority_answer_empty_is_none():
    assert moa.majority_answer([]) is None


# --------------------------------------------------------------------------- #
# debate_judge                                                                 #
# --------------------------------------------------------------------------- #
def _const_judge(value: int):
    """Return a judge callable that always returns ``value``."""

    def judge(a: Proposal, b: Proposal) -> int:
        return value

    return judge


def test_debate_judge_a_wins():
    a = Proposal(agent="a", text="a", score=0.0)
    b = Proposal(agent="b", text="b", score=1.0)
    # Judge says -1 (a wins) even though b scores higher.
    assert moa.debate_judge(a, b, _const_judge(-1)) is a


def test_debate_judge_b_wins():
    a = Proposal(agent="a", text="a", score=1.0)
    b = Proposal(agent="b", text="b", score=0.0)
    assert moa.debate_judge(a, b, _const_judge(1)) is b


def test_debate_judge_tie_picks_a():
    a = Proposal(agent="a", text="a", score=0.0)
    b = Proposal(agent="b", text="b", score=0.0)
    assert moa.debate_judge(a, b, _const_judge(0)) is a


def test_debate_judge_raises_falls_back_to_higher_score():
    a = Proposal(agent="a", text="a", score=0.2)
    b = Proposal(agent="b", text="b", score=0.9)

    def boom(a, b):
        raise RuntimeError("judge exploded")

    assert moa.debate_judge(a, b, boom) is b


def test_debate_judge_raises_fallback_tie_prefers_a():
    a = Proposal(agent="a", text="a", score=0.5)
    b = Proposal(agent="b", text="b", score=0.5)

    def boom(a, b):
        raise ValueError("nope")

    # Equal scores -> `a` wins the fallback (>= keeps a).
    assert moa.debate_judge(a, b, boom) is a


# --------------------------------------------------------------------------- #
# panel                                                                        #
# --------------------------------------------------------------------------- #
def test_panel_without_judge_uses_aggregate():
    proposals = [
        Proposal(agent="a", text="low", score=0.1),
        Proposal(agent="b", text="high", score=0.9),
    ]
    assert moa.panel(proposals).agent == "b"


def test_panel_with_judge_runs_single_elimination():
    proposals = [
        Proposal(agent="a", text="a", score=0.0),
        Proposal(agent="b", text="b", score=0.0),
        Proposal(agent="c", text="c", score=0.0),
    ]

    # Judge that always prefers `b` (the second arg / challenger) means the
    # last challenger standing wins the left-fold tournament: c.
    assert moa.panel(proposals, judge=_const_judge(1)).agent == "c"

    # Judge that always keeps the running winner (`a` / first arg) means the
    # very first proposal survives every round: a.
    assert moa.panel(proposals, judge=_const_judge(-1)).agent == "a"


def test_panel_with_judge_single_proposal():
    only = Proposal(agent="solo", text="x", score=0.3)
    # One proposal: reduce returns it untouched, judge never called.
    assert moa.panel([only], judge=_const_judge(1)) is only


def test_panel_empty_raises():
    with pytest.raises(ValueError):
        moa.panel([])
