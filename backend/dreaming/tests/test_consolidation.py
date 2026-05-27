"""Tests for consolidation scoring + sweep (feature 025, T051/T052)."""
from __future__ import annotations

from dreaming.consolidation import run_sweep, score_signal, select_promotions
from personalization.phi_gate import PHIGate

NOW = 1_748_300_000_000


class _CleanAnalyzer:
    def analyze(self, text, language, entities, score_threshold):
        return []


def _clean_gate() -> PHIGate:
    return PHIGate(analyzer=_CleanAnalyzer())


class _FakeRepo:
    def __init__(self, signals):
        self._signals = {s["id"]: s for s in signals}
        self.memory = []
        self.sweeps = []

    def list_signals(self, user_id):
        return list(self._signals.values())

    def create_memory(self, user_id, category, value, *, source="explicit", salience=0.0):
        item = {"id": f"m{len(self.memory)}", "category": category, "value": value, "source": source}
        self.memory.append(item)
        return item

    def delete_signal(self, user_id, sig_id):
        self._signals.pop(sig_id, None)

    def record_sweep(self, sweep):
        self.sweeps.append(sweep)


def test_score_rewards_frequency_and_recency():
    recent = score_signal(3, NOW, NOW)
    stale = score_signal(3, NOW - 30 * 86_400_000, NOW)
    assert recent > stale


def test_select_excludes_one_offs():
    signals = [
        {"id": "a", "category": "preference", "value": "x", "recall_count": 1, "last_seen_at": NOW},
        {"id": "b", "category": "preference", "value": "y", "recall_count": 3, "last_seen_at": NOW},
    ]
    chosen = select_promotions(signals, NOW, min_recalls=2)
    assert [c["id"] for c in chosen] == ["b"]  # one-off "a" excluded


def test_run_sweep_promotes_recurring_excludes_phi():
    signals = [
        {"id": "a", "category": "preference", "value": "prefers bullet points", "recall_count": 3, "last_seen_at": NOW},
        {"id": "b", "category": "context", "value": "one-off note", "recall_count": 1, "last_seen_at": NOW},
        {"id": "c", "category": "context", "value": "SSN 123-45-6789", "recall_count": 4, "last_seen_at": NOW},
    ]
    repo = _FakeRepo(signals)
    sweep = run_sweep(repo, _clean_gate(), "u1", now_ms=NOW, min_recalls=2)

    # Only the recurring, non-PHI signal "a" is promoted.
    assert sweep["promoted_count"] == 1
    assert repo.memory[0]["value"] == "prefers bullet points"
    assert repo.memory[0]["source"] == "promoted"
    # The PHI signal "c" was eligible by recall count but blocked + removed.
    assert all(m["value"] != "SSN 123-45-6789" for m in repo.memory)
    assert "c" not in repo._signals
    assert repo.sweeps and repo.sweeps[0]["trigger"] == "scheduled"
